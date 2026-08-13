"""런타임 설정 — .env 기본값 폴백과 DB 반영 검증."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.services import app_settings


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_falls_back_to_env_default(db):
    """DB에 값이 없으면 .env 기본값을 쓴다 — 기존 동작이 유지된다."""
    assert app_settings.get(db, "scheduler_auto_analyze") == settings.scheduler_auto_analyze
    assert app_settings.get(db, "section_extract_enabled") == settings.section_extract_enabled


def test_db_value_overrides_env(db):
    for key in app_settings.TOGGLES:
        app_settings.set_value(db, key, False)
        assert app_settings.get(db, key) is False
        app_settings.set_value(db, key, True)
        assert app_settings.get(db, key) is True


def test_set_twice_updates_not_duplicates(db):
    """같은 키를 두 번 저장해도 행이 하나여야 한다 (primary key)."""
    app_settings.set_value(db, "scheduler_auto_analyze", True)
    app_settings.set_value(db, "scheduler_auto_analyze", False)
    assert app_settings.get(db, "scheduler_auto_analyze") is False


def test_list_all_exposes_labels(db):
    items = app_settings.list_all(db)
    assert {i["key"] for i in items} == set(app_settings.TOGGLES)
    for i in items:
        assert i["label"] and i["description"]
        assert isinstance(i["value"], bool)
