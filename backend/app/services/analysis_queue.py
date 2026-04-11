import asyncio
import logging

from app.database import SessionLocal
from app.services.analysis_service import run_analysis

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[int] = asyncio.Queue()
_current_analysis_id: int | None = None


def enqueue(analysis_id: int) -> None:
    """분석 작업을 큐에 추가."""
    _queue.put_nowait(analysis_id)


def get_queue_info() -> dict:
    """큐 상태 정보 반환."""
    return {
        "pending_count": _queue.qsize(),
        "running": {"analysis_id": _current_analysis_id} if _current_analysis_id else None,
    }


async def worker() -> None:
    """큐에서 분석 작업을 하나씩 꺼내 실행하는 무한 루프 워커."""
    global _current_analysis_id
    while True:
        analysis_id = await _queue.get()
        _current_analysis_id = analysis_id
        try:
            db = SessionLocal()
            try:
                await run_analysis(db, analysis_id)
            finally:
                db.close()
        except Exception:
            logger.exception(f"분석 실행 실패: analysis_id={analysis_id}")
        finally:
            _current_analysis_id = None
            _queue.task_done()
