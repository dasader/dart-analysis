"""출원인 벌크 파싱·마이그레이션 검증. 외부 호출 없음."""
import io
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.migrate import run as run_migrations
from scripts.load_applicant_corps import parse

HEADER = "출원인코드¶출원인명¶출원인영문명¶법인번호¶사업자번호\n"
SAMPLE = HEADER + (
    "119980001253¶계양전기 주식회사¶KEYANG ELECTRIC¶110111-0212889¶104-81-34422\n"
    "120010012345¶주식회사 엘지화학¶LG CHEM¶110111-2207995¶ \n"          # 사업자번호 없음
    "120020099999¶홍길동¶ ¶ ¶ \n"                                      # 개인 — 둘 다 없음
    "120030011111¶깨진줄¶영문\n"                                        # 필드 부족 → 건너뜀
    "119980001253¶중복코드¶DUP¶110111-9999999¶104-81-99999\n"          # 중복 → 첫 줄 유지
)


def write(tmp_path: Path, name: str, text_body: str) -> Path:
    p = tmp_path / name
    p.write_text(text_body, encoding="utf-8")
    return p


def test_parse_extracts_numbers_and_drops_bad_rows(tmp_path):
    rows, skipped = parse(write(tmp_path, "CORP.txt", SAMPLE))

    assert skipped == 2                      # 필드 부족 + 중복
    assert [r["applicant_code"] for r in rows] == [
        "119980001253", "120010012345", "120020099999"]

    first = rows[0]
    assert first["jurir_no"] == "1101110212889"   # 하이픈 제거
    assert first["bizr_no"] == "1048134422"

    lg = rows[1]
    assert lg["jurir_no"] == "1101112207995"
    assert lg["bizr_no"] is None                  # 공백은 None

    person = rows[2]
    assert person["jurir_no"] is None and person["bizr_no"] is None


def test_parse_keeps_first_of_duplicate_code(tmp_path):
    rows, _ = parse(write(tmp_path, "CORP.txt", SAMPLE))
    dup = next(r for r in rows if r["applicant_code"] == "119980001253")
    assert dup["applicant_name"] == "계양전기 주식회사"   # 뒤의 '중복코드'가 아님


def test_parse_reads_zip(tmp_path):
    """실제 배포물이 ZIP이므로 그대로 읽혀야 한다."""
    zp = tmp_path / "Corporate.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("CORP_APPLICANT.txt", SAMPLE)
    rows, _ = parse(zp)
    assert len(rows) == 3


def test_parse_rejects_changed_header(tmp_path):
    """서식이 바뀌면 조용히 잘못 적재하지 말고 멈춰야 한다."""
    bad = "출원인코드¶출원인명¶법인번호\n119980001253¶계양전기¶110111-0212889\n"
    with pytest.raises(SystemExit, match="헤더"):
        parse(write(tmp_path, "CORP.txt", bad))


def test_migration_adds_missing_column(tmp_path):
    """create_all은 기존 테이블에 컬럼을 못 붙인다 — 마이그레이션이 채워야 한다."""
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:                      # jurir_no 없는 구버전 테이블
        conn.execute(text(
            "CREATE TABLE companies (id INTEGER PRIMARY KEY, corp_code VARCHAR)"))

    run_migrations(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("companies")}
    assert "jurir_no" in cols

    run_migrations(engine)                            # 두 번 돌려도 안전해야 한다
    assert "jurir_no" in {c["name"] for c in inspect(engine).get_columns("companies")}


def test_migration_skips_absent_table(tmp_path):
    """아직 없는 테이블은 create_all이 만들 몫 — 건드리지 않는다."""
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    run_migrations(engine)                            # 예외 없이 통과하면 된다
    assert "companies" not in inspect(engine).get_table_names()
