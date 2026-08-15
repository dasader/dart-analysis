import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.crud import get_or_404
from app.database import get_db
from app.dependencies import require_admin
from app.models import Technology, TechCompany
from app.schemas import (
    TechCompanyResponse, TechnologyCreate, TechnologyDetail,
    TechnologyResponse, TechnologyUpdate,
)
from app.services import api_usage, keyword_extract, tech_scan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/technologies", tags=["technologies"])


def _counts(tech: Technology) -> dict:
    c = {"tracked": 0, "available": 0, "excluded": 0}
    for tc in tech.companies:
        if tc.status in c:
            c[tc.status] += 1
    return c


def _to_response(tech: Technology) -> TechnologyResponse:
    c = _counts(tech)
    return TechnologyResponse(
        id=tech.id, name=tech.name, description=tech.description,
        keywords=tech_scan.get_keywords(tech), max_companies=tech.max_companies,
        is_active=tech.is_active, last_scanned_at=tech.last_scanned_at,
        created_at=tech.created_at,
        tracked_count=c["tracked"], available_count=c["available"],
        excluded_count=c["excluded"],
    )


def _company_response(tc: TechCompany, scanned_at) -> TechCompanyResponse:
    # 마지막 스캔 시각과 비교해 신규/이탈을 가른다
    is_new = bool(scanned_at and tc.first_seen_at and tc.first_seen_at >= scanned_at)
    is_gone = bool(scanned_at and tc.last_seen_at and tc.last_seen_at < scanned_at)
    try:
        hits = json.loads(tc.keyword_hits or "[]")
    except json.JSONDecodeError:
        hits = []
    return TechCompanyResponse(
        id=tc.id, company_id=tc.company_id, corp_code=tc.corp_code,
        corp_name=tc.corp_name, applicant_name=tc.applicant_name,
        patent_count=tc.patent_count, keyword_hits=hits, status=tc.status,
        exclude_reason=tc.exclude_reason, first_seen_at=tc.first_seen_at,
        last_seen_at=tc.last_seen_at, is_new=is_new, is_gone=is_gone,
    )


@router.get("", response_model=list[TechnologyResponse])
def list_technologies(db: Session = Depends(get_db)):
    techs = (db.query(Technology)
             .options(selectinload(Technology.companies))
             .order_by(Technology.id.desc()).all())
    return [_to_response(t) for t in techs]


@router.get("/{tech_id}", response_model=TechnologyDetail)
def get_technology(tech_id: int, db: Session = Depends(get_db)):
    tech = get_or_404(db, Technology, tech_id, "기술을 찾을 수 없습니다.")
    base = _to_response(tech)
    # 특허 많은 순, 같으면 추적 중인 것부터
    order = {"tracked": 0, "available": 1, "excluded": 2}
    rows = sorted(tech.companies,
                  key=lambda tc: (order.get(tc.status, 9), -tc.patent_count))
    return TechnologyDetail(
        **base.model_dump(),
        companies=[_company_response(tc, tech.last_scanned_at) for tc in rows],
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
        data["keywords"] = json.dumps(data["keywords"], ensure_ascii=False)
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


@router.get("/{tech_id}/keywords/suggest", dependencies=[Depends(require_admin)])
async def suggest_keywords(tech_id: int, db: Session = Depends(get_db)):
    """설명문으로 검색어를 다시 뽑는다. 저장하지 않고 제안만 한다."""
    tech = get_or_404(db, Technology, tech_id, "기술을 찾을 수 없습니다.")
    try:
        return {"keywords": await keyword_extract.extract(tech.description)}
    except Exception as e:
        raise HTTPException(400, f"검색어를 만들지 못했습니다: {e}") from e
