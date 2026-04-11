from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Report, Analysis
from app.schemas import AnalysisRequest, AnalysisResponse, QueueStatus
from app.services.analysis_queue import enqueue, get_queue_info

VALID_TYPES = ("subsidiary", "rnd", "national_tech")

router = APIRouter(tags=["analyses"])


def _get_or_create_analysis(
    db: Session, company_id: int, report_id: int, analysis_type: str
) -> Analysis:
    """분석 레코드를 가져오거나 새로 생성. 실패/완료 상태면 pending으로 리셋."""
    existing = db.query(Analysis).filter_by(
        company_id=company_id,
        report_id=report_id,
        analysis_type=analysis_type,
    ).first()

    if existing:
        existing.status = "pending"
        existing.error_message = None
        db.commit()
        db.refresh(existing)
        return existing

    analysis = Analysis(
        company_id=company_id,
        report_id=report_id,
        analysis_type=analysis_type,
        status="pending",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


@router.post("/api/reports/{report_id}/analyze", response_model=AnalysisResponse)
def analyze_report(
    report_id: int,
    body: AnalysisRequest,
    db: Session = Depends(get_db),
):
    """특정 분석 유형 1개를 요청. 큐에 report_id를 투입해 combined worker가 처리."""
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    if not report.file_path:
        raise HTTPException(400, "보고서 파일이 아직 다운로드되지 않았습니다.")
    if body.analysis_type not in VALID_TYPES:
        raise HTTPException(400, f"지원하지 않는 분석 유형: {body.analysis_type}")

    analysis = _get_or_create_analysis(
        db, report.company_id, report.id, body.analysis_type
    )
    enqueue(report.id)  # report_id 기반 큐 — worker가 pending 항목 일괄 처리
    return AnalysisResponse.model_validate(analysis)


@router.post("/api/reports/{report_id}/analyze-all")
def analyze_report_all(report_id: int, db: Session = Depends(get_db)):
    """보고서의 모든 분석 유형(3종)을 pending으로 설정하고 report_id를 큐에 1회 투입."""
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    if not report.file_path:
        raise HTTPException(400, "보고서 파일이 아직 다운로드되지 않았습니다.")

    for atype in VALID_TYPES:
        _get_or_create_analysis(db, report.company_id, report.id, atype)

    enqueue(report.id)  # 중복 투입은 enqueue 내부에서 무시
    return {"message": "3가지 분석이 큐에 추가되었습니다. (Gemini 1회 호출)", "queued": 3}


@router.post("/api/companies/{company_id}/analyze-all")
def analyze_all(company_id: int, db: Session = Depends(get_db)):
    """기업의 모든 보고서 × 3가지 유형을 일괄 요청. 보고서별로 1회씩 큐 투입."""
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")

    reports = db.query(Report).filter(
        Report.company_id == company_id,
        Report.file_path.isnot(None),
    ).all()

    queued_reports = 0
    for report in reports:
        has_pending = False
        for atype in VALID_TYPES:
            existing = db.query(Analysis).filter_by(
                company_id=company_id,
                report_id=report.id,
                analysis_type=atype,
            ).first()
            if existing and existing.status == "completed":
                continue
            _get_or_create_analysis(db, company_id, report.id, atype)
            has_pending = True

        if has_pending:
            enqueue(report.id)
            queued_reports += 1

    return {
        "message": f"{queued_reports}개 보고서 분석이 큐에 추가되었습니다. (보고서당 Gemini 1회 호출)",
        "queued": queued_reports,
    }


@router.get("/api/reports/{report_id}/analyses", response_model=list[AnalysisResponse])
def get_report_analyses(report_id: int, db: Session = Depends(get_db)):
    analyses = db.query(Analysis).filter(Analysis.report_id == report_id).all()
    return [AnalysisResponse.model_validate(a) for a in analyses]


@router.get("/api/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        raise HTTPException(404, "분석 결과를 찾을 수 없습니다.")
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
