import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import get_or_404
from app.database import get_db
from app.dependencies import require_admin
from app.models import BatchJob
from app.schemas import BatchJobResponse
from app.services import gemini_batch as batch

router = APIRouter(tags=["batches"])


def _to_response(job: BatchJob) -> BatchJobResponse:
    return BatchJobResponse(
        id=job.id,
        job_name=job.job_name,
        model_name=job.model_name,
        thinking_level=job.thinking_level,
        state=job.state,
        report_ids=json.loads(job.report_ids),
        request_count=job.request_count,
        success_count=job.success_count,
        failed_count=job.failed_count,
        error_message=job.error_message,
        submitted_at=job.submitted_at,
        completed_at=job.completed_at,
        is_terminal=job.state in batch.TERMINAL_STATES,
    )


@router.get("/api/batches", response_model=list[BatchJobResponse])
def list_batches(limit: int = 50, db: Session = Depends(get_db)):
    jobs = db.query(BatchJob).order_by(BatchJob.id.desc()).limit(limit).all()
    return [_to_response(j) for j in jobs]


@router.post("/api/batches/{batch_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_batch(batch_id: int, db: Session = Depends(get_db)):
    """진행 중인 batch를 취소. 결과 반영은 다음 폴링에서 처리된다."""
    job = get_or_404(db, BatchJob, batch_id, "batch 작업을 찾을 수 없습니다.")
    if job.state in batch.TERMINAL_STATES:
        return {"message": f"이미 종료된 작업입니다 ({job.state})."}

    await batch.cancel(job.job_name)
    return {"message": "취소를 요청했습니다. 잠시 후 상태가 갱신됩니다."}
