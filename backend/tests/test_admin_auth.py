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


from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PROTECTED = [
    ("delete", "/api/tags/1"),
    ("delete", "/api/reports/1"),
    ("delete", "/api/companies/1"),
    ("post", "/api/reports/1/redownload"),
    ("post", "/api/reports/1/analyze-all"),
    ("post", "/api/companies/1/analyze-all"),
    ("post", "/api/scheduler/run-now"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_401_without_key(monkeypatch, method, path):
    monkeypatch.setattr(settings, "admin_key", "secret")
    resp = getattr(client, method)(path)
    assert resp.status_code == 401


def test_verify_ok_with_correct_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    resp = client.get("/api/admin/verify", headers={"X-Admin-Key": "secret"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_verify_401_with_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    resp = client.get("/api/admin/verify", headers={"X-Admin-Key": "nope"})
    assert resp.status_code == 401
