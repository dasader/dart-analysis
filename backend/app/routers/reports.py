from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Report, Analysis
from app.schemas import ReportResponse, ReportDownloadRequest
from app.services.dart_client import list_reports
from app.services.report_service import download_and_extract, extract_text_from_report

router = APIRouter(tags=["reports"])


@router.get("/api/companies/{company_id}/reports", response_model=list[ReportResponse])
def get_reports(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")

    reports = (
        db.query(Report)
        .filter(Report.company_id == company_id)
        .order_by(Report.fiscal_year.desc())
        .all()
    )
    results = []
    for r in reports:
        count = db.query(func.count(Analysis.id)).filter(Analysis.report_id == r.id).scalar()
        resp = ReportResponse.model_validate(r)
        resp.analysis_count = count
        results.append(resp)
    return results


@router.post("/api/companies/{company_id}/reports/download", response_model=list[ReportResponse])
async def download_reports(
    company_id: int,
    body: ReportDownloadRequest,
    db: Session = Depends(get_db),
):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")

    bgn_de = f"{body.fiscal_year}0101" if body.fiscal_year else None
    end_de = f"{body.fiscal_year + 1}1231" if body.fiscal_year else None

    dart_reports = await list_reports(company.corp_code, bgn_de=bgn_de, end_de=end_de)

    if body.report_type:
        dart_reports = [r for r in dart_reports if r["report_type"] == body.report_type]

    downloaded = []
    for dr in dart_reports:
        existing = db.query(Report).filter_by(
            company_id=company_id, rcept_no=dr["rcept_no"]
        ).first()
        if existing:
            downloaded.append(existing)
            continue

        filing = dr.get("filing_date")
        fiscal_year = int(filing[:4]) if filing else (body.fiscal_year or 2024)

        file_path = await download_and_extract(company.corp_code, dr["rcept_no"], fiscal_year)

        report = Report(
            company_id=company_id,
            rcept_no=dr["rcept_no"],
            report_name=dr["report_name"],
            report_type=dr["report_type"],
            fiscal_year=fiscal_year,
            filing_date=filing,
            file_path=file_path,
            downloaded_at=datetime.utcnow(),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        downloaded.append(report)

    return [ReportResponse.model_validate(r) for r in downloaded]


@router.get("/api/companies/{company_id}/reports/check")
async def check_new_reports(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")

    dart_reports = await list_reports(company.corp_code)
    existing_rcepts = {
        r.rcept_no
        for r in db.query(Report.rcept_no).filter(Report.company_id == company_id).all()
    }

    new_reports = [r for r in dart_reports if r["rcept_no"] not in existing_rcepts]
    return {"new_count": len(new_reports), "reports": new_reports}


@router.get("/api/reports/{report_id}/content")
def get_report_content(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    if not report.file_path:
        raise HTTPException(404, "보고서 파일이 아직 다운로드되지 않았습니다.")

    text = extract_text_from_report(report.file_path)
    return {"report_id": report_id, "content": text[:50000]}
