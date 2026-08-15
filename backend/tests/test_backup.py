"""DB 백업·복원·법인 벌크 적재.

**복원은 되돌릴 수 없다.** 잘못된 파일을 받았을 때 기존 데이터를 건드리지 않는지가
이 테스트의 핵심이다. 라운드트립(내보내고 다시 넣기)도 실제 건수로 확인한다.
"""
import gzip
import sqlite3
import zipfile

import pytest

from app.services import backup as svc


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    """실제 스키마의 빈 DB를 만들고 settings.data_dir를 거기로 돌린다."""
    from sqlalchemy import create_engine

    from app.migrate import run as run_migrations

    monkeypatch.setattr(svc.settings, "data_dir", tmp_path)
    path = tmp_path / "db.sqlite3"
    engine = create_engine(f"sqlite:///{path}")
    run_migrations(engine)
    engine.dispose()
    return path


def seed_corps(path, applicants=3, dart=2):
    with sqlite3.connect(path) as c:
        for i in range(applicants):
            c.execute("insert into applicant_corps (applicant_code, applicant_name, "
                      "jurir_no) values (?,?,?)", (f"A{i}", f"가전자{i}", f"{i:013d}"))
        for i in range(dart):
            c.execute("insert into dart_corps (corp_code, corp_name) values (?,?)",
                      (f"{i:08d}", f"나소재{i}"))
        c.commit()


def counts(path):
    with sqlite3.connect(path) as c:
        return tuple(c.execute(f"select count(*) from {t}").fetchone()[0]
                     for t in ("applicant_corps", "dart_corps"))


def test_corps_roundtrip(db_file, tmp_path):
    """새 서버로 옮기는 주 경로 — 뽑아서 빈 DB에 넣으면 건수가 같아야 한다."""
    seed_corps(db_file, applicants=5, dart=3)
    dump = tmp_path / "corps.gz"
    svc.dump_corps(dump)
    assert dump.stat().st_size > 0

    with sqlite3.connect(db_file) as c:      # 비운 뒤 복원
        c.execute("delete from applicant_corps")
        c.execute("delete from dart_corps")
        c.commit()
    assert counts(db_file) == (0, 0)

    result = svc.restore_corps(dump)
    assert counts(db_file) == (5, 3)
    assert result == {"applicant_corps": 5, "dart_corps": 3}


def test_corps_restore_replaces_not_merges(db_file, tmp_path):
    """분기 갱신은 전량 교체다 — 병합하면 삭제된 출원인이 남아 조인을 오염시킨다."""
    seed_corps(db_file, applicants=2, dart=1)
    dump = tmp_path / "corps.gz"
    svc.dump_corps(dump)

    with sqlite3.connect(db_file) as c:      # 옛 데이터를 잔뜩 넣어 둔다
        for i in range(90, 95):
            c.execute("insert into applicant_corps (applicant_code, applicant_name) "
                      "values (?,?)", (f"OLD{i}", "사라진출원인"))
        c.commit()

    svc.restore_corps(dump)
    assert counts(db_file)[0] == 2           # 옛것이 남지 않았다
    with sqlite3.connect(db_file) as c:
        assert c.execute("select count(*) from applicant_corps where "
                         "applicant_name='사라진출원인'").fetchone()[0] == 0


def test_corps_restore_keeps_other_tables(db_file, tmp_path):
    """법인 복원이 기업·보고서·분석을 건드리면 안 된다."""
    seed_corps(db_file)
    with sqlite3.connect(db_file) as c:
        c.execute("insert into companies (corp_code, corp_name) values ('X','지켜야할기업')")
        c.commit()
    dump = tmp_path / "corps.gz"
    svc.dump_corps(dump)
    svc.restore_corps(dump)

    with sqlite3.connect(db_file) as c:
        assert c.execute("select count(*) from companies").fetchone()[0] == 1


def test_full_roundtrip_includes_everything(db_file, tmp_path):
    seed_corps(db_file)
    with sqlite3.connect(db_file) as c:
        c.execute("insert into companies (corp_code, corp_name) values ('X','가전자')")
        c.commit()

    dump = tmp_path / "db.gz"
    svc.dump_full(dump)
    with sqlite3.connect(db_file) as c:
        c.execute("delete from companies")
        c.commit()

    svc.restore_full(dump)
    with sqlite3.connect(db_file) as c:
        assert c.execute("select count(*) from companies").fetchone()[0] == 1


