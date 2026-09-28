"""기술 설명 → 특허 → 기업 → 보고서 → 분석까지 잇는 파이프라인.

앞단(특허·매칭)은 신규지만 뒷단은 기존 서비스를 그대로 쓴다.
기업 등록·보고서 수집·분석 큐는 이미 있는 것을 부르기만 한다.

**비용이 기업 수만큼 곱해진다.** 보고서 1건당 약 $0.048이므로 상한 없이 돌리면
기술 하나에 수십 건이 나간다. 호출부가 반드시 상한을 정하게 한다.
"""
import asyncio
import json
import logging
from datetime import datetime

from google.genai import types
from sqlalchemy.orm import Session

from app.config import gemini
from app.constants import REPORT_TYPE_ANNUAL
from app.models import Company, DartCorp, Report
from app.services.analysis_queue import queue_report
from app.services.dart_client import list_reports
from app.services.report_service import create_report_from_dart

logger = logging.getLogger(__name__)

# ── 온보딩 순서 ─────────────────────────────────────────────────────────────
# `onboard`는 앞에서부터 max_companies개를 자르므로 **순서가 곧 누가 분석되는가**다.
#
# 특허 건수만으로는 두 가지를 못 가른다(6개 키워드 세트 × 기업 120곳을 제목으로 수작업 판정):
#   1) 사업을 접은 기업 — 옛 특허로 올라온다. 최근 10년 건수로 센다(patent_search.RECENT_YEARS)
#   2) 낱말만 겹친 다른 기술 — '유전자 가위 염기 교정'에 식물 유전자교정(NH농우바이오·LG화학)과
#      이종장기 돼지(옵티팜)가, '리튬 이온 전도도'에 레독스 흐름전지(HLB제약)가 걸린다.
#      건수·최근성·키워드 수로는 안 걸러진다 — 제목을 읽어야 안다
# 그래서 후보가 상한보다 많을 때만 LLM이 기업별 특허 제목을 읽고 core/peripheral/unrelated로
# 판정한다. **순서만 바꾸고 아무도 버리지 않는다** — unrelated는 맨 뒤로 갈 뿐이다.
#
# 실측 P@5(상위 5곳 중 실제로 그 기술을 하는 기업, 6세트 합계 30):
#   건수순 25 → 최근10년순 26 → 판정+최근10년순 30(3.8-flash, 3회 모두)
# 3.5-flash-lite 29.0·3.7-flash 29.3(3회 평균). 3.8-flash는 3.7-flash와 가격이 같고
# 판정 흔들림도 가장 적었다(반복 간 판정이 바뀐 기업 10/119, 3.7 15, 3.5-lite 18).
# 입력 ~3천·출력 ~700토큰, 3초 — 기업 1곳 분석($0.048)보다 싸다.
FIT_MODEL = "gemini-3.8-flash"
# 3.8-flash도 MINIMAL을 지원하지 않는다. LOW에서 thinking 토큰은 실측 0이었다
# (MEDIUM은 ~1,000토큰·2배 느린데 P@5가 같았다)
FIT_THINKING = types.ThinkingLevel.LOW
FIT_MAX_COMPANIES = 30      # 판정에 올릴 후보 수(최근순 상위). 그 뒤는 어차피 상한 밖이다
FIT_TITLES = 10             # 기업당 특허 제목 수
ROLE_RANK = {"core": 0, "peripheral": 1, "unrelated": 2}

FIT_PROMPT = """기술: {name}
설명: {description}

아래는 이 기술 키워드로 특허를 검색해 나온 한국 기업과, 그 기업의 검색된 특허 제목이다.
기업마다 "이 기업이 지금 이 기술을 하는가"를 특허 제목만 근거로 판정하라.

- core: 제목이 이 기술 자체(핵심 소재·부품·공정·제품)를 다루고, 최근 10년 안에 출원한 것이 있다
- peripheral: 이 기술의 가치사슬 주변(장비·부자재·재활용·응용)이거나, 관련 특허가 10년도 더 된 것뿐이다
- unrelated: 키워드의 낱말이 우연히 겹쳤을 뿐 다른 기술이다(다른 전지 종류·식물·화장품·다른 산업 등)

기업 이름이나 규모로 판단하지 말고 제목으로만 판단하라.

{rows}

JSON 배열로만 답하라: [{{"corp": "기업명", "role": "core|peripheral|unrelated", "reason": "15자 이내"}}]"""

def rank(cands: list[dict]) -> list[dict]:
    """판정(없으면 동률) → 최근 출원 건수 → 누적 건수 순."""
    return sorted(cands, key=lambda x: (ROLE_RANK.get(x.get("role"), 1),
                                        -x.get("recent", x["patents"]), -x["patents"]))


