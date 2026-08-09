from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.constants import ANALYSIS_TYPES, AnalysisStatus, REPORT_TYPE_ANNUAL
from app.database import SessionLocal
from app.models import Analysis, Company, Report
from app.services.analysis_queue import enqueue
from app.services.batch_poller import poll_batches
from app.services.dart_client import list_reports, parse_filing_date
from app.services.report_service import create_report_from_dart

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
                        Report.report_type == REPORT_TYPE_ANNUAL,
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

                    # 보고서명에 연도가 없으면 공시 연도, 그것도 없으면 max_year+1
                    filing = parse_filing_date(dr.get("filing_date"))
                    fallback_year = filing.year if filing else max_year + 1
                    report = await create_report_from_dart(db, company, dr, fallback_year)
                    if settings.scheduler_auto_analyze:
                        _request_analysis(db, report)
            except Exception:
                continue
    finally:
        db.close()


def _request_analysis(db, report: Report) -> None:
    """신규 수집 보고서의 3종 분석을 pending으로 만들고 큐에 투입."""
    for atype in ANALYSIS_TYPES:
        db.add(Analysis(
            company_id=report.company_id,
            report_id=report.id,
            analysis_type=atype,
            status=AnalysisStatus.PENDING,
        ))
    db.commit()
    enqueue(report.id)


def start_scheduler():
    scheduler.add_job(
        check_and_download_reports,
        trigger=IntervalTrigger(hours=settings.scheduler_interval_hours),
        id="check_reports",
        replace_existing=True,
    )
    scheduler.add_job(
        poll_batches,
        trigger=IntervalTrigger(seconds=settings.batch_poll_interval_secs),
        id="poll_batches",
        replace_existing=True,
    )
    scheduler.start()


def shutdown_scheduler():
    scheduler.shutdown(wait=False)
