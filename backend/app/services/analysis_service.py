import json
import logging
import re

from sqlalchemy.orm import Session, joinedload

from app.constants import AnalysisStatus
from app.models import Analysis, PromptTemplate, Report

logger = logging.getLogger(__name__)

# Gemini 입력 한도 (실측 1.49자/토큰 기준 — 1.4M자 ≈ 94만 토큰, 상한 1,048,576에 근접)
MAX_CHARS = 1_400_000


def _truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    head = int(MAX_CHARS * 0.8)
    tail = MAX_CHARS - head
    return text[:head] + "\n\n[...중간 내용 생략...]\n\n" + text[-tail:]


def extract_json(raw: str) -> dict:
    """LLM 응답에서 JSON 추출.

    코드 블록을 벗겨낸 뒤 raw_decode로 첫 객체만 취한다 — 모델이 끝에 잉여 문자를
    붙이는 경우가 있어 json.loads는 "Extra data"로 실패한다.
    """
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE).strip()
    return json.JSONDecoder().raw_decode(text[text.index("{"):])[0]


def get_by_status(db: Session, report_id: int, status: str) -> list[Analysis]:
    """report_id의 특정 상태 분석들을 report·company까지 즉시 로드해 반환."""
    return (
        db.query(Analysis)
        .options(joinedload(Analysis.report).joinedload(Report.company))
        .filter(Analysis.report_id == report_id, Analysis.status == status)
        .all()
    )


def get_pending(db: Session, report_id: int) -> list[Analysis]:
    return get_by_status(db, report_id, AnalysisStatus.PENDING)


def get_running(db: Session, report_id: int) -> list[Analysis]:
    return get_by_status(db, report_id, AnalysisStatus.RUNNING)


def build_prompts(
    db: Session, report: Report, types_to_run: list[str], report_text: str
) -> tuple[str, str, int]:
    """3종 분석을 1회 호출로 묶는 통합 프롬프트를 조립.

    반환: (system_prompt, user_prompt, max_output_tokens)
    """
    templates: dict[str, PromptTemplate] = {
        t.analysis_type: t
        for t in db.query(PromptTemplate)
        .filter(PromptTemplate.analysis_type.in_(types_to_run))
        .all()
    }
    missing = [t for t in types_to_run if t not in templates]
    if missing:
        raise ValueError(f"프롬프트 템플릿이 없습니다: {', '.join(missing)}")

    # ── 통합 시스템 프롬프트 ── (라벨은 PromptTemplate.label 재사용)
    sections = "\n\n".join(
        f"## [{templates[t].label}] 분석 지침\n{templates[t].system_prompt}"
        for t in types_to_run
    )
    keys_desc = ", ".join(f'"{t}"' for t in types_to_run)
    system_prompt = f"""{sections}

---
위의 {len(types_to_run)}가지 분석을 동시에 수행합니다.
반드시 아래 JSON 형식으로만 응답하세요. 마크다운 코드 블록 없이 순수 JSON만 출력하세요.
각 값은 해당 분석 지침에서 요구하는 마크다운 형식 그대로 작성합니다.

{{{keys_desc}: "마크다운 텍스트"}}"""

    # user_prompt_template들은 보고서 부분이 동일 → 보고서는 한 번만 첨부하고 분석 지시만 결합
    user_prompt = (
        f"아래는 {report.company.corp_name}의 {report.fiscal_year}년 사업보고서 전문입니다.\n"
        f"위의 {len(types_to_run)}가지 분석을 모두 수행하고 JSON으로 반환해주세요.\n\n"
        f"---\n{_truncate(report_text)}"
    )
    # 출력 토큰: 분석 유형당 ~8192 × 유형 수
    return system_prompt, user_prompt, 8192 * len(types_to_run)


def save_result(db: Session, pending: list[Analysis], raw: str, model_name: str) -> None:
    """LLM 응답을 분석 유형별로 분배해 저장. 커밋까지 수행."""
    try:
        result = extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("JSON 파싱 실패, 전체 텍스트를 첫 번째 유형에 저장: %s", e)
        result = {pending[0].analysis_type: raw}

    for a in pending:
        text = result.get(a.analysis_type, "")
        a.result_summary = text
        a.model_name = model_name
        a.status = AnalysisStatus.COMPLETED if text else AnalysisStatus.FAILED
        if not text:
            a.error_message = "LLM 응답에 해당 분석 유형 결과가 없습니다."
    db.commit()


def mark_failed(db: Session, pending: list[Analysis], message: str) -> None:
    for a in pending:
        a.status = AnalysisStatus.FAILED
        a.error_message = message
    db.commit()
