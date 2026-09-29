import json
import logging
import re

from sqlalchemy.orm import Session, joinedload

from app.constants import ANALYSIS_TYPES, MALFORMED_RESPONSE_PREFIX, AnalysisStatus
from app.models import Analysis, PromptTemplate, Report

logger = logging.getLogger(__name__)

# Gemini 입력 한도 (실측 1.49자/토큰 기준 — 1.4M자 ≈ 94만 토큰, 상한 1,048,576에 근접)
MAX_CHARS = 1_400_000
OUTPUT_TOKENS_PER_TYPE = 12_288


def _truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    head = int(MAX_CHARS * 0.8)
    tail = MAX_CHARS - head
    return text[:head] + "\n\n[...중간 내용 생략...]\n\n" + text[-tail:]


# 원문의 큰따옴표(27" 모니터, "E-FOREST" 등)를 모델이 인용하며 그대로 옮기면
# responseSchema가 거는 JSON 문법상 **문자열의 끝**으로 해석된다. 그 뒤 내용은 조용히
# 버려지고 상태는 completed로 남는다 — 실측 30건 중 2건(삼성전자 rnd가 `| SDC | 27`에서,
# 바이오솔루션 national_tech가 인용을 여는 `"`에서 끊겼다). 실시간 재현 18건 중 2건.
# 원문에서 미리 치워 두고, 지침으로 인용 부호를 「」로 고정한다.
_ASCII_QUOTE = str.maketrans({'"': "″"})


def _last_heading(system_prompt: str) -> str | None:
    """템플릿이 요구하는 마지막 `## ` 제목. 결과에 이것이 없으면 응답이 도중에 끊긴 것이다."""
    heads = re.findall(r"^## (.+?)\s*$", system_prompt, flags=re.MULTILINE)
    return heads[-1] if heads else None


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


def mark_pending(db: Session, report: Report, existing: dict[str, Analysis],
                 types: tuple[str, ...] | list[str] = ANALYSIS_TYPES,
                 skip_completed: bool = True) -> int:
    """분석을 pending으로 만든다 — 있으면 되돌리고 없으면 만든다. 커밋·큐 투입은 호출자가 한다.

    skip_completed=True면 이미 완료된 유형은 건너뛴다(비용이 곱해지므로 다시 돌리지 않는다).
    existing은 미리 조회한 {유형: Analysis}라 여러 보고서를 묶을 때 N+1이 생기지 않는다.
    반환: pending이 된 유형 수.
    """
    n = 0
    for atype in types:
        a = existing.get(atype)
        if skip_completed and a and a.status == AnalysisStatus.COMPLETED:
            continue
        if a:
            a.status = AnalysisStatus.PENDING
            a.error_message = None
        else:
            db.add(Analysis(company_id=report.company_id, report_id=report.id,
                            analysis_type=atype, status=AnalysisStatus.PENDING))
        n += 1
    return n


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
**본문에 큰따옴표(")를 쓰지 마세요.** JSON 문자열이 거기서 끝나 뒤 내용이 전부 사라집니다.
보고서를 인용할 때는 「」로 감싸고, 인치 표기는 27인치처럼 풀어 씁니다.

{{{keys_desc}: "마크다운 텍스트"}}"""

    # 보고서는 한 번만 첨부하고 분석 지시(system_prompt)만 유형별로 결합한다
    user_prompt = (
        f"아래는 {report.company.corp_name}의 {report.fiscal_year}년 사업보고서 전문입니다.\n"
        f"위의 {len(types_to_run)}가지 분석을 모두 수행하고 JSON으로 반환해주세요.\n\n"
        f"---\n{_truncate(report_text).translate(_ASCII_QUOTE)}"
    )
    # 출력 토큰: 분석 유형당 12,288 × 유형 수. 3.8-flash는 출력이 길다 — 실측 최대 20.9k
    # (POSCO홀딩스)로 예전 상한 24,576(8,192×3)의 85%였다. 상한은 쓴 만큼만 과금된다
    return system_prompt, user_prompt, OUTPUT_TOKENS_PER_TYPE * len(types_to_run)


def save_result(db: Session, pending: list[Analysis], raw: str, model_name: str) -> None:
    """LLM 응답을 분석 유형별로 분배해 저장. 커밋까지 수행."""
    try:
        result = extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        # 예전엔 raw 전체를 첫 유형에 넣었는데, 잘린 JSON 안에도 `## 시사점`이 들어 있어
        # 끊김 판정을 통과해 completed로 저장됐다(나머지 둘만 failed). 전부 실패로 둔다
        logger.warning("JSON 파싱 실패, 담당 분석 전부 failed: %s", e)
        for a in pending:
            a.model_name = model_name
        mark_failed(db, pending, f"{MALFORMED_RESPONSE_PREFIX}JSON 파싱 실패({e}). 재분석하세요.")
        return

    last = {
        t.analysis_type: _last_heading(t.system_prompt)
        for t in db.query(PromptTemplate)
        .filter(PromptTemplate.analysis_type.in_([a.analysis_type for a in pending]))
        .all()
    }
    for a in pending:
        text = result.get(a.analysis_type, "")
        a.result_summary = text
        a.model_name = model_name
        a.status = AnalysisStatus.COMPLETED if text else AnalysisStatus.FAILED
        if not text:
            a.error_message = "LLM 응답에 해당 분석 유형 결과가 없습니다."
        elif last.get(a.analysis_type) and f"## {last[a.analysis_type]}" not in text:
            # 끊긴 결과를 completed로 두면 기술 종합 보고서가 반쪽 근거로 판정한다
            a.status = AnalysisStatus.FAILED
            a.error_message = (f"응답이 중간에 끊겼습니다 — 마지막 항목 "
                               f"'## {last[a.analysis_type]}'이 없습니다. 재분석하세요.")
    db.commit()


def mark_failed(db: Session, pending: list[Analysis], message: str) -> None:
    for a in pending:
        a.status = AnalysisStatus.FAILED
        a.error_message = message
    db.commit()
