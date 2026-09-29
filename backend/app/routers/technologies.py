import json
import logging
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, defer

from app.crud import get_or_404
from app.constants import TechStatus
from app.database import get_db
from app.dependencies import require_admin
from app.models import Technology, TechCompany
from app.schemas import (
    TechCompanyResponse, TechnologyCreate, TechnologyDetail,
    TechnologyResponse, TechnologyUpdate,
)
from app.services import api_usage, keyword_extract, tech_report, tech_scan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/technologies", tags=["technologies"])


def _counts(tech: Technology) -> Counter:
    return Counter(tc.status for tc in tech.companies)


def _keyword_stats(tech: Technology) -> list[dict]:
    return [r for r in tech_scan.json_list(tech.keyword_stats, dict) if "word" in r]


def _to_response(tech: Technology, counts: Counter | None = None) -> TechnologyResponse:
    c = counts if counts is not None else _counts(tech)
    return TechnologyResponse(
        id=tech.id, name=tech.name, description=tech.description,
        keywords=tech_scan.get_keywords(tech), keyword_stats=_keyword_stats(tech),
        ipc_core=tech_scan.get_ipc_core(tech),
        max_companies=tech.max_companies,
        is_active=tech.is_active, last_scanned_at=tech.last_scanned_at,
        created_at=tech.created_at,
        tracked_count=c[TechStatus.TRACKED], available_count=c[TechStatus.AVAILABLE],
        excluded_count=c[TechStatus.EXCLUDED],
    )


def _company_response(tc: TechCompany, scanned_at) -> TechCompanyResponse:
    # 마지막 스캔 시각과 비교해 신규/이탈을 가른다
    is_new = bool(scanned_at and tc.first_seen_at and tc.first_seen_at >= scanned_at)
    is_gone = bool(scanned_at and tc.last_seen_at and tc.last_seen_at < scanned_at)
    hits = tech_scan.json_list(tc.keyword_hits)
    return TechCompanyResponse(
        id=tc.id, company_id=tc.company_id, corp_code=tc.corp_code,
        corp_name=tc.corp_name, applicant_name=tc.applicant_name,
        patent_count=tc.patent_count, keyword_hits=hits, status=tc.status,
        exclude_reason=tc.exclude_reason, first_seen_at=tc.first_seen_at,
        last_seen_at=tc.last_seen_at, is_new=is_new, is_gone=is_gone,
    )


@router.get("", response_model=list[TechnologyResponse])
def list_technologies(db: Session = Depends(get_db)):
    # 목록은 개수만 필요하다 — 기업 행 수백 개와 보고서 본문을 싣지 않고 집계 한 번으로
    techs = (db.query(Technology).options(defer(Technology.report_md))
             .order_by(Technology.id.desc()).all())
    counts: dict[int, Counter] = defaultdict(Counter)
    for tid, status, n in (db.query(TechCompany.technology_id, TechCompany.status, func.count())
                           .group_by(TechCompany.technology_id, TechCompany.status)):
        counts[tid][status] = n
    return [_to_response(t, counts[t.id]) for t in techs]


@router.get("/{tech_id}", response_model=TechnologyDetail)
def get_technology(tech_id: int, db: Session = Depends(get_db)):
    tech = get_or_404(db, Technology, tech_id, "기술을 찾을 수 없습니다.")
    base = _to_response(tech)
    # 추적 중 → 등록 가능 → 산업 밖, 그 안에서 특허 많은 순
    order = {s: i for i, s in enumerate(TechStatus)}
    rows = sorted(tech.companies,
                  key=lambda tc: (order.get(tc.status, 9), -tc.patent_count))
    return TechnologyDetail(
        **base.model_dump(),
        companies=[_company_response(tc, tech.last_scanned_at) for tc in rows],
        report_md=tech.report_md,
        report_generated_at=tech.report_generated_at,
        report_basis=tech.report_basis,
    )


@router.post("", response_model=TechnologyResponse, status_code=201,
             dependencies=[Depends(require_admin)])
async def create_technology(body: TechnologyCreate, db: Session = Depends(get_db)):
    if db.query(Technology).filter(Technology.name == body.name).first():
        raise HTTPException(409, f"이미 등록된 기술입니다: {body.name}")

    keywords = body.keywords
    if not keywords:
        try:
            keywords = await keyword_extract.extract(body.description)
        except Exception as e:
            raise HTTPException(400, f"검색어를 만들지 못했습니다: {e}") from e

    tech = Technology(name=body.name, description=body.description,
                      keywords=json.dumps(keywords, ensure_ascii=False),
                      max_companies=body.max_companies)
    db.add(tech)
    db.commit()
    db.refresh(tech)
    return _to_response(tech)


@router.put("/{tech_id}", response_model=TechnologyResponse,
            dependencies=[Depends(require_admin)])
def update_technology(tech_id: int, body: TechnologyUpdate, db: Session = Depends(get_db)):
    tech = get_or_404(db, Technology, tech_id, "기술을 찾을 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    if "keywords" in data and data["keywords"] is not None:
        new = json.dumps(data["keywords"], ensure_ascii=False)
        if new != tech.keywords:
            # 코어는 키워드가 정한다 — 다음 스캔이 제한 없이 검색해 다시 잡는다
            tech.ipc_core = None
        data["keywords"] = new
    for k, v in data.items():
        setattr(tech, k, v)
    db.commit()
    db.refresh(tech)
    return _to_response(tech)


@router.delete("/{tech_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_technology(tech_id: int, db: Session = Depends(get_db)):
    tech = get_or_404(db, Technology, tech_id, "기술을 찾을 수 없습니다.")
    db.delete(tech)
    db.commit()


@router.post("/{tech_id}/scan", dependencies=[Depends(require_admin)])
async def scan_technology(tech_id: int, onboard: bool = False,
                          db: Session = Depends(get_db)):
    """수동 스캔. onboard=true면 미등록 기업을 등록하고 분석까지 건다(비용 발생)."""
    tech = get_or_404(db, Technology, tech_id, "기술을 찾을 수 없습니다.")
    try:
        return await tech_scan.scan(db, tech, onboard=onboard)
    except tech_scan.ScanIncomplete as e:
        raise HTTPException(409, str(e)) from e


@router.post("/{tech_id}/report", dependencies=[Depends(require_admin)])
async def generate_report(tech_id: int, db: Session = Depends(get_db)):
    """기술 종합 보고서 생성. 특허를 다시 검색하므로 KIPRIS 한도를 쓴다(키워드 수만큼)."""
    tech = get_or_404(db, Technology, tech_id, "기술을 찾을 수 없습니다.")
    try:
        md = await tech_report.generate(db, tech)
    except api_usage.QuotaExceeded as e:
        raise HTTPException(429, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"report_md": md, "report_generated_at": tech.report_generated_at,
            "report_basis": tech.report_basis}


@router.get("/{tech_id}/keywords/suggest", dependencies=[Depends(require_admin)])
async def suggest_keywords(tech_id: int, db: Session = Depends(get_db)):
    """설명문으로 검색어를 다시 뽑는다. 저장하지 않고 제안만 한다."""
    tech = get_or_404(db, Technology, tech_id, "기술을 찾을 수 없습니다.")
    try:
        return {"keywords": await keyword_extract.extract(tech.description)}
    except Exception as e:
        raise HTTPException(400, f"검색어를 만들지 못했습니다: {e}") from e
