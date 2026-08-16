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

from app.models import Report, Technology, TechCompany
from app.services import api_usage, patent_search, tech_pipeline

logger = logging.getLogger(__name__)


class ScanIncomplete(RuntimeError):
    """전체 검색이 완결되지 않아 저장하지 않았다."""


# 키워드당 받아 올 페이지 수(100건/페이지). 1페이지는 기업을 통째로 놓친다 —
# 실측: '황화물계 고체전해질' 상위 100건에 LG화학 0건, 101~300위에 15건.
# 출원인도 27명 → 61명으로 늘었다. 대신 KIPRIS 월 1,000회를 2배로 쓴다
# (키워드 4개 기준 기술 125건까지 월 1회 스캔 가능).
PAGES = 2


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


async def scan(db: Session, tech: Technology, pages: int = PAGES, top: int | None = None,
               onboard: bool = False) -> dict:
    """기술 1건 스캔. onboard=True면 available 상위를 등록하고 분석까지 건다."""
    keywords = get_keywords(tech)
    if not keywords:
        raise ScanIncomplete("검색 키워드가 없습니다. 기술을 먼저 저장하세요.")

    results = await _search_all(db, keywords, pages)
    applicants, kw_hits = patent_search.aggregate_applicants(results)
    matched = patent_search.match_companies(db, applicants, limit=top, keywords=kw_hits)

    searched = [{"word": r["word"], "total": r["total"],
                 "broad": r["total"] > patent_search.BROAD_THRESHOLD} for r in results]

    now = datetime.utcnow()
    stats = _merge(db, tech, matched, now)
    tech.last_scanned_at = now
    tech.keyword_stats = json.dumps(searched, ensure_ascii=False)
    db.commit()

    onboarded = None
    if onboard:
        targets = _onboard_targets(db, matched)
        if targets:
            onboarded = await tech_pipeline.onboard(db, targets, tech.max_companies)
            # 등록된 기업은 tracked로 승격된다 — 다음 스캔을 기다리지 않고 바로 반영
            _promote(db, tech, onboarded)

    return {
        "technology_id": tech.id,
        "keywords": keywords,
        "searched": searched,
        "applicants": len(applicants),
        "tracked": len(matched["tracked"]),
        "available": len(matched["available"]),
        "excluded": len(matched["excluded"]),
        **stats,
        "onboarded": onboarded,
    }


def _tracked_without_report(db: Session, tracked: list[dict]) -> list[dict]:
    """이미 등록됐지만 사업보고서가 없는 기업.

    `onboard`는 corp_code로 기업을 찾으므로 available과 같은 모양이면 그대로 태울 수 있다.
    """
    have = {cid for (cid,) in db.query(Report.company_id)
            .filter(Report.file_path.isnot(None)).distinct().all()}
    return [x for x in tracked if x.get("company_id") and x["company_id"] not in have]


def _onboard_targets(db: Session, matched: dict) -> list[dict]:
    """온보딩 대상 — 미등록 기업 + **등록됐지만 보고서가 없는 기업**.

    available만 태우면 이미 등록된 기업이 영영 빠진다. LG에너지솔루션(전고체 특허
    16건)이 등록만 돼 있고 보고서가 0건이라, 종합 보고서에서 "사업보고서에 언급 없음"
    으로 잘못 읽혔다 — 전업 배터리 회사가 그 기술을 안 하는 것처럼 보였다.

    `onboard`는 앞에서부터 max_companies개를 자르므로 **순서가 곧 우선순위다.**
    그냥 이어붙이면 특허 3건짜리 미등록 기업이 16건짜리 기존 기업보다 먼저 간다.
    """
    targets = matched["available"] + _tracked_without_report(db, matched["tracked"])
    return sorted(targets, key=lambda x: -x["patents"])


def _promote(db: Session, tech: Technology, onboarded: dict) -> None:
    """온보딩으로 등록된 기업을 available → tracked로 올리고 **company_id를 채운다.**

    company_id를 빠뜨리면 status만 tracked가 되어 겉보기엔 멀쩡한데,
    화면에서 기업 상세로 가는 링크가 생기지 않고 종합 보고서도 그 기업의
    사업보고서 분석을 찾지 못한다(실측으로 겪었다 — 3사가 조용히 누락됐다).
    """
    by_name = {r["corp_name"]: r["company_id"] for r in onboarded.get("registered", [])}
    if not by_name:
        return
    for tc in db.query(TechCompany).filter(
            TechCompany.technology_id == tech.id,
            TechCompany.status == "available").all():
        # 여기서 비교하는 corp_name은 양쪽 다 DART 표기다(특허 출원인명이 아니다)
        if tc.corp_name in by_name:
            tc.status = "tracked"
            tc.company_id = by_name[tc.corp_name]
    db.commit()
