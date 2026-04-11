from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Report, Analysis
from app.schemas import (
    CompanyCreate, CompanyUpdate, CompanyResponse, CompanySearchResult,
)
from app.services.dart_client import search_companies

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=list[CompanyResponse])
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.created_at.desc()).all()
    results = []
    for c in companies:
        report_count = db.query(func.count(Report.id)).filter(Report.company_id == c.id).scalar()
        latest = (
            db.query(func.max(Analysis.updated_at))
            .filter(Analysis.company_id == c.id)
            .scalar()
        )
        resp = CompanyResponse.model_validate(c)
        resp.report_count = report_count
        resp.latest_analysis_date = latest
        results.append(resp)
    return results


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
    return CompanyResponse.model_validate(company)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(company_id: int, body: CompanyUpdate, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(company, key, val)
    db.commit()
    db.refresh(company)
    return CompanyResponse.model_validate(company)


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    db.delete(company)
    db.commit()
