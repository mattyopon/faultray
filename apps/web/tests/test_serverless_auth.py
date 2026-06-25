"""Regression tests for serverless auth parity (api/_auth.py).

compliance.py and reports.py previously served unauthenticated while their
engine.py sibling enforced an auth gate. They now call the shared
`authenticate()` first in every do_GET/do_POST. These tests pin the shared
gate's behaviour and that both handlers import it.
"""
import importlib.util
import io
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / "api" / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


auth = _load("faultray_auth", "_auth.py")


class _Headers(dict):
    def get(self, key, default=""):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeHandler:
    def __init__(self, headers=None):
        self.headers = _Headers(headers or {})
        self.status = None
        self.sent_headers = []
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, k, v):
        self.sent_headers.append((k, v))

    def end_headers(self):
        pass


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("FAULTRAY_ENGINE_SECRET", "NEXT_PUBLIC_SUPABASE_URL",
              "SUPABASE_SERVICE_ROLE_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY",
              "FAULTRAY_ALLOW_UNAUTHENTICATED"):
        monkeypatch.delenv(k, raising=False)


def test_unauthenticated_fails_closed_with_401():
    h = _FakeHandler()
    assert auth.authenticate(h) is False
    assert h.status == 401


def test_valid_api_key_allows(monkeypatch):
    monkeypatch.setenv("FAULTRAY_ENGINE_SECRET", "s3cret")
    assert auth.authenticate(_FakeHandler({"X-API-Key": "s3cret"})) is True


def test_wrong_api_key_rejected(monkeypatch):
    monkeypatch.setenv("FAULTRAY_ENGINE_SECRET", "s3cret")
    h = _FakeHandler({"X-API-Key": "nope"})
    assert auth.authenticate(h) is False
    assert h.status == 401


def test_dev_optin_only_when_supabase_unconfigured(monkeypatch):
    monkeypatch.setenv("FAULTRAY_ALLOW_UNAUTHENTICATED", "1")
    assert auth.authenticate(_FakeHandler()) is True


def test_no_fail_open_once_supabase_configured(monkeypatch):
    # The dev opt-in must NOT bypass auth once Supabase is configured.
    monkeypatch.setenv("FAULTRAY_ALLOW_UNAUTHENTICATED", "1")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")
    h = _FakeHandler()
    assert auth.authenticate(h) is False
    assert h.status == 401


@pytest.mark.parametrize("rel", ["compliance.py", "reports.py"])
def test_handlers_import_shared_auth(rel):
    mod = _load(f"faultray_{rel.split('.')[0]}", rel)
    assert mod.authenticate is auth.authenticate or mod.authenticate.__name__ == "authenticate"
