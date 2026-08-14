"""기술 설명 → 특허 → 기업 → 보고서 → 분석까지 잇는 파이프라인.

앞단(특허·매칭)은 신규지만 뒷단은 기존 서비스를 그대로 쓴다.
기업 등록·보고서 수집·분석 큐는 이미 있는 것을 부르기만 한다.

**비용이 기업 수만큼 곱해진다.** 보고서 1건당 약 $0.0135이므로 상한 없이 돌리면
기술 하나에 수십 건이 나간다. 호출부가 반드시 상한을 정하게 한다.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.constants import ANALYSIS_TYPES, REPORT_TYPE_ANNUAL, AnalysisStatus
from app.models import Analysis, Company, DartCorp, Report
from app.services.analysis_queue import enqueue
from app.services.dart_client import list_reports
from app.services.report_service import create_report_from_dart

logger = logging.getLogger(__name__)


def register_company(db: Session, corp_code: str) -> Company | None:
    """DART 색인에 있는 기업을 추적 대상으로 올린다. 이미 있으면 그대로 돌려준다."""
    existing = db.query(Company).filter(Company.corp_code == corp_code).first()
    if existing:
        return existing

    indexed = db.get(DartCorp, corp_code)
    if indexed is None:
        logger.warning("DART 색인에 없는 corp_code: %s", corp_code)
        return None

    company = Company(corp_code=indexed.corp_code, corp_name=indexed.corp_name,
                      stock_code=indexed.stock_code, jurir_no=indexed.jurir_no)
    db.add(company)
    db.commit()
    db.refresh(company)
    logger.info("기업 등록: %s (%s)", company.corp_name, corp_code)
    return company


async def ensure_latest_report(db: Session, company: Company, year: int | None = None) -> Report | None:
    """기업의 최신 사업보고서를 확보한다. 이미 있으면 그것을 쓴다(재다운로드하지 않는다)."""
    have = (db.query(Report)
            .filter(Report.company_id == company.id,
                    Report.report_type == REPORT_TYPE_ANNUAL,
                    Report.file_path.isnot(None))
            .order_by(Report.fiscal_year.desc())
            .first())
    if have and (year is None or have.fiscal_year == year):
        return have

    target = year or datetime.utcnow().year - 1
    dart_reports = await list_reports(company.corp_code,
                                      bgn_de=f"{target}0101", end_de=f"{target + 1}1231")
    if not dart_reports:
        logger.info("사업보고서 없음: %s (%d년)", company.corp_name, target)
        return have

    try:
        return await create_report_from_dart(db, company, dart_reports[0], target)
    except Exception:
        logger.exception("보고서 수집 실패: %s", company.corp_name)
        return have


def queue_analysis(db: Session, report: Report) -> int:
    """보고서의 미완료 분석을 pending으로 만들고 큐에 넣는다. 새로 잡힌 유형 수를 반환."""
    existing = {a.analysis_type: a for a in
                db.query(Analysis).filter(Analysis.report_id == report.id).all()}
    queued = 0
    for atype in ANALYSIS_TYPES:
        a = existing.get(atype)
        if a and a.status == AnalysisStatus.COMPLETED:
            continue        # 이미 분석된 건 다시 돌리지 않는다 — 비용이 곱해진다
        if a:
            a.status = AnalysisStatus.PENDING
            a.error_message = None
        else:
            db.add(Analysis(company_id=report.company_id, report_id=report.id,
                            analysis_type=atype, status=AnalysisStatus.PENDING))
        queued += 1
    if queued:
        db.commit()
        enqueue(report.id)
    return queued


async def onboard(db: Session, candidates: list[dict], max_companies: int,
                  year: int | None = None) -> dict:
    """미등록 후보를 등록하고 보고서를 확보한 뒤 분석 큐에 넣는다.

    candidates는 match_companies의 `available` 목록(특허 건수 내림차순).
    max_companies로 반드시 상한을 둔다 — 비용이 기업 수만큼 곱해진다.
    """
    picked = candidates[:max_companies]
    registered, with_report, queued_reports, failed = [], [], 0, []

    for cand in picked:
        company = register_company(db, cand["corp_code"])
        if company is None:
            failed.append({**cand, "reason": "색인 조회 실패"})
            continue
        registered.append(company)

        report = await ensure_latest_report(db, company, year)
        if report is None:
            failed.append({**cand, "reason": "사업보고서 없음"})
            continue
        with_report.append((company, report))

        if queue_analysis(db, report):
            queued_reports += 1

    return {
        "registered": [{"company_id": c.id, "corp_name": c.corp_name} for c in registered],
        "reports": [{"company": c.corp_name, "report_id": r.id,
                     "fiscal_year": r.fiscal_year} for c, r in with_report],
        "queued_reports": queued_reports,
        "failed": failed,
    }
