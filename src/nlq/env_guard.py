"""NLQ environment loading + env-class guard (aam_deferred_work.md #45; DISP #24 class).

NLQ's main.py used to call load_dotenv() bare, which loads nlq/.env — and .env
targets PROD (DCL_API_URL :8004 + SUPABASE_URL = AOS_NLQ prod). A plain
`pm2 restart` therefore silently reverted NLQ from dev to prod, so it queried the
wrong DCL (and read a prod DB).

This module makes DEV the default (CLAUDE.md: "always load .env.development for
local runs and testing"): it loads .env as the base (shared keys), then overlays
.env.development unless AOS_ENV=prod. After loading it classifies the resolved
DCL + DB targets and REFUSES to start (fail loud, A1) on either a mixed dev/prod
configuration or a PROD configuration reached without an explicit AOS_ENV=prod —
so a bare restart can never silently land on prod again.

Env classes (DCL port + Supabase project ref):
  DEV  — DCL :8104 + aos-dev (glmeqbnuahlkkbolkent)
  PROD — DCL :8004 + AOS_NLQ (yuxrdoamtjmodjzqpeds) or prod DCL (gdbmdrouocxjxiohpixr)
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]  # .../nlq

_DEV_MARKERS = (":8104", "glmeqbnuahlkkbolkent")
_PROD_MARKERS = (":8004", "yuxrdoamtjmodjzqpeds", "gdbmdrouocxjxiohpixr")


def _classify(*values: str) -> str:
    """DEV / PROD / MIXED / UNKNOWN from the resolved DCL + DB strings."""
    blob = " ".join(v for v in values if v)
    has_dev = any(m in blob for m in _DEV_MARKERS)
    has_prod = any(m in blob for m in _PROD_MARKERS)
    if has_dev and has_prod:
        return "MIXED"
    if has_dev:
        return "DEV"
    if has_prod:
        return "PROD"
    return "UNKNOWN"


def load_and_guard_env() -> str:
    """Load env (dev by default) then enforce class consistency. Returns the class.

    Call once, before any NLQ service module reads os.environ.
    """
    want_prod = os.environ.get("AOS_ENV", "").strip().lower() in ("prod", "production")
    # A pre-set AOS_TENANT_ID (an operator scoping a run at a specific entity's
    # tenant) is OPERATIONAL, not a dev/prod class choice — it must survive the
    # .env.development overlay below, which load_dotenv(override=True) would
    # otherwise clobber with the file's default tenant.
    _pin_tenant = os.environ.get("AOS_TENANT_ID", "").strip()

    base = _REPO_ROOT / ".env"
    if base.is_file():
        load_dotenv(base)
    if not want_prod:
        dev = _REPO_ROOT / ".env.development"
        if dev.is_file():
            # Dev overlay wins over the base — DCL :8104 + aos-dev.
            load_dotenv(dev, override=True)
    if _pin_tenant:
        os.environ["AOS_TENANT_ID"] = _pin_tenant  # operator scoping wins over the files

    dcl = os.environ.get("DCL_API_URL", "")
    db = os.environ.get("SUPABASE_URL", "") + " " + os.environ.get("DATABASE_URL", "")
    cls = _classify(dcl, db)

    if cls == "MIXED":
        raise RuntimeError(
            "FATAL: NLQ env-class drift — refusing to start. The resolved DCL/DB "
            f"targets mix dev and prod (DCL_API_URL={dcl!r}). Dev "
            "(.env.development: DCL :8104 + aos-dev glmeqbn) and prod (.env: DCL "
            ":8004 + AOS_NLQ yuxrdo) must not be combined (aam_deferred_work.md #45)."
        )
    if cls == "PROD" and not want_prod:
        raise RuntimeError(
            "FATAL: NLQ resolved a PROD configuration without AOS_ENV=prod "
            f"(DCL_API_URL={dcl!r}). Refusing to start — a bare restart must not "
            "silently target prod. Use the default dev config (.env.development), "
            "or set AOS_ENV=prod to opt into prod explicitly (aam_deferred_work.md #45)."
        )
    return cls
