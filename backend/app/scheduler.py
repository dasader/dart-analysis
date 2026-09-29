import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.constants import REPORT_TYPE_ANNUAL
from app.database import SessionLocal
from app.models import Company, Report, Technology
from app.services import app_settings
from app.services.analysis_queue import queue_report
from app.services.batch_poller import poll_batches
from app.services import tech_scan
from app.services.dart_client import list_reports, parse_filing_date
from app.services.report_service import create_report_from_dart

logger = logging.getLogger(__name__)

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
                    if app_settings.get(db, "scheduler_auto_analyze"):
                        queue_report(db, report)
            except Exception:
                logger.exception("보고서 자동 수집 실패: %s", company.corp_name)
    finally:
        db.close()


async def scan_technologies():
    """활성 기술의 특허를 재검색해 새 기업을 찾는다.

    발견된 기업을 Company에 등록하기만 하면 보고서 수집·분석은 기존 스케줄러가
    이어받는다 — 여기서 온보딩까지 하지 않는 이유다(비용이 나가는 쪽은 그쪽 토글이 잠근다).
    """
    db = SessionLocal()
    try:
        if not app_settings.get(db, "tech_scan_enabled"):
            return
        techs = db.query(Technology).filter(Technology.is_active == True).all()
        for tech in techs:
            try:
                stats = await tech_scan.scan(db, tech, onboard=False)
                logger.info("기술 스캔 완료: %s — 신규 %d / 이탈 %d",
                            tech.name, stats["new"], stats["dropped"])
            except tech_scan.ScanIncomplete as e:
                logger.warning("기술 스캔 중단: %s — %s", tech.name, e)
                break            # 한도 문제면 남은 기술도 마찬가지다
            except Exception:
                logger.exception("기술 스캔 실패: %s", tech.name)
    finally:
        db.close()


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
    scheduler.add_job(
        scan_technologies,
        trigger=IntervalTrigger(days=settings.tech_scan_interval_days),
        id="scan_technologies",
        replace_existing=True,
    )
    scheduler.start()


def shutdown_scheduler():
    scheduler.shutdown(wait=False)
