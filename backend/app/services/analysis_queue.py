"""분석 큐 — 요청을 모아 Gemini Batch API에 한 번에 제출한다.

큐는 실행 대기열이 아니라 **묶는 버퍼**다. analyze-all이 보고서 10개를 연속 enqueue하면
batch 1개로 묶여 나간다. 진행 상태의 원본은 DB(BatchJob)이므로 재시작해도 폴링이 이어받는다.
"""
import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.constants import EXTRACTION_FAILED_PREFIX, AnalysisStatus
from app.database import SessionLocal
from app.models import Analysis, BatchJob
from app.services import analysis_service as svc
from app.services import app_settings
from app.services import gemini_batch as batch
from app.services.report_service import extract_text_from_report
from app.services.section_extract import ExtractionFailed, extract as extract_sections

logger = logging.getLogger(__name__)

# 큐는 report_id를 저장 — 동일 report_id 중복 투입 방지
_queue: asyncio.Queue[int] = asyncio.Queue()
_queued_ids: set[int] = set()

# 첫 요청 후 이 시간만큼 더 기다렸다가 제출 — 연속 enqueue를 한 batch로 묶기 위한 창
_BATCH_WINDOW_SECS = 5


def enqueue(report_id: int) -> None:
    """report_id를 큐에 추가. 이미 대기 중이면 무시."""
    if report_id in _queued_ids:
        logger.debug("report_id=%d 이미 큐에 있음, 중복 투입 무시", report_id)
        return
    _queue.put_nowait(report_id)
    _queued_ids.add(report_id)


def get_queue_info() -> dict:
    """대기 건수 + 진행 중인 batch 작업 요약."""
    db = SessionLocal()
    try:
        running = (
            db.query(BatchJob)
            .filter(BatchJob.state.notin_(list(batch.TERMINAL_STATES)))
            .order_by(BatchJob.id.desc())
            .all()
        )
        return {
            "pending_count": _queue.qsize(),
            "running_batches": len(running),
            "running_reports": sum(len(json.loads(j.report_ids)) for j in running),
        }
    finally:
        db.close()


def requeue_orphans() -> int:
    """앱 시작 시 호출 — batch에 실리지 못하고 남은 pending 분석을 다시 투입한다.

    in-memory 큐는 재시작으로 유실되므로 DB의 pending이 유일한 단서다.
    진행 중인 BatchJob에 이미 실린 report는 제외한다(폴링이 이어받는다).
    """
    db = SessionLocal()
    try:
        in_flight: set[int] = set()
        for j in db.query(BatchJob).filter(
            BatchJob.state.notin_(list(batch.TERMINAL_STATES))
        ).all():
            in_flight.update(json.loads(j.report_ids))

        orphans = {
            rid for (rid,) in db.query(Analysis.report_id)
            .filter(Analysis.status == AnalysisStatus.PENDING).distinct().all()
        } - in_flight

        for rid in orphans:
            enqueue(rid)
        if orphans:
            logger.info("고아 pending 분석 재투입: %d개 보고서", len(orphans))
        return len(orphans)
    finally:
        db.close()


def _build_request(db: Session, report_id: int) -> str | None:
    """report 1건의 JSONL 줄을 만든다. 불가하면 해당 분석을 failed로 두고 None."""
    pending = svc.get_pending(db, report_id)
    if not pending:
        return None

    try:
        raw_text = extract_text_from_report(pending[0].report.file_path)
        if not raw_text:
            raise ValueError("보고서 텍스트를 추출할 수 없습니다.")

        if app_settings.get(db, "section_extract_enabled"):
            # 구역 추출에 실패하면 LLM으로 보내지 않는다 — 서식이 바뀐 채로 전문을
            # 흘려보내면 아무도 모르게 비용만 나간다. 실패를 드러내 소스를 고치게 한다.
            try:
                raw_text = extract_sections(raw_text)
            except ExtractionFailed as e:
                logger.error("구역 추출 실패: report_id=%d — %s", report_id, e)
                svc.mark_failed(db, pending, f"{EXTRACTION_FAILED_PREFIX}{e}")
                return None

        types_to_run = [a.analysis_type for a in pending]
        system, user, max_out = svc.build_prompts(
            db, pending[0].report, types_to_run, raw_text
        )
    except Exception as e:
        logger.exception("요청 생성 실패: report_id=%d", report_id)
        svc.mark_failed(db, pending, str(e))
        return None

    for a in pending:
        a.status = AnalysisStatus.RUNNING
    db.commit()
    return batch.build_jsonl_line(str(report_id), system, user, max_out, types_to_run)


async def _drain(first: int) -> list[int]:
    """첫 항목 이후 짧은 창 동안 더 모아 한 batch로 묶는다."""
    ids = [first]
    deadline = asyncio.get_running_loop().time() + _BATCH_WINDOW_SECS
    while True:
        timeout = deadline - asyncio.get_running_loop().time()
        if timeout <= 0:
            break
        try:
            rid = await asyncio.wait_for(_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            break
        ids.append(rid)
        _queue.task_done()
    return ids


async def worker() -> None:
    """큐를 드레인해 batch로 제출하는 무한 루프."""
    while True:
        first = await _queue.get()
        try:
            report_ids = await _drain(first)
            for rid in report_ids:
                _queued_ids.discard(rid)

            db = SessionLocal()
            try:
                lines, submitted_ids = [], []
                for rid in report_ids:
                    line = await asyncio.get_running_loop().run_in_executor(
                        None, _build_request, db, rid
                    )
                    if line:
                        lines.append(line)
                        submitted_ids.append(rid)

                if not lines:
                    continue

                display = f"dart-{datetime.utcnow():%Y%m%d-%H%M%S}-{len(lines)}건"
                try:
                    job_name, file_name = await batch.submit(lines, display)
                except Exception as e:
                    logger.exception("batch 제출 실패")
                    for rid in submitted_ids:
                        svc.mark_failed(db, svc.get_running(db, rid), f"batch 제출 실패: {e}")
                    continue

                db.add(BatchJob(
                    job_name=job_name,
                    file_name=file_name,
                    model_name=batch.MODEL_NAME,
                    thinking_level=batch.THINKING_LEVEL,
                    state="JOB_STATE_PENDING",
                    report_ids=json.dumps(submitted_ids),
                    request_count=len(lines),
                ))
                db.commit()
                logger.info("batch 제출: %s (%d건)", job_name, len(lines))
            finally:
                db.close()
        except Exception:
            logger.exception("큐 워커 오류")
        finally:
            _queue.task_done()
