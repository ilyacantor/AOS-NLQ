"""Env-class guard tests (aam_deferred_work.md #45).

NLQ must default to DEV and refuse to silently start on PROD after a bare
`pm2 restart`. These pin the classifier and both fail-loud paths.
"""
import pytest

from src.nlq import env_guard
from src.nlq.env_guard import _classify, load_and_guard_env

_PROD = "DCL_API_URL=http://localhost:8004\nSUPABASE_URL=https://yuxrdoamtjmodjzqpeds.supabase.co\n"
_DEV = "DCL_API_URL=http://localhost:8104\nSUPABASE_URL=https://glmeqbnuahlkkbolkent.supabase.co\n"
_MIXED = "DCL_API_URL=http://localhost:8104\nSUPABASE_URL=https://yuxrdoamtjmodjzqpeds.supabase.co\n"


def _clear(monkeypatch):
    for k in ("DCL_API_URL", "SUPABASE_URL", "DATABASE_URL", "AOS_ENV"):
        monkeypatch.delenv(k, raising=False)


def _repo(tmp_path, monkeypatch, env_text, dev_text=None):
    (tmp_path / ".env").write_text(env_text)
    if dev_text is not None:
        (tmp_path / ".env.development").write_text(dev_text)
    monkeypatch.setattr(env_guard, "_REPO_ROOT", tmp_path)


def test_classify():
    assert _classify("http://localhost:8104", "x glmeqbnuahlkkbolkent") == "DEV"
    assert _classify("http://localhost:8004", "x yuxrdoamtjmodjzqpeds") == "PROD"
    assert _classify("http://localhost:8104", "x yuxrdoamtjmodjzqpeds") == "MIXED"
    assert _classify("", "") == "UNKNOWN"


def test_dev_is_default(tmp_path, monkeypatch):
    # Prod base + dev overlay, no AOS_ENV -> dev overlay wins (dev survives restart).
    _clear(monkeypatch)
    _repo(tmp_path, monkeypatch, _PROD, dev_text=_DEV)
    assert load_and_guard_env() == "DEV"


def test_prod_without_optin_refused(tmp_path, monkeypatch):
    # Prod-only box, no .env.development, no AOS_ENV -> must fail loud.
    _clear(monkeypatch)
    _repo(tmp_path, monkeypatch, _PROD)
    with pytest.raises(RuntimeError, match="without AOS_ENV=prod"):
        load_and_guard_env()


def test_mixed_refused(tmp_path, monkeypatch):
    _clear(monkeypatch)
    _repo(tmp_path, monkeypatch, _MIXED)
    with pytest.raises(RuntimeError, match="env-class drift"):
        load_and_guard_env()


def test_explicit_prod_optin(tmp_path, monkeypatch):
    # AOS_ENV=prod -> load .env (prod), skip dev overlay, allowed.
    _clear(monkeypatch)
    monkeypatch.setenv("AOS_ENV", "prod")
    _repo(tmp_path, monkeypatch, _PROD, dev_text=_DEV)
    assert load_and_guard_env() == "PROD"
