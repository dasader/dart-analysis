import pytest
from fastapi import HTTPException

from app.config import settings
from app.dependencies import require_admin


def test_disabled_when_key_empty(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "")
    assert require_admin(None) is None
    assert require_admin("anything") is None


def test_rejects_missing_header(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    with pytest.raises(HTTPException) as exc:
        require_admin(None)
    assert exc.value.status_code == 401


def test_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    with pytest.raises(HTTPException) as exc:
        require_admin("wrong")
    assert exc.value.status_code == 401


def test_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    assert require_admin("secret") is None
