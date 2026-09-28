"""진행 중인 BatchJob의 상태를 확인하고, 완료되면 결과를 Analysis에 분배한다.

스케줄러가 주기적으로 호출한다. 재시작해도 DB의 BatchJob이 원본이라 그대로 이어받는다.
"""
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.constants import AnalysisStatus
from app.database import SessionLocal
from app.models import BatchJob
from app.services import analysis_service as svc
from app.services import gemini_batch as batch

logger = logging.getLogger(__name__)


def _distribute(db: Session, job: BatchJob, lines: list[str]) -> tuple[int, int]:
    """결과 JSONL을 report_id별로 분배해 저장하고 (성공, 실패) 건수를 반환.

    잡이 SUCCEEDED여도 개별 요청은 실패할 수 있으므로 줄 단위로 확인한다.
    """
    seen: set[int] = set()
    ok = failed = 0
    for line in lines:
        try:
            key, text, err = batch.parse_result_line(line)
            report_id = int(key)
        except (ValueError, json.JSONDecodeError):
            logger.warning("결과 줄 파싱 실패: %s", line[:200])
            continue

        seen.add(report_id)
        running = svc.get_by_status(db, report_id, AnalysisStatus.RUNNING)
        if not running:
            logger.warning("running 분석이 없어 결과를 버림: report_id=%d", report_id)
            continue

        if err:
            svc.mark_failed(db, running, err)
            failed += 1
        else:
            svc.save_result(db, running, text, job.model_name)
            ok += 1

    # 결과 줄이 아예 오지 않은 보고서 — 원인 불명이므로 실패로 남긴다
    for report_id in set(json.loads(job.report_ids)) - seen:
        running = svc.get_by_status(db, report_id, AnalysisStatus.RUNNING)
        if running:
            svc.mark_failed(db, running, "batch 결과에 해당 요청의 응답이 없습니다.")
            failed += 1
    return ok, failed


async def poll_batches() -> None:
    """미완료 BatchJob을 전부 확인한다."""
    db = SessionLocal()
    try:
        jobs = db.query(BatchJob).filter(
            BatchJob.state.notin_(list(batch.TERMINAL_STATES))
        ).all()
        if not jobs:
            return

        for job in jobs:
            try:
                info = await batch.get_status(job.job_name)
            except Exception:
                logger.exception("batch 상태 조회 실패: %s", job.job_name)
                continue

            job.state = info["state"]
            # batchStats는 비어 오는 경우가 있다 — 실제 결과 분배 후 덮어쓴다
            for field in ("request_count", "success_count", "failed_count"):
                if info[field]:
                    setattr(job, field, info[field])

            if info["state"] not in batch.TERMINAL_STATES:
                db.commit()
                continue

            job.completed_at = datetime.utcnow()
            job.error_message = info["error"]

            if info["state"] == "JOB_STATE_SUCCEEDED" and info["result_file"]:
                try:
                    lines = await batch.download_results(info["result_file"])
                    ok, failed = _distribute(db, job, lines)
                    job.success_count, job.failed_count = ok, failed
                    logger.info("batch 완료: %s (성공 %d, 실패 %d)", job.job_name, ok, failed)
                except Exception as e:
                    logger.exception("batch 결과 처리 실패: %s", job.job_name)
                    job.error_message = f"결과 처리 실패: {e}"
                    _fail_all(db, job, job.error_message)
            else:
                msg = info["error"] or f"batch 작업이 {info['state']} 상태로 끝났습니다."
                _fail_all(db, job, msg)
                logger.warning("batch 실패: %s — %s", job.job_name, msg)

            db.commit()
    finally:
        db.close()


def _fail_all(db: Session, job: BatchJob, message: str) -> None:
    report_ids = json.loads(job.report_ids)
    for report_id in report_ids:
        running = svc.get_by_status(db, report_id, AnalysisStatus.RUNNING)
        if running:
            svc.mark_failed(db, running, message)
    job.failed_count = len(report_ids)
    job.success_count = 0
