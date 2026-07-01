from fastapi import APIRouter, Depends

from app.config import settings
from app.scheduler import scheduler, check_and_download_reports
from app.schemas import SchedulerStatus
from app.dependencies import require_admin

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/status", response_model=SchedulerStatus)
def get_status():
    job = scheduler.get_job("check_reports")
    return SchedulerStatus(
        is_running=scheduler.running,
        next_run_time=job.next_run_time if job else None,
        interval_hours=settings.scheduler_interval_hours,
    )


@router.post("/run-now", dependencies=[Depends(require_admin)])
async def run_now():
    await check_and_download_reports()
    return {"message": "실행 완료"}
