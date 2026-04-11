from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Report, Analysis
from app.schemas import AnalysisRequest, AnalysisResponse, QueueStatus
from app.services.analysis_queue import enqueue, get_queue_info

VALID_TYPES = ("subsidiary", "rnd", "national_tech")

router = APIRouter(tags=["analyses"])


@router.post("/api/reports/{report_id}/analyze", response_model=AnalysisResponse)
def analyze_report(
    report_id: int,
    body: AnalysisRequest,
    db: Session = Depends(get_db),
):
    """분석 요청을 큐에 추가하고 즉시 반환. 백그라운드에서 처리됨."""
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    if not report.file_path:
        raise HTTPException(400, "보고서 파일이 아직 다운로드되지 않았습니다.")
    if body.analysis_type not in VALID_TYPES:
        raise HTTPException(400, f"지원하지 않는 분석 유형: {body.analysis_type}")

    # 기존 분석이 있으면 재사용 (status를 pending으로 리셋)
    existing = db.query(Analysis).filter_by(
        company_id=report.company_id,
        report_id=report.id,
        analysis_type=body.analysis_type,
    ).first()

    if existing:
        existing.status = "pending"
        existing.error_message = None
        db.commit()
        db.refresh(existing)
        enqueue(existing.id)
        return AnalysisResponse.model_validate(existing)

    analysis = Analysis(
        company_id=report.company_id,
        report_id=report.id,
        analysis_type=body.analysis_type,
        status="pending",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    enqueue(analysis.id)
    return AnalysisResponse.model_validate(analysis)


@router.post("/api/companies/{company_id}/analyze-all")
def analyze_all(company_id: int, db: Session = Depends(get_db)):
    """해당 기업의 모든 보고서 × 모든 분석 유형을 일괄 큐에 추가."""
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")

    reports = db.query(Report).filter(
        Report.company_id == company_id,
        Report.file_path.isnot(None),
    ).all()

    queued = 0
    for report in reports:
        for atype in VALID_TYPES:
            existing = db.query(Analysis).filter_by(
                company_id=company_id,
                report_id=report.id,
                analysis_type=atype,
            ).first()

            if existing and existing.status == "completed":
                continue  # 이미 완료된 건 건너뜀

            if existing:
                existing.status = "pending"
                existing.error_message = None
                db.commit()
                enqueue(existing.id)
            else:
                analysis = Analysis(
                    company_id=company_id,
                    report_id=report.id,
                    analysis_type=atype,
                    status="pending",
                )
                db.add(analysis)
                db.commit()
                db.refresh(analysis)
                enqueue(analysis.id)
            queued += 1

    return {"message": f"{queued}건의 분석이 큐에 추가되었습니다.", "queued": queued}


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
