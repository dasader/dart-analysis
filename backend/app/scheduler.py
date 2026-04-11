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
    """등록된 모든 활성 기업의 새 보고서를 체크하고 다운로드."""
    db = SessionLocal()
    try:
        companies = db.query(Company).filter(Company.is_active == True).all()
        for company in companies:
            try:
                dart_reports = await list_reports(company.corp_code)
                existing_rcepts = {
                    r.rcept_no
                    for r in db.query(Report.rcept_no).filter(
                        Report.company_id == company.id
                    ).all()
                }

                for dr in dart_reports:
                    if dr["rcept_no"] in existing_rcepts:
                        continue

                    filing = dr.get("filing_date")
                    fiscal_year = int(filing[:4]) if filing else 2024

                    file_path = await download_and_extract(
                        company.corp_code, dr["rcept_no"], fiscal_year
                    )

                    from datetime import datetime
                    report = Report(
                        company_id=company.id,
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
