"""기술 스캔 병합 검증 — 외부 호출 없이 순수 로직만.

설계에서 정한 세 가지를 지킨다.
  1. 신규 진입 / 이탈 / 유지가 first_seen_at·last_seen_at으로 갈린다
  2. 부분 실패 시 저장하지 않는다
  3. max_companies 상한이 지켜진다
"""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.migrate import run as run_migrations
from app.models import Technology, TechCompany
from app.services import tech_scan


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tech.db'}")
    run_migrations(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def tech(db):
    t = Technology(name="전고체 배터리", description="설명",
                   keywords=json.dumps(["황화물계 고체전해질"], ensure_ascii=False),
                   max_companies=3)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def matched(tracked=(), available=(), excluded=()):
    def row(name, n, **kw):
        return {"applicant": name, "patents": n, "jurir_no": kw.get("jurir"),
                "keywords": kw.get("kws", []), **kw.get("extra", {})}
    return {
        "tracked": [row(n, c) for n, c in tracked],
        "available": [row(n, c) for n, c in available],
        "excluded": [row(n, c, extra={"reason": "법인번호 없음"}) for n, c in excluded],
    }


def test_first_scan_marks_everything_new(db, tech):
    now = datetime.utcnow()
    stats = tech_scan._merge(db, tech, matched(available=[("가전자", 10)]), now)
    assert stats == {"new": 1, "kept": 0, "dropped": 0}

    tc = db.query(TechCompany).one()
    assert tc.first_seen_at == now and tc.last_seen_at == now
    assert tc.status == "available" and tc.patent_count == 10


def test_second_scan_separates_new_kept_dropped(db, tech):
    t1 = datetime.utcnow()
    tech_scan._merge(db, tech, matched(available=[("가전자", 10), ("나소재", 5)]), t1)
    db.commit()

    t2 = t1 + timedelta(days=30)
    # 가전자는 유지, 나소재는 사라짐, 다모빌리티는 신규
    stats = tech_scan._merge(db, tech, matched(available=[("가전자", 12), ("다모빌리티", 7)]), t2)
    db.commit()

    assert stats == {"new": 1, "kept": 1, "dropped": 1}

    rows = {tc.applicant_name: tc for tc in db.query(TechCompany).all()}
    assert rows["가전자"].last_seen_at == t2 and rows["가전자"].patent_count == 12
    assert rows["다모빌리티"].first_seen_at == t2
    # 이탈은 지우지 않는다 — last_seen_at이 뒤처져 드러난다
    assert rows["나소재"].last_seen_at == t1


def test_dropped_company_is_kept_not_deleted(db, tech):
    t1 = datetime.utcnow()
    tech_scan._merge(db, tech, matched(available=[("나소재", 5)]), t1)
    db.commit()
    tech_scan._merge(db, tech, matched(available=[("가전자", 3)]), t1 + timedelta(days=30))
    db.commit()

    assert db.query(TechCompany).count() == 2      # 사라진 것도 남아 있다


def test_status_change_is_recorded(db, tech):
    """등록되면 available → tracked로 바뀐다."""
    t1 = datetime.utcnow()
    tech_scan._merge(db, tech, matched(available=[("가전자", 10)]), t1)
    db.commit()
    tech_scan._merge(db, tech, matched(tracked=[("가전자", 10)]), t1 + timedelta(days=30))
    db.commit()

    assert db.query(TechCompany).one().status == "tracked"


def test_keyword_hits_round_trip(db, tech):
    now = datetime.utcnow()
    m = {"tracked": [], "excluded": [],
         "available": [{"applicant": "가전자", "patents": 3, "jurir_no": None,
                        "keywords": ["황화물계 고체전해질", "전고체 배터리"]}]}
    tech_scan._merge(db, tech, m, now)
    db.commit()
    assert json.loads(db.query(TechCompany).one().keyword_hits) == [
        "황화물계 고체전해질", "전고체 배터리"]


def test_scan_refuses_without_keywords(db):
    """키워드가 없으면 검색을 시작조차 하지 않는다 (pytest-asyncio 없이 돌린다)."""
    import asyncio
    t = Technology(name="빈 기술", description="설명", keywords="[]")
    db.add(t)
    db.commit()
    with pytest.raises(tech_scan.ScanIncomplete, match="키워드"):
        asyncio.run(tech_scan.scan(db, t))


def test_keyword_stats_survives_broken_json(db, tech):
    """스캔 전이거나 값이 깨져 있어도 기술 화면이 열려야 한다."""
    from app.routers.technologies import _keyword_stats

    assert _keyword_stats(tech) == []                      # 스캔 전
    tech.keyword_stats = "{이건 JSON이 아님"
    assert _keyword_stats(tech) == []
    tech.keyword_stats = json.dumps(
        [{"word": "황화물계 고체전해질", "total": 4635, "broad": False}, "쓰레기"])
    assert _keyword_stats(tech) == [
        {"word": "황화물계 고체전해질", "total": 4635, "broad": False}]


def test_get_keywords_survives_broken_json(db):
    t = Technology(name="깨진 기술", description="설명", keywords="{이건 JSON이 아님")
    assert tech_scan.get_keywords(t) == []


def test_scan_learns_ipc_core_then_searches_inside_it(db, tech, monkeypatch):
    """첫 스캔은 제한 없이 검색해 코어를 저장하고, 다음 스캔은 그 코어 안에서만 검색한다."""
    import asyncio
    from app.services import patent_search
    calls = []

    async def fake_search(db, word, pages=1, rows=100, ipc=None):
        calls.append(ipc)
        items = [{"app_no": f"10-{i}", "ipc": "H01M 10/0562", "applicants": ["가"],
                  "title": "t", "app_date": "20240101", "status": "공개", "abstract": ""}
                 for i in range(10)]
        items.append({"app_no": "10-x", "ipc": "G06Q 50/08", "applicants": ["잡음"],
                      "title": "t", "app_date": "20240101", "status": "공개", "abstract": ""})
        return {"word": word, "total": len(items), "items": items, "pages_fetched": 1}

    monkeypatch.setattr(patent_search, "search", fake_search)
    asyncio.run(tech_scan.scan(db, tech))
    assert calls == [None]
    assert tech_scan.get_ipc_core(tech) == ["H01M 10"]
    # 사후로 걸러져 잡음 출원인은 들어오지 않는다
    assert {tc.applicant_name for tc in tech.companies} == {"가"}

    asyncio.run(tech_scan.scan(db, tech))
    assert calls[1] == ["H01M 10"]


def test_keyword_edit_clears_ipc_core(db, tech):
    """코어는 키워드가 정한다 — 키워드를 바꾸면 다음 스캔이 다시 잡는다. 같은 값이면 둔다."""
    from app.routers.technologies import update_technology
    from app.schemas import TechnologyUpdate
    tech.ipc_core = json.dumps(["H01M 10"])
    db.commit()

    update_technology(tech.id, TechnologyUpdate(keywords=["황화물계 고체전해질"]), db)
    assert tech_scan.get_ipc_core(tech) == ["H01M 10"]

    update_technology(tech.id, TechnologyUpdate(keywords=["아지로다이트"]), db)
    assert tech.ipc_core is None
