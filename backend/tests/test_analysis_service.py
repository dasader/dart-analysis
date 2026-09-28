"""통합 분석 프롬프트 조립·결과 저장 검증 — 외부 호출 없음.

핵심은 **끊긴 결과가 completed로 남지 않는 것**이다. responseSchema가 걸린 응답에서
모델이 인용 큰따옴표를 이스케이프 없이 쓰면 JSON 문자열이 거기서 끝나고, 뒤 내용은
조용히 사라졌다(실측 30건 중 2건).
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import MALFORMED_RESPONSE_PREFIX, AnalysisStatus
from app.migrate import run as run_migrations
from app.models import Analysis, Company, Report
from app.seed_prompts import seed_default_prompts
from app.services import analysis_service as svc

TYPES = ["subsidiary", "rnd", "national_tech"]


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    run_migrations(engine)
    session = sessionmaker(bind=engine)()
    seed_default_prompts(session)
    yield session
    session.close()


@pytest.fixture
def report(db):
    c = Company(corp_code="00126380", corp_name="삼성전자")
    db.add(c)
    db.flush()
    r = Report(company_id=c.id, rcept_no="1", report_name="사업보고서",
               report_type="annual", fiscal_year=2025)
    db.add(r)
    db.commit()
    return r


def _pending(db, report):
    rows = [Analysis(company_id=report.company_id, report_id=report.id,
                     analysis_type=t, status=AnalysisStatus.RUNNING) for t in TYPES]
    db.add_all(rows)
    db.commit()
    return rows


def test_report_text_has_no_ascii_double_quote(db, report):
    """원문의 27\" 같은 큰따옴표를 모델이 옮기면 JSON 문자열이 끝난다 — 미리 치운다."""
    _, user, _ = svc.build_prompts(db, report, TYPES, '27"QHD 500Hz QD-OLED 개발')
    body = user.split("---\n", 1)[1]
    assert '"' not in body and "27″QHD" in body


def test_truncated_result_is_failed_not_completed(db, report):
    rows = _pending(db, report)
    full = "## 요약\n내용\n\n## 시사점\n1. 끝"
    raw = json.dumps({"subsidiary": full, "rnd": "## 요약\n| SDC | 27", "national_tech": full},
                     ensure_ascii=False)
    svc.save_result(db, rows, raw, "m")

    status = {a.analysis_type: a.status for a in rows}
    assert status == {"subsidiary": AnalysisStatus.COMPLETED,
                      "rnd": AnalysisStatus.FAILED,
                      "national_tech": AnalysisStatus.COMPLETED}
    rnd = next(a for a in rows if a.analysis_type == "rnd")
    assert "끊겼" in rnd.error_message
    assert rnd.result_summary.endswith("| SDC | 27")  # 원인 추적용으로 남긴다


FULL = "## 요약\n내용\n\n## 시사점\n1. 끝"


def test_broken_json_fails_all_types(db, report):
    """잘린 JSON 안에도 `## 시사점`이 있다 — 예전엔 raw가 첫 유형에 들어가 completed로 저장됐다."""
    rows = _pending(db, report)
    raw = json.dumps({"subsidiary": FULL, "rnd": FULL}, ensure_ascii=False)[:-20]
    svc.save_result(db, rows, raw, "m")

    assert all(a.status == AnalysisStatus.FAILED for a in rows)
    assert all(a.error_message.startswith(MALFORMED_RESPONSE_PREFIX) for a in rows)


def test_complete_result_is_completed(db, report):
    rows = _pending(db, report)
    svc.save_result(db, rows, json.dumps({t: FULL for t in TYPES}, ensure_ascii=False), "m")

    assert all(a.status == AnalysisStatus.COMPLETED for a in rows)
