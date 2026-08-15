"""DB 백업·복원과 법인 벌크 적재.

**왜 필요한가.** 새 서버에 올릴 때 `dart_corps`의 법인번호를 다시 채우려면 DART를
3,983번 호출해야 하는데, 분당 제한이 네트워크 레이어에서 IP를 차단하는 방식이라
0.2초 간격 직렬로 20분 넘게 걸리고 차단 위험도 있다. 파일로 옮기는 편이 안전하다.

**파일 복사가 아니라 SQLite backup API를 쓴다.** 운영 중 `db.sqlite3`를 그냥 복사하면
쓰기 도중의 상태가 섞여 깨질 수 있다. `Connection.backup()`은 일관된 스냅샷을 보장하고,
같은 API를 역방향으로 쓰면 열린 DB에 **재시작 없이** 복원할 수 있다.
"""
import gzip
import io
import logging
import re
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import ApplicantCorp

logger = logging.getLogger(__name__)

# 새 서버로 옮겨야 하는 것 — 나머지(기업·보고서·분석)는 그 서버에서 쌓인다
CORP_TABLES = ("applicant_corps", "dart_corps")

# 복원 파일이 이 서비스의 DB가 맞는지 보는 최소 조건
_REQUIRED_TABLES = {"companies", "reports", "analyses"}

SEP = "¶"
EXPECTED_HEADER = ["출원인코드", "출원인명", "출원인영문명", "법인번호", "사업자번호"]


class BackupError(RuntimeError):
    """복원 파일이 잘못됐다. 이 예외가 나면 기존 DB는 건드리지 않은 상태다."""


def _db_path() -> Path:
    return settings.data_dir / "db.sqlite3"


# --- export -------------------------------------------------------------

def _snapshot(src: Path, dst: Path) -> None:
    """일관된 스냅샷. 운영 중 파일 복사와 달리 쓰기 중간 상태가 섞이지 않는다."""
    with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
        s.backup(d)


def dump_full(out: Path) -> None:
    """전체 DB를 gzip으로."""
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "snap.sqlite3"
        _snapshot(_db_path(), snap)
        _gzip_to(snap, out)


def dump_corps(out: Path) -> None:
    """법인 2테이블만 새 SQLite로 뽑아 gzip. 실측 21.6MB / 1.6초."""
    with tempfile.TemporaryDirectory() as tmp:
        snap, sub = Path(tmp) / "snap.sqlite3", Path(tmp) / "corps.sqlite3"
        _snapshot(_db_path(), snap)      # 먼저 스냅샷 — 뽑는 동안 원본이 바뀌어도 무관

        conn = sqlite3.connect(snap)
        try:
            conn.execute("attach database ? as sub", (str(sub),))
            for table in CORP_TABLES:
                row = conn.execute(
                    "select sql from sqlite_master where type='table' and name=?",
                    (table,)).fetchone()
                if not row:
                    continue
                # CREATE TABLE x → CREATE TABLE sub.x (따옴표 유무 둘 다 처리)
                ddl = re.sub(rf'\bTABLE\s+("?){re.escape(table)}\1',
                             f'TABLE sub."{table}"', row[0], count=1)
                conn.execute(ddl)
                conn.execute(f'insert into sub."{table}" select * from "{table}"')
            conn.commit()
            conn.execute("detach sub")
        finally:
            conn.close()
        _gzip_to(sub, out)


def _gzip_to(src: Path, out: Path) -> None:
    with open(src, "rb") as f, gzip.open(out, "wb", compresslevel=6) as g:
        shutil.copyfileobj(f, g)


# --- import -------------------------------------------------------------

def _gunzip_if_needed(src: Path, dst: Path) -> Path:
    """gzip이면 풀고, 아니면 그대로 쓴다 — 사용자가 압축을 풀어 올려도 받아준다."""
    with open(src, "rb") as f:
        magic = f.read(2)
    if magic != b"\x1f\x8b":
        return src
    with gzip.open(src, "rb") as g, open(dst, "wb") as f:
        shutil.copyfileobj(g, f)
    return dst


def _tables_of(path: Path) -> set[str]:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as c:
            return {r[0] for r in
                    c.execute("select name from sqlite_master where type='table'")}
    except sqlite3.DatabaseError as e:
        raise BackupError(f"SQLite 파일이 아닙니다: {e}") from e


