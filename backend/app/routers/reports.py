import re
import urllib.parse
from datetime import datetime, date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Report, Analysis
from app.schemas import ReportResponse, ReportDownloadRequest
from app.services.dart_client import list_reports, extract_fiscal_year_from_name
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

    # 보고서명에서 사업연도 파싱 후 선택 연도와 일치하는 것만 수집
    if body.fiscal_year:
        dart_reports = [
            r for r in dart_reports
            if extract_fiscal_year_from_name(r["report_name"]) == body.fiscal_year
        ]

    downloaded = []
    for dr in dart_reports:
        existing = db.query(Report).filter_by(
            company_id=company_id, rcept_no=dr["rcept_no"]
        ).first()
        if existing:
            # 이전 버그로 잘못 저장된 fiscal_year를 보고서명 기준으로 교정
            parsed_year = extract_fiscal_year_from_name(dr["report_name"])
            if parsed_year and existing.fiscal_year != parsed_year:
                existing.fiscal_year = parsed_year
                db.commit()
                db.refresh(existing)
            downloaded.append(existing)
            continue

        filing_str = dr.get("filing_date")
        # 보고서명에서 사업연도 추출, 없으면 선택 연도 사용
        fiscal_year = extract_fiscal_year_from_name(dr["report_name"]) or body.fiscal_year or 2024
        filing_date = (
            date(int(filing_str[:4]), int(filing_str[4:6]), int(filing_str[6:8]))
            if filing_str
            else None
        )

        file_path = await download_and_extract(company.corp_code, dr["rcept_no"], fiscal_year)

        report = Report(
            company_id=company_id,
            rcept_no=dr["rcept_no"],
            report_name=dr["report_name"],
            report_type=dr["report_type"],
            fiscal_year=fiscal_year,
            filing_date=filing_date,
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


@router.delete("/api/reports/{report_id}", status_code=204)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    db.delete(report)
    db.commit()


@router.post("/api/reports/{report_id}/redownload", response_model=ReportResponse)
async def redownload_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")

    # 파일이 바뀌므로 기존 분석 결과 삭제
    db.query(Analysis).filter(Analysis.report_id == report_id).delete()

    file_path = await download_and_extract(
        report.company.corp_code, report.rcept_no, report.fiscal_year
    )
    report.file_path = file_path
    report.downloaded_at = datetime.utcnow()
    db.commit()
    db.refresh(report)

    resp = ReportResponse.model_validate(report)
    resp.analysis_count = 0
    return resp


@router.get("/api/reports/{report_id}/download")
def download_report_zip(report_id: int, db: Session = Depends(get_db)):
    """저장된 보고서 ZIP 파일을 다운로드. 파일명: 회사명_연도_보고서유형.zip"""
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    if not report.file_path:
        raise HTTPException(404, "보고서 파일이 아직 다운로드되지 않았습니다.")

    zip_path = Path(report.file_path) / f"{report.rcept_no}.zip"
    if not zip_path.exists():
        raise HTTPException(404, "ZIP 파일을 찾을 수 없습니다.")

    corp_name = report.company.corp_name
    raw_name = f"{corp_name}_{report.fiscal_year}_{report.report_type}.zip"
    # 파일명에 사용 불가한 문자 제거
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", raw_name)
    encoded_name = urllib.parse.quote(safe_name, encoding="utf-8")

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
        },
    )


@router.get("/api/reports/{report_id}/content")
def get_report_content(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    if not report.file_path:
        raise HTTPException(404, "보고서 파일이 아직 다운로드되지 않았습니다.")

    text = extract_text_from_report(report.file_path)
    return {"report_id": report_id, "content": text[:50000]}
