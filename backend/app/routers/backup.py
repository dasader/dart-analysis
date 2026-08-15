"""DB 백업·복원·법인 벌크 업로드. 전부 관리자 전용.

업로드는 디스크의 임시 파일을 경유한다 — 89MB짜리 DB를 메모리에 통째로 올리지 않기
위해서다. FastAPI의 UploadFile은 SpooledTemporaryFile이라 일정 크기를 넘으면 알아서
디스크로 넘어가지만, 여기서는 확실히 하려고 명시적으로 청크 복사한다.
"""
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.dependencies import require_admin
from app.services import backup as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"],
                   dependencies=[Depends(require_admin)])

_CHUNK = 1 << 20  # 1MB


def _spool(upload: UploadFile, dest: Path) -> None:
    """업로드를 디스크로 흘려보낸다(메모리에 통째로 올리지 않는다)."""
    with open(dest, "wb") as f:
        while chunk := upload.file.read(_CHUNK):
            f.write(chunk)


def _download(path: Path, filename: str) -> FileResponse:
    """다 보내고 나면 임시 파일을 지운다."""
    return FileResponse(
        path=str(path),
        media_type="application/gzip",
        filename=filename,
        background=BackgroundTask(lambda: path.unlink(missing_ok=True)),
    )


@router.get("/corps")
def export_corps():
    """법인 2테이블만 — 새 서버로 옮길 때 쓴다. 실측 21.6MB."""
    out = Path(tempfile.mkdtemp()) / "corps.sqlite3.gz"
    svc.dump_corps(out)
    return _download(out, f"dart-corps-{datetime.now():%Y%m%d}.sqlite3.gz")


@router.get("/db")
def export_db():
    """전체 DB. 분석 결과까지 포함한다."""
    out = Path(tempfile.mkdtemp()) / "db.sqlite3.gz"
    svc.dump_full(out)
    return _download(out, f"dart-db-{datetime.now():%Y%m%d}.sqlite3.gz")


@router.post("/corps")
def import_corps(file: UploadFile):
    """법인 2테이블 전량 교체. 기업·보고서·분석은 건드리지 않는다."""
    return _restore(file, svc.restore_corps)


@router.post("/db")
def import_db(file: UploadFile):
    """전체 DB 교체. **현재 데이터가 전부 사라진다.**"""
    return _restore(file, svc.restore_full)


def _restore(file: UploadFile, fn):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.bin"
        _spool(file, path)
        try:
            counts = fn(path)
        except svc.BackupError as e:
            # 검증 실패 — 기존 DB는 그대로다
            raise HTTPException(400, str(e)) from e
    return {"ok": True, "counts": counts}


@router.post("/applicant-corps")
def upload_applicant_corps(file: UploadFile):
    """KIPRIS 벌크(ZIP 또는 TXT)를 즉시 적재. 실측 13MB / 5초."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (file.filename or "corp.zip")
        _spool(file, path)
        try:
            return svc.load_applicant_corps(path)
        except svc.BackupError as e:
            raise HTTPException(400, str(e)) from e


@router.get("/status")
def backup_status():
    """현재 적재량 — 화면에서 '옮겨야 할 게 있는지' 판단하는 근거."""
    return svc._row_counts()
