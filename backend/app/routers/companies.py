from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.constants import AnalysisStatus
from app.crud import apply_update, get_or_404, group_agg
from app.database import get_db
from app.models import Company, Report, Analysis, Tag
from app.schemas import (
    CompanyCreate, CompanyUpdate, CompanyResponse, CompanySearchResult,
)
from app.services.dart_client import search_companies

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _aggregates(db: Session, company_ids: list[int]) -> tuple[dict, dict]:
    """기업 id 목록의 (보고서 수, 최근 완료 분석일)을 각각 단일 group_by 쿼리로 집계."""
    report_counts = group_agg(db, func.count(Report.id), Report.company_id, company_ids)
    latest_dates = group_agg(
        db, func.max(Analysis.updated_at), Analysis.company_id, company_ids,
        Analysis.status == AnalysisStatus.COMPLETED,
    )
    return report_counts, latest_dates


def _company_response(
    company: Company, report_count: int, latest: datetime | None
) -> CompanyResponse:
    resp = CompanyResponse.model_validate(company)
    resp.report_count = report_count
    resp.latest_analysis_date = latest
    return resp


def _single_company_response(db: Session, company: Company) -> CompanyResponse:
    """단건 응답용 — 집계를 공용 헬퍼로 조회 (목록 경로와 동일 로직 재사용)."""
    report_counts, latest_dates = _aggregates(db, [company.id])
    return _company_response(
        company, report_counts.get(company.id, 0), latest_dates.get(company.id)
    )


@router.get("", response_model=list[CompanyResponse])
def list_companies(tag_ids: str | None = None, db: Session = Depends(get_db)):
    query = (
        db.query(Company)
        .options(selectinload(Company.tags))  # 태그 eager 로딩 (직렬화 시 N+1 방지)
        .order_by(Company.created_at.desc())
    )
    if tag_ids:
        ids = [int(i) for i in tag_ids.split(",") if i.strip().isdigit()]
        if ids:
            query = query.filter(Company.tags.any(Tag.id.in_(ids)))
    companies = query.all()
    if not companies:
        return []

    report_counts, latest_dates = _aggregates(db, [c.id for c in companies])
    return [
        _company_response(c, report_counts.get(c.id, 0), latest_dates.get(c.id))
        for c in companies
    ]


@router.get("/search", response_model=list[CompanySearchResult])
async def search(name: str):
    if len(name) < 2:
        raise HTTPException(400, "검색어는 2자 이상 입력하세요.")
    results = await search_companies(name)
    return [CompanySearchResult(**r) for r in results]


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = get_or_404(db, Company, company_id, "기업을 찾을 수 없습니다.")
    return _single_company_response(db, company)


@router.post("", response_model=CompanyResponse, status_code=201)
def create_company(body: CompanyCreate, db: Session = Depends(get_db)):
    existing = db.query(Company).filter(Company.corp_code == body.corp_code).first()
    if existing:
        raise HTTPException(409, f"이미 등록된 기업입니다: {existing.corp_name}")
    company = Company(**body.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    # 신규 기업은 보고서·분석이 없으므로 집계 쿼리 없이 0/None
    return _company_response(company, 0, None)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(company_id: int, body: CompanyUpdate, db: Session = Depends(get_db)):
    company = get_or_404(db, Company, company_id, "기업을 찾을 수 없습니다.")
    apply_update(company, body)
    db.commit()
    db.refresh(company)
    return _single_company_response(db, company)


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    company = get_or_404(db, Company, company_id, "기업을 찾을 수 없습니다.")
    db.delete(company)
    db.commit()


@router.post("/{company_id}/tags/{tag_id}", response_model=CompanyResponse)
def assign_tag(company_id: int, tag_id: int, db: Session = Depends(get_db)):
    company = get_or_404(db, Company, company_id, "기업을 찾을 수 없습니다.")
    tag = get_or_404(db, Tag, tag_id, "태그를 찾을 수 없습니다.")
    if tag not in company.tags:
        company.tags.append(tag)
        db.commit()
        db.refresh(company)
    return _single_company_response(db, company)


@router.delete("/{company_id}/tags/{tag_id}", response_model=CompanyResponse)
def remove_tag(company_id: int, tag_id: int, db: Session = Depends(get_db)):
    company = get_or_404(db, Company, company_id, "기업을 찾을 수 없습니다.")
    tag = db.get(Tag, tag_id)
    if tag and tag in company.tags:
        company.tags.remove(tag)
        db.commit()
        db.refresh(company)
    return _single_company_response(db, company)
