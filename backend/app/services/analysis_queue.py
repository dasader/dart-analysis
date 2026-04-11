import asyncio
import logging
import time

from app.config import settings
from app.database import SessionLocal
from app.services.analysis_service import run_combined_analysis

logger = logging.getLogger(__name__)

# 큐는 report_id를 저장 — 동일 report_id 중복 투입 방지
_queue: asyncio.Queue[int] = asyncio.Queue()
_queued_ids: set[int] = set()          # 큐에 대기 중인 report_id
_running_report_id: int | None = None
_last_finished_at: float = 0.0


def enqueue(report_id: int) -> None:
    """report_id를 큐에 추가. 이미 대기/실행 중이면 무시."""
    if report_id in _queued_ids or report_id == _running_report_id:
        logger.debug("report_id=%d 이미 큐에 있음, 중복 투입 무시", report_id)
        return
    _queue.put_nowait(report_id)
    _queued_ids.add(report_id)


def get_queue_info() -> dict:
    return {
        "pending_count": _queue.qsize(),
        "running": {"report_id": _running_report_id} if _running_report_id else None,
    }


async def worker() -> None:
    """큐에서 report_id를 꺼내 combined analysis를 실행하는 무한 루프 워커.

    TPM 한도 준수를 위해 직전 분석 완료 후 settings.analysis_interval_secs 대기.
    """
    global _running_report_id, _last_finished_at

    while True:
        report_id = await _queue.get()
        _queued_ids.discard(report_id)

        # 직전 분석 완료 후 최소 대기
        elapsed = time.monotonic() - _last_finished_at
        wait = settings.analysis_interval_secs - elapsed
        if wait > 0 and _last_finished_at > 0:
            logger.info(
                "TPM 한도 준수: %.1fs 대기 후 report_id=%d 분석 시작", wait, report_id
            )
            await asyncio.sleep(wait)

        _running_report_id = report_id
        try:
            db = SessionLocal()
            try:
                await run_combined_analysis(db, report_id)
            finally:
                db.close()
        except Exception:
            logger.exception("combined analysis 워커 오류: report_id=%d", report_id)
        finally:
            _last_finished_at = time.monotonic()
            _running_report_id = None
            _queue.task_done()
