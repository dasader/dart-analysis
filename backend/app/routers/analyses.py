from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, defer

from app.constants import ANALYSIS_TYPES
from app.crud import get_or_404
from app.database import get_db
from app.models import Company, Report, Analysis
from app.schemas import AnalysisRequest, AnalysisResponse, QueueStatus
from app.services import analysis_service as svc
from app.services.analysis_queue import enqueue, get_queue_info, queue_report
from app.dependencies import require_admin

router = APIRouter(tags=["analyses"])


def _downloaded_report(db: Session, report_id: int) -> Report:
    """분석할 보고서. 없으면 404, 파일을 아직 못 받았으면 400."""
    report = get_or_404(db, Report, report_id, "보고서를 찾을 수 없습니다.")
    if not report.file_path:
        raise HTTPException(400, "보고서 파일이 아직 다운로드되지 않았습니다.")
    return report


@router.post("/api/reports/{report_id}/analyze", response_model=AnalysisResponse, dependencies=[Depends(require_admin)])
def analyze_report(
    report_id: int,
    body: AnalysisRequest,
    db: Session = Depends(get_db),
):
    """특정 분석 유형 1개를 요청. 큐에 report_id를 투입해 combined worker가 처리."""
    report = _downloaded_report(db, report_id)

    q = db.query(Analysis).filter_by(report_id=report.id, analysis_type=body.analysis_type)
    existing = q.first()
    svc.mark_pending(db, report, {body.analysis_type: existing} if existing else {},
                     [body.analysis_type], skip_completed=False)
    db.commit()
    enqueue(report.id)  # report_id 기반 큐 — worker가 pending 항목 일괄 처리
    return AnalysisResponse.model_validate(q.one())


@router.post("/api/reports/{report_id}/analyze-all", dependencies=[Depends(require_admin)])
def analyze_report_all(report_id: int, db: Session = Depends(get_db)):
    """보고서의 모든 분석 유형(3종)을 pending으로 설정하고 report_id를 큐에 1회 투입."""
    report = _downloaded_report(db, report_id)

    queue_report(db, report, skip_completed=False)
    return {
        "message": f"{len(ANALYSIS_TYPES)}가지 분석이 큐에 추가되었습니다. (Gemini 1회 호출)",
        "queued": len(ANALYSIS_TYPES),
    }


@router.post("/api/companies/{company_id}/analyze-all", dependencies=[Depends(require_admin)])
def analyze_all(company_id: int, db: Session = Depends(get_db)):
    """기업의 모든 보고서 × 3가지 유형을 일괄 요청. 보고서별로 1회씩 큐 투입."""
    company = get_or_404(db, Company, company_id, "기업을 찾을 수 없습니다.")

    reports = db.query(Report).filter(
        Report.company_id == company.id,
        Report.file_path.isnot(None),
    ).all()

    # 기업의 모든 분석을 1회 로드(대용량 결과 컬럼은 defer) → report_id별 dict로 N+1 제거
    by_report: dict[int, dict] = defaultdict(dict)
    for a in (
        db.query(Analysis)
        .filter_by(company_id=company.id)
        .options(defer(Analysis.result_json), defer(Analysis.result_summary))
        .all()
    ):
        by_report[a.report_id][a.analysis_type] = a

    report_ids_to_queue = [
        report.id
        for report in reports
        if svc.mark_pending(db, report, by_report.get(report.id, {}))
    ]

    db.commit()  # 워커가 미커밋 상태를 읽지 않도록 enqueue 전에 커밋
    for rid in report_ids_to_queue:
        enqueue(rid)

    return {
        "message": f"{len(report_ids_to_queue)}개 보고서 분석이 큐에 추가되었습니다. (보고서당 Gemini 1회 호출)",
        "queued": len(report_ids_to_queue),
    }


@router.get("/api/reports/{report_id}/analyses", response_model=list[AnalysisResponse])
def get_report_analyses(report_id: int, db: Session = Depends(get_db)):
    analyses = db.query(Analysis).filter(Analysis.report_id == report_id).all()
    return [AnalysisResponse.model_validate(a) for a in analyses]


@router.get("/api/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = get_or_404(db, Analysis, analysis_id, "분석 결과를 찾을 수 없습니다.")
    return AnalysisResponse.model_validate(analysis)


@router.get("/api/companies/{company_id}/analyses", response_model=list[AnalysisResponse])
def get_company_analyses(company_id: int, db: Session = Depends(get_db)):
    analyses = (
        db.query(Analysis)
        .filter(Analysis.company_id == company_id)
        .order_by(Analysis.report_id.desc(), Analysis.analysis_type)
        .all()
    )
    return [AnalysisResponse.model_validate(a) for a in analyses]


@router.get("/api/queue/status", response_model=QueueStatus)
def queue_status():
    return get_queue_info()
