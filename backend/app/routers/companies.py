from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.constants import AnalysisStatus
from app.crud import get_or_404
from app.database import get_db
from app.models import Company, Report, Analysis, Tag
from app.schemas import (
    CompanyCreate, CompanyUpdate, CompanyResponse, CompanySearchResult,
)
from app.services.dart_client import search_companies

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _company_response(
    company: Company, report_count: int, latest: datetime | None
) -> CompanyResponse:
    resp = CompanyResponse.model_validate(company)
    resp.report_count = report_count
    resp.latest_analysis_date = latest
    return resp


def _single_company_response(db: Session, company: Company) -> CompanyResponse:
    """단건 응답용 — 보고서 수·최근 분석일을 개별 조회."""
    report_count = (
        db.query(func.count(Report.id)).filter(Report.company_id == company.id).scalar()
    )
    latest = (
        db.query(func.max(Analysis.updated_at))
        .filter(Analysis.company_id == company.id, Analysis.status == AnalysisStatus.COMPLETED)
        .scalar()
    )
    return _company_response(company, report_count or 0, latest)


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

    # 보고서 수·최근 분석일을 각각 단일 group_by 쿼리로 집계 (기업당 2쿼리 N+1 제거)
    company_ids = [c.id for c in companies]
    report_counts = dict(
        db.query(Report.company_id, func.count(Report.id))
        .filter(Report.company_id.in_(company_ids))
        .group_by(Report.company_id)
        .all()
    )
    latest_dates = dict(
        db.query(Analysis.company_id, func.max(Analysis.updated_at))
        .filter(
            Analysis.company_id.in_(company_ids),
            Analysis.status == AnalysisStatus.COMPLETED,
        )
        .group_by(Analysis.company_id)
        .all()
    )
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
    return _single_company_response(db, company)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(company_id: int, body: CompanyUpdate, db: Session = Depends(get_db)):
    company = get_or_404(db, Company, company_id, "기업을 찾을 수 없습니다.")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(company, key, val)
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
