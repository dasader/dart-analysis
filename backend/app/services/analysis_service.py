import json
import logging
import re

from sqlalchemy.orm import Session

from app.models import Analysis, PromptTemplate
from app.services.gemini_client import generate, MODEL_NAME
from app.services.report_service import extract_text_from_report

logger = logging.getLogger(__name__)

VALID_TYPES = ["subsidiary", "rnd", "national_tech"]

# Gemini 입력 한도 (한국어 ~1.65자/토큰 기준 안전 상한)
MAX_CHARS = 1_400_000


def _truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    head = int(MAX_CHARS * 0.8)
    tail = MAX_CHARS - head
    return text[:head] + "\n\n[...중간 내용 생략...]\n\n" + text[-tail:]


def _extract_json(raw: str) -> dict:
    """Gemini 응답에서 JSON 추출. 코드 블록으로 감싸진 경우 제거."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    return json.loads(text.strip())


async def run_combined_analysis(db: Session, report_id: int) -> None:
    """report_id에 대해 pending 상태인 분석들을 Gemini 1회 호출로 일괄 처리."""
    pending = (
        db.query(Analysis)
        .filter(Analysis.report_id == report_id, Analysis.status == "pending")
        .all()
    )
    if not pending:
        return

    report = pending[0].report
    types_to_run = [a.analysis_type for a in pending]
    logger.info("combined analysis 시작: report_id=%d, types=%s", report_id, types_to_run)

    # 모두 running으로 전환
    for a in pending:
        a.status = "running"
    db.commit()

    try:
        # 보고서 텍스트 추출
        report_text = _truncate(extract_text_from_report(report.file_path) or "")
        if not report_text:
            raise ValueError("보고서 텍스트를 추출할 수 없습니다.")

        # 각 분석 유형의 프롬프트 템플릿 로드
        templates: dict[str, PromptTemplate] = {}
        for atype in types_to_run:
            t = db.query(PromptTemplate).filter_by(analysis_type=atype).first()
            if not t:
                raise ValueError(f"프롬프트 템플릿이 없습니다: {atype}")
            templates[atype] = t

        # ── 통합 시스템 프롬프트 ──────────────────────────────────────
        type_labels = {
            "subsidiary": "종속회사 변동 분석",
            "rnd": "R&D/투자 분석",
            "national_tech": "국가전략기술 분석",
        }
        sections = "\n\n".join(
            f"## [{type_labels[t]}] 분석 지침\n{templates[t].system_prompt}"
            for t in types_to_run
        )
        keys_desc = ", ".join(f'"{t}"' for t in types_to_run)
        system_prompt = f"""{sections}

---
위의 {len(types_to_run)}가지 분석을 동시에 수행합니다.
반드시 아래 JSON 형식으로만 응답하세요. 마크다운 코드 블록 없이 순수 JSON만 출력하세요.
각 값은 해당 분석 지침에서 요구하는 마크다운 형식 그대로 작성합니다.

{{{keys_desc}: "마크다운 텍스트"}}"""

        # ── 통합 유저 프롬프트 ────────────────────────────────────────
        # user_prompt_template들은 {report_text} 변수만 다르고 보고서 부분 동일
        # → 보고서는 한 번만 첨부하고 분석 지시만 결합
        user_prompt = (
            f"아래는 {report.company.corp_name}의 {report.fiscal_year}년 사업보고서 전문입니다.\n"
            f"위의 {len(types_to_run)}가지 분석을 모두 수행하고 JSON으로 반환해주세요.\n\n"
            f"---\n{report_text}"
        )

        # ── 단일 Gemini 호출 ──────────────────────────────────────────
        # 출력 토큰: 분석 유형당 ~8192 × 유형 수
        max_output = 8192 * len(types_to_run)
        raw = await generate(system_prompt, user_prompt, max_output_tokens=max_output)

        # ── JSON 파싱 ─────────────────────────────────────────────────
        try:
            result = _extract_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("JSON 파싱 실패, 전체 텍스트를 첫 번째 유형에 저장: %s", e)
            result = {types_to_run[0]: raw}

        # ── 개별 Analysis 레코드 업데이트 ─────────────────────────────
        for a in pending:
            text = result.get(a.analysis_type, "")
            a.result_summary = text
            a.result_json = json.dumps({"raw_response": text}, ensure_ascii=False)
            a.model_name = MODEL_NAME
            a.status = "completed" if text else "failed"
            if not text:
                a.error_message = "LLM 응답에 해당 분석 유형 결과가 없습니다."
        db.commit()
        logger.info("combined analysis 완료: report_id=%d", report_id)

    except Exception as e:
        for a in pending:
            a.status = "failed"
            a.error_message = str(e)
        db.commit()
        logger.exception("combined analysis 실패: report_id=%d", report_id)