def test_restore_rejects_non_sqlite_without_touching_db(db_file, tmp_path):
    """쓰레기 파일을 올려도 기존 데이터는 그대로여야 한다."""
    seed_corps(db_file, applicants=4, dart=2)
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"this is not a database")

    with pytest.raises(svc.BackupError):
        svc.restore_full(junk)
    assert counts(db_file) == (4, 2)


def test_restore_full_rejects_foreign_sqlite(db_file, tmp_path):
    """SQLite이긴 하나 다른 서비스의 DB — 필수 테이블이 없으면 거부한다."""
    seed_corps(db_file, applicants=4, dart=2)
    other = tmp_path / "other.sqlite3"
    with sqlite3.connect(other) as c:
        c.execute("create table something (id integer)")
        c.commit()

    with pytest.raises(svc.BackupError, match="없는 테이블"):
        svc.restore_full(other)
    assert counts(db_file) == (4, 2)


def test_restore_accepts_plain_and_gzip(db_file, tmp_path):
    """사용자가 압축을 풀어 올려도 받아준다."""
    seed_corps(db_file, applicants=3, dart=1)
    gz = tmp_path / "corps.gz"
    svc.dump_corps(gz)

    plain = tmp_path / "corps.sqlite3"
    plain.write_bytes(gzip.decompress(gz.read_bytes()))

    with sqlite3.connect(db_file) as c:
        c.execute("delete from applicant_corps")
        c.commit()
    svc.restore_corps(plain)
    assert counts(db_file)[0] == 3


def make_bulk(path, rows, header=None):
    head = SEP_JOIN(header or svc.EXPECTED_HEADER)
    body = "\n".join(SEP_JOIN(r) for r in rows)
    path.write_text(f"{head}\n{body}\n", encoding="utf-8")


def SEP_JOIN(parts):
    return svc.SEP.join(parts)


def test_applicant_bulk_txt(db_file, tmp_path):
    f = tmp_path / "corp.txt"
    make_bulk(f, [["A1", "가전자", "GA", "1234567890123", "1234567890"],
                  ["A2", "나소재", "", "", ""]])
    r = svc.load_applicant_corps(f)
    assert (r["after"], r["with_jurir"]) == (2, 1)


def test_applicant_bulk_zip(db_file, tmp_path):
    """KIPRIS는 ZIP으로 준다 — 풀지 않고 그대로 받는다."""
    txt = tmp_path / "corp.txt"
    make_bulk(txt, [["A1", "가전자", "GA", "1234567890123", "1234567890"]])
    z = tmp_path / "corp.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(txt, "CORP_APPLICANT.txt")

    assert svc.load_applicant_corps(z)["after"] == 1


def test_applicant_bulk_rejects_changed_header(db_file, tmp_path):
    """서식이 바뀌면 조용히 잘못 적재하지 말고 멈춘다."""
    f = tmp_path / "corp.txt"
    make_bulk(f, [["A1", "가전자", "", "", ""]], header=["코드", "이름", "x", "y", "z"])
    with pytest.raises(svc.BackupError, match="헤더"):
        svc.load_applicant_corps(f)


def test_applicant_bulk_replaces_all(db_file, tmp_path):
    f = tmp_path / "corp.txt"
    make_bulk(f, [["A1", "가전자", "", "", ""], ["A2", "나소재", "", "", ""]])
    svc.load_applicant_corps(f)

    make_bulk(f, [["A3", "다모빌리티", "", "", ""]])
    r = svc.load_applicant_corps(f)
    assert (r["before"], r["after"]) == (2, 1)


def test_applicant_bulk_skips_duplicate_codes(db_file, tmp_path):
    f = tmp_path / "corp.txt"
    make_bulk(f, [["A1", "가전자", "", "", ""], ["A1", "가전자(중복)", "", "", ""]])
    r = svc.load_applicant_corps(f)
    assert (r["after"], r["skipped"]) == (1, 1)
