from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Report, Analysis, Tag
from app.schemas import (
    CompanyCreate, CompanyUpdate, CompanyResponse, CompanySearchResult,
)
from app.services.dart_client import search_companies

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _build_company_response(db: Session, company: Company) -> CompanyResponse:
    report_count = (
        db.query(func.count(Report.id)).filter(Report.company_id == company.id).scalar()
    )
    latest = (
        db.query(func.max(Analysis.updated_at))
        .filter(Analysis.company_id == company.id, Analysis.status == "completed")
        .scalar()
    )
    resp = CompanyResponse.model_validate(company)
    resp.report_count = report_count
    resp.latest_analysis_date = latest
    return resp


@router.get("", response_model=list[CompanyResponse])
def list_companies(tag_ids: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Company).order_by(Company.created_at.desc())
    if tag_ids:
        ids = [int(i) for i in tag_ids.split(",") if i.strip().isdigit()]
        if ids:
            query = query.filter(Company.tags.any(Tag.id.in_(ids)))
    companies = query.all()
    return [_build_company_response(db, c) for c in companies]


@router.get("/search", response_model=list[CompanySearchResult])
async def search(name: str):
    if len(name) < 2:
        raise HTTPException(400, "검색어는 2자 이상 입력하세요.")
    results = await search_companies(name)
    return [CompanySearchResult(**r) for r in results]


@router.post("", response_model=CompanyResponse, status_code=201)
def create_company(body: CompanyCreate, db: Session = Depends(get_db)):
    existing = db.query(Company).filter(Company.corp_code == body.corp_code).first()
    if existing:
        raise HTTPException(409, f"이미 등록된 기업입니다: {existing.corp_name}")
    company = Company(**body.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return _build_company_response(db, company)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(company_id: int, body: CompanyUpdate, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(company, key, val)
    db.commit()
    db.refresh(company)
    return _build_company_response(db, company)


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    db.delete(company)
    db.commit()


@router.post("/{company_id}/tags/{tag_id}", response_model=CompanyResponse)
def assign_tag(company_id: int, tag_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    tag = db.query(Tag).get(tag_id)
    if not tag:
        raise HTTPException(404, "태그를 찾을 수 없습니다.")
    if tag not in company.tags:
        company.tags.append(tag)
        db.commit()
        db.refresh(company)
    return _build_company_response(db, company)


@router.delete("/{company_id}/tags/{tag_id}", response_model=CompanyResponse)
def remove_tag(company_id: int, tag_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    tag = db.query(Tag).get(tag_id)
    if tag and tag in company.tags:
        company.tags.remove(tag)
        db.commit()
        db.refresh(company)
    return _build_company_response(db, company)