def restore_full(upload: Path) -> dict:
    """전체 DB 교체. 검증에 실패하면 기존 DB를 건드리지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        src = _gunzip_if_needed(upload, Path(tmp) / "restore.sqlite3")
        missing = _REQUIRED_TABLES - _tables_of(src)
        if missing:
            raise BackupError(
                f"이 서비스의 DB가 아닌 것 같습니다. 없는 테이블: {', '.join(sorted(missing))}")

        # 열린 커넥션을 정리한 뒤 backup API로 덮어쓴다 — 파일 교체가 아니라
        # in-place 복원이라 재시작이 필요 없다
        engine.dispose()
        with sqlite3.connect(src) as s, sqlite3.connect(_db_path()) as d:
            s.backup(d)

    counts = _row_counts()
    logger.info("전체 DB 복원 완료: %s", counts)
    return counts


def restore_corps(upload: Path) -> dict:
    """법인 2테이블만 전량 교체. 기업·보고서·분석은 건드리지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        src = _gunzip_if_needed(upload, Path(tmp) / "corps.sqlite3")
        found = _tables_of(src) & set(CORP_TABLES)
        if not found:
            raise BackupError(
                f"법인 테이블이 없습니다. 기대: {', '.join(CORP_TABLES)}")

        conn = sqlite3.connect(_db_path())
        try:
            conn.execute("attach database ? as src", (str(src),))
            for table in sorted(found):
                # 분기 갱신은 전량 교체 — 증분 병합은 삭제된 출원인을 남겨 조인을 오염시킨다
                conn.execute(f'delete from "{table}"')
                conn.execute(f'insert into "{table}" select * from src."{table}"')
            conn.commit()
            conn.execute("detach src")
        finally:
            conn.close()

    counts = _row_counts()
    logger.info("법인 테이블 복원 완료: %s", counts)
    return counts


def _row_counts() -> dict:
    out = {}
    with sqlite3.connect(_db_path()) as c:
        for t in CORP_TABLES:
            try:
                out[t] = c.execute(f'select count(*) from "{t}"').fetchone()[0]
            except sqlite3.DatabaseError:
                out[t] = 0
    return out


# --- KIPRIS 벌크 적재 ----------------------------------------------------

def _open_text(path: Path) -> io.TextIOBase:
    """ZIP이면 안의 TXT를, 아니면 파일 자체를 텍스트로 연다."""
    if zipfile.is_zipfile(path):
        zf = zipfile.ZipFile(path)
        names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not names:
            raise BackupError(f"ZIP 안에 .txt가 없습니다: {zf.namelist()}")
        return io.TextIOWrapper(zf.open(names[0]), encoding="utf-8")
    return path.open(encoding="utf-8")


def parse_applicant_corps(path: Path) -> tuple[list[dict], int]:
    """(적재할 dict 목록, 건너뛴 줄 수). 형식: UTF-8, `¶` 구분, 헤더 1줄."""
    rows, skipped = [], 0
    with _open_text(path) as f:
        header = [c.strip() for c in f.readline().rstrip("\n").split(SEP)]
        if header[:5] != EXPECTED_HEADER:
            raise BackupError(
                f"헤더가 예상과 다릅니다. 서식이 바뀌었을 수 있습니다. 실제: {header[:5]}")
        seen = set()
        for line in f:
            parts = [p.strip() for p in line.rstrip("\n").split(SEP)]
            if len(parts) < 5 or not parts[0] or not parts[1]:
                skipped += 1
                continue
            code = parts[0]
            if code in seen:          # 같은 출원인코드가 두 번 나오면 첫 줄을 쓴다
                skipped += 1
                continue
            seen.add(code)
            jurir = re.sub(r"\D", "", parts[3])
            bizr = re.sub(r"\D", "", parts[4])
            rows.append({
                "applicant_code": code,
                "applicant_name": parts[1],
                "applicant_name_eng": parts[2] or None,
                "jurir_no": jurir if len(jurir) == 13 else None,
                "bizr_no": bizr if len(bizr) == 10 else None,
            })
    return rows, skipped


def load_applicant_corps(path: Path, db: Session | None = None) -> dict:
    """KIPRIS 벌크 파일을 전량 교체 적재. CLI와 API가 같이 쓴다."""
    rows, skipped = parse_applicant_corps(path)
    if not rows:
        raise BackupError("적재할 행이 없습니다.")

    Base.metadata.create_all(bind=engine)
    own = db is None
    db = db or SessionLocal()
    try:
        before = db.query(ApplicantCorp).count()
        db.query(ApplicantCorp).delete()
        db.bulk_insert_mappings(ApplicantCorp, rows)
        db.commit()
        after = db.query(ApplicantCorp).count()
    finally:
        if own:
            db.close()

    with_jurir = sum(1 for r in rows if r["jurir_no"])
    logger.info("법인 벌크 적재: %d → %d건", before, after)
    return {"before": before, "after": after, "skipped": skipped,
            "with_jurir": with_jurir}
