from datetime import datetime, date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.models import Company
from app.services.dart_client import list_reports
from app.services.report_service import download_and_extract
from app.models import Report

scheduler = AsyncIOScheduler()


async def check_and_download_reports():
    """활성 기업의 사업보고서를 자동 수집.

    조건: DB에 사업보고서가 1건 이상 있는 기업만 대상.
    범위: 기존 최신 사업보고서 연도 이후에 DART에 공시된 신규 사업보고서.
    """
    db = SessionLocal()
    try:
        companies = db.query(Company).filter(Company.is_active == True).all()
        for company in companies:
            try:
                # 기존 사업보고서 목록 조회
                existing_annual = (
                    db.query(Report)
                    .filter(
                        Report.company_id == company.id,
                        Report.report_type == "사업보고서",
                    )
                    .all()
                )

                # 사업보고서가 없으면 스케줄러 대상 아님 (수동 최초 수집 필요)
                if not existing_annual:
                    continue

                max_year = max(r.fiscal_year for r in existing_annual)
                existing_rcepts = {r.rcept_no for r in existing_annual}

                # 최신 연도 이후 공시된 사업보고서만 조회
                bgn_de = f"{max_year + 1}0101"
                dart_reports = await list_reports(company.corp_code, bgn_de=bgn_de)

                for dr in dart_reports:
                    if dr["rcept_no"] in existing_rcepts:
                        continue

                    filing_str = dr.get("filing_date")
                    fiscal_year = int(filing_str[:4]) if filing_str else max_year + 1
                    filing_date = (
                        date(int(filing_str[:4]), int(filing_str[4:6]), int(filing_str[6:8]))
                        if filing_str
                        else None
                    )

                    file_path = await download_and_extract(
                        company.corp_code, dr["rcept_no"], fiscal_year
                    )

                    report = Report(
                        company_id=company.id,
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
            except Exception:
                continue
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        check_and_download_reports,
        trigger=IntervalTrigger(hours=settings.scheduler_interval_hours),
        id="check_reports",
        replace_existing=True,
    )
    scheduler.start()


def shutdown_scheduler():
    scheduler.shutdown(wait=False)