def _judge_sync(name: str, description: str, cands: list[dict],
                patents: dict[str, list[dict]]) -> dict[str, dict]:
    rows = []
    for x in cands:
        titles = "\n".join(f"    - {it.get('app_date', '')[:4]} {it.get('status', '')} {it.get('title', '')}"
                           for it in patents.get(x["applicant"], [])[:FIT_TITLES])
        rows.append(f"## {x['corp_name']} (특허 {x['patents']}건)\n{titles}")
    r = gemini().models.generate_content(
        model=FIT_MODEL,
        contents=FIT_PROMPT.format(name=name, description=description, rows="\n".join(rows)),
        config=types.GenerateContentConfig(
            temperature=0, max_output_tokens=4096, response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_level=FIT_THINKING)))
    return {j["corp"]: j for j in json.loads(r.text or "[]") if isinstance(j, dict) and "corp" in j}


async def order_candidates(name: str, description: str, cands: list[dict],
                           patents: dict[str, list[dict]], max_companies: int) -> list[dict]:
    """온보딩 순서. 상한이 후보보다 작을 때만 LLM 판정을 붙인다(0=전체면 순서가 무의미).

    판정이 실패해도 온보딩을 막지 않는다 — 최근 출원순으로 대신한다.
    """
    cands = rank(cands)
    if not max_companies or len(cands) <= max_companies:
        return cands
    head = cands[:FIT_MAX_COMPANIES]
    try:
        roles = await asyncio.to_thread(_judge_sync, name, description, head, patents)
    except Exception:
        logger.exception("적합도 판정 실패 — 최근 출원순으로 온보딩합니다")
        return cands
    for x in head:
        j = roles.get(x["corp_name"])
        if j and j.get("role") in ROLE_RANK:
            x["role"], x["reason"] = j["role"], j.get("reason")
    return rank(head) + cands[FIT_MAX_COMPANIES:]


def register_company(db: Session, corp_code: str) -> Company | None:
    """DART 색인에 있는 기업을 추적 대상으로 올린다. 이미 있으면 그대로 돌려준다."""
    existing = db.query(Company).filter(Company.corp_code == corp_code).first()
    if existing:
        return existing

    indexed = db.get(DartCorp, corp_code)
    if indexed is None:
        logger.warning("DART 색인에 없는 corp_code: %s", corp_code)
        return None

    company = Company(corp_code=indexed.corp_code, corp_name=indexed.corp_name,
                      stock_code=indexed.stock_code, jurir_no=indexed.jurir_no)
    db.add(company)
    db.commit()
    db.refresh(company)
    logger.info("기업 등록: %s (%s)", company.corp_name, corp_code)
    return company


async def ensure_latest_report(db: Session, company: Company, year: int | None = None) -> Report | None:
    """기업의 최신 사업보고서를 확보한다. 이미 있으면 그것을 쓴다(재다운로드하지 않는다)."""
    have = (db.query(Report)
            .filter(Report.company_id == company.id,
                    Report.report_type == REPORT_TYPE_ANNUAL,
                    Report.file_path.isnot(None))
            .order_by(Report.fiscal_year.desc())
            .first())
    if have and (year is None or have.fiscal_year == year):
        return have

    target = year or datetime.utcnow().year - 1
    dart_reports = await list_reports(company.corp_code,
                                      bgn_de=f"{target}0101", end_de=f"{target + 1}1231")
    if not dart_reports:
        logger.info("사업보고서 없음: %s (%d년)", company.corp_name, target)
        return have

    try:
        return await create_report_from_dart(db, company, dart_reports[0], target)
    except Exception:
        logger.exception("보고서 수집 실패: %s", company.corp_name)
        return have



async def onboard(db: Session, candidates: list[dict], max_companies: int,
                  year: int | None = None) -> dict:
    """미등록 후보를 등록하고 보고서를 확보한 뒤 분석 큐에 넣는다.

    candidates는 **이미 순서가 정해진** 후보(`order_candidates`). 앞에서부터 자른다.

    **비용이 기업 수만큼 곱해진다**(보고서 1건당 약 $0.048). `max_companies`가
    상한이고, **0이면 전체**다 — 후보를 다 태우겠다는 선택은 화면에서 예상 비용을
    보여준 뒤 받는다.
    """
    picked = candidates[:max_companies] if max_companies else candidates
    registered, with_report, queued_reports, failed = [], [], 0, []

    for cand in picked:
        company = register_company(db, cand["corp_code"])
        if company is None:
            failed.append({**cand, "reason": "색인 조회 실패"})
            continue
        registered.append((company, cand))

        report = await ensure_latest_report(db, company, year)
        if report is None:
            failed.append({**cand, "reason": "사업보고서 없음"})
            continue
        with_report.append((company, report))

        if queue_report(db, report):
            queued_reports += 1

    return {
        # role·reason은 적합도 판정을 거친 경우에만 있다 — 왜 이 기업이 뽑혔는지
        "registered": [{"company_id": c.id, "corp_name": c.corp_name,
                        "role": x.get("role"), "reason": x.get("reason")} for c, x in registered],
        "reports": [{"company": c.corp_name, "report_id": r.id,
                     "fiscal_year": r.fiscal_year} for c, r in with_report],
        "queued_reports": queued_reports,
        "failed": failed,
    }
