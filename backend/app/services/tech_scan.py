"""기술 스캔 — 특허 재검색으로 관련 기업을 찾고 변동을 기록한다.

Phase 1 프로토타입(scripts/tech_to_companies.py)이 검증한 흐름을 서비스로 옮긴 것이다.
앞단(검색·집계·매칭)은 patent_search를 그대로 쓰고, 여기서는 결과를 TechCompany에
병합하고 신규 진입/이탈을 가른다.

**부분 결과를 저장하지 않는다.** 키워드 일부만 성공한 채로 병합하면 나오지 않은 기업이
"이탈"로 잘못 찍힌다. 한도 초과처럼 전체가 불완전해지는 상황에서는 아예 저장하지 않는다.
"""
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Technology, TechCompany
from app.services import api_usage, patent_search, tech_pipeline

logger = logging.getLogger(__name__)


class ScanIncomplete(RuntimeError):
    """전체 검색이 완결되지 않아 저장하지 않았다."""


def get_keywords(tech: Technology) -> list[str]:
    try:
        return [k for k in json.loads(tech.keywords or "[]") if isinstance(k, str)]
    except json.JSONDecodeError:
        return []


async def _search_all(db: Session, keywords: list[str], pages: int) -> list[dict]:
    """모든 키워드를 검색한다. 하나라도 한도로 막히면 전체를 무효로 본다."""
    results = []
    for word in keywords:
        try:
            results.append(await patent_search.search(db, word, pages=pages))
        except api_usage.QuotaExceeded as e:
            # 남은 키워드를 못 돌면 결과가 편향된다 — 부분 저장하지 않는다
            raise ScanIncomplete(f"KIPRIS 한도로 스캔을 중단했습니다: {e}") from e
        except patent_search.PatentSearchError as e:
            # 키워드 하나의 실패는 감수한다. 검색어가 나쁠 수도 있다
            logger.warning("검색 실패, 건너뜀: %r — %s", word, e)
    if not results:
        raise ScanIncomplete("검색 결과가 없습니다.")
    return results


def _merge(db: Session, tech: Technology, matched: dict, now: datetime) -> dict:
    """스캔 결과를 TechCompany에 병합하고 (신규, 유지, 이탈) 수를 낸다."""
    existing = {tc.applicant_name: tc for tc in
                db.query(TechCompany).filter(TechCompany.technology_id == tech.id).all()}

    rows = [("tracked", x) for x in matched["tracked"]] \
        + [("available", x) for x in matched["available"]] \
        + [("excluded", x) for x in matched["excluded"]]

    new_count = 0
    for status, x in rows:
        tc = existing.pop(x["applicant"], None)
        if tc is None:
            tc = TechCompany(technology_id=tech.id, applicant_name=x["applicant"],
                             first_seen_at=now)
            db.add(tc)
            new_count += 1
        tc.status = status
        tc.patent_count = x["patents"]
        tc.jurir_no = x.get("jurir_no")
        tc.corp_code = x.get("corp_code")
        tc.corp_name = x.get("corp_name")
        tc.company_id = x.get("company_id")
        tc.keyword_hits = json.dumps(x.get("keywords", []), ensure_ascii=False)
        tc.exclude_reason = x.get("reason")
        tc.last_seen_at = now

    # 이번 스캔에 안 나온 것들 — 지우지 않는다. last_seen_at으로 이탈을 드러낸다
    dropped = len(existing)
    return {"new": new_count, "kept": len(rows) - new_count, "dropped": dropped}


async def scan(db: Session, tech: Technology, pages: int = 1, top: int = 30,
               onboard: bool = False) -> dict:
    """기술 1건 스캔. onboard=True면 available 상위를 등록하고 분석까지 건다."""
    keywords = get_keywords(tech)
    if not keywords:
        raise ScanIncomplete("검색 키워드가 없습니다. 기술을 먼저 저장하세요.")

    results = await _search_all(db, keywords, pages)
    applicants, kw_hits = patent_search.aggregate_applicants(results)
    matched = patent_search.match_companies(db, applicants, limit=top, keywords=kw_hits)

    now = datetime.utcnow()
    stats = _merge(db, tech, matched, now)
    tech.last_scanned_at = now
    db.commit()

    onboarded = None
    if onboard and matched["available"]:
        onboarded = await tech_pipeline.onboard(db, matched["available"], tech.max_companies)
        # 등록된 기업은 tracked로 승격된다 — 다음 스캔을 기다리지 않고 바로 반영
        _promote(db, tech, onboarded)

    return {
        "technology_id": tech.id,
        "keywords": keywords,
        "searched": [{"word": r["word"], "total": r["total"],
                      "broad": r["total"] > patent_search.BROAD_THRESHOLD} for r in results],
        "applicants": len(applicants),
        "tracked": len(matched["tracked"]),
        "available": len(matched["available"]),
        "excluded": len(matched["excluded"]),
        **stats,
        "onboarded": onboarded,
    }


def _promote(db: Session, tech: Technology, onboarded: dict) -> None:
    """온보딩으로 등록된 기업을 available → tracked로 올린다."""
    names = {r["corp_name"] for r in onboarded.get("registered", [])}
    if not names:
        return
    for tc in db.query(TechCompany).filter(
            TechCompany.technology_id == tech.id,
            TechCompany.status == "available").all():
        if tc.corp_name in names:
            tc.status = "tracked"
    db.commit()
