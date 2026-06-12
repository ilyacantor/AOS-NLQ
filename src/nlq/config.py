"""
Configuration management for AOS-NLQ.

Handles environment variables, settings, and configuration loading.
Uses pydantic-settings for validation and type safety.

Tenant ID resolution: use get_tenant_id() — NLQ MIRRORS DCL. The active tenant
is whatever DCL last ingested (the top of GET /api/dcl/triples/runs), re-checked
on a short TTL so a fresh pipeline run shows up in NLQ without a restart.
AOS_TENANT_ID is only a fallback when DCL is unreachable (never the pin it used
to be). Never falls back silently; raises RuntimeError if neither resolves.
"""

import json
import logging
import os
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

_config_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tenant ID resolution (replaces the old DEFAULT_TENANT_ID constant)
# ---------------------------------------------------------------------------

_tenant_id_cache: Optional[str] = None
_tenant_cache_ts: float = 0.0
# How long NLQ trusts its last DCL-current resolution before re-checking. Short
# enough that a fresh pipeline run is reflected within seconds; long enough that
# get_tenant_id() (called per request) does not hit DCL on every call.
_TENANT_FOLLOW_TTL_S = 15.0

# ONE cached read of DCL's most-recent ingest run (top of GET /api/dcl/triples/runs).
# BOTH tenant resolution (_current_tenant_from_dcl) and run-identity display
# (current_run_from_dcl — the pipeline status light) derive from this single cached
# fetch, on the same follow cadence as tenant. So a status poll adds NO DCL round-trip
# over what tenant resolution already does, and the run NLQ displays is provably the
# run NLQ queries against (same source, same cache).
_current_run_cache: Optional[Dict[str, Any]] = None
_current_run_cache_ts: float = 0.0


def _fetch_top_run_from_dcl() -> Optional[Dict[str, Any]]:
    """Raw, uncached read of DCL's most-recent ingest run (top of
    GET /api/dcl/triples/runs). Returns the full run dict, or None if DCL is
    unreachable / has no runs. Callers go through current_run_from_dcl() for caching.
    """
    import httpx

    dcl_url = os.environ.get("DCL_API_URL", "").rstrip("/")
    if not dcl_url:
        return None
    try:
        resp = httpx.get(f"{dcl_url}/api/dcl/triples/runs", params={"limit": 1}, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        runs = data.get("runs", data if isinstance(data, list) else [])
        return runs[0] if runs else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None


def current_run_from_dcl() -> Optional[Dict[str, Any]]:
    """Identity of DCL's most-recent ingest run — read from the RUNS surface, never
    from DCL's /api/health payload.

    DCL's /api/health carries a `last_run_id`, but health endpoints are liveness
    probes, not data contracts (dcl#69): that id lags or diverges from the actual
    most-recent ingest run — verified empirically, the health `last_run_id` is not
    even present in the runs list. Run identity is therefore read from the SAME
    ordered surface get_tenant_id() and the entity index already follow
    (GET /api/dcl/triples/runs), so the run NLQ displays in its status light matches
    the run NLQ actually resolves queries against.

    Cached for _TENANT_FOLLOW_TTL_S and shared with _current_tenant_from_dcl(): one
    runs fetch backs both tenant resolution and the status light, so no caller pays a
    duplicate round-trip. On a transient DCL miss the last good read is served rather
    than flapping to None; only a cold miss (never resolved) returns None — the caller
    decides whether that is fatal. No silent fabrication.

    Returns {dcl_ingest_id, tenant_id, tenant_label, timestamp} for the top
    (most-recent) run. dcl_ingest_id is the namespaced run identifier
    (I1: never a bare run_id).
    """
    global _current_run_cache, _current_run_cache_ts

    now = time.monotonic()
    if _current_run_cache is not None and (now - _current_run_cache_ts) < _TENANT_FOLLOW_TTL_S:
        return _current_run_cache

    top = _fetch_top_run_from_dcl()
    if top is not None:
        _current_run_cache = {
            "dcl_ingest_id": top.get("dcl_ingest_id"),
            "tenant_id": top.get("tenant_id"),
            "tenant_label": top.get("tenant_label"),
            "timestamp": top.get("timestamp"),
        }
        _current_run_cache_ts = now
        return _current_run_cache

    # DCL momentarily unreachable but we resolved before → serve the last known
    # current run rather than flapping to None (mirrors get_tenant_id's behavior).
    return _current_run_cache


def _current_tenant_from_dcl() -> Optional[str]:
    """The tenant of DCL's most-recent ingest run — "whatever entity DCL shows".

    NLQ mirrors DCL: the active entity is whatever was last ingested (the top of
    GET /api/dcl/triples/runs). Derives from the shared cached current-run read
    (current_run_from_dcl) so tenant resolution and the status light never issue two
    separate runs fetches. Returns None if DCL is unreachable or has no runs (the
    caller decides whether that is fatal) — no silent fabrication of a tenant.
    """
    run = current_run_from_dcl()
    return (run.get("tenant_id") or None) if run else None


def get_tenant_id() -> Optional[str]:
    """Resolve the active tenant ID — NLQ mirrors DCL's current entity.

    Resolution order:
      1. DCL's most-recent ingest run (GET /api/dcl/triples/runs) — "whatever entity
         DCL shows is the entity NLQ shows". Re-evaluated every _TENANT_FOLLOW_TTL_S
         so a fresh pipeline run is reflected without a restart.
      2. AOS_TENANT_ID env var — FALLBACK only, used if DCL is unreachable and nothing
         was resolved before. It is no longer a pin; it just keeps NLQ alive when DCL
         is momentarily down.
      3. RuntimeError — no silent fallback.

    Call reset_tenant_cache() to clear (useful in tests).
    """
    global _tenant_id_cache, _tenant_cache_ts

    # 1. Follow DCL's current entity, with a short TTL so NLQ tracks new runs.
    now = time.monotonic()
    if _tenant_id_cache is not None and (now - _tenant_cache_ts) < _TENANT_FOLLOW_TTL_S:
        return _tenant_id_cache

    dcl_tid = _current_tenant_from_dcl()
    if dcl_tid:
        _tenant_id_cache, _tenant_cache_ts = dcl_tid, now
        return dcl_tid

    # DCL momentarily unreachable but we resolved before → keep serving the last
    # known current entity rather than flapping.
    if _tenant_id_cache is not None:
        return _tenant_id_cache

    # 2. Fallback: AOS_TENANT_ID (keeps NLQ usable if DCL is down at first call).
    env_tid = os.environ.get("AOS_TENANT_ID", "").strip()
    if env_tid:
        _config_logger.warning(
            "get_tenant_id: DCL unreachable; falling back to AOS_TENANT_ID env var."
        )
        return env_tid

    raise RuntimeError(
        "Cannot determine tenant_id: DCL "
        f"({os.environ.get('DCL_API_URL', '')}/api/dcl/triples/runs) returned no runs "
        "and AOS_TENANT_ID is unset. Run a pipeline so DCL has a current entity."
    )


def reset_tenant_cache() -> None:
    """Clear the cached tenant ID + current-run + entity index. For testing only."""
    global _tenant_id_cache, _tenant_cache_ts, _entity_index, _entity_index_ts
    global _current_run_cache, _current_run_cache_ts
    _tenant_id_cache, _tenant_cache_ts = None, 0.0
    _current_run_cache, _current_run_cache_ts = None, 0.0
    _entity_index, _entity_index_ts = None, 0.0


# ---------------------------------------------------------------------------
# DCL entity index — the nameable universe + each entity's tenant, one source
# ---------------------------------------------------------------------------
#
# get_tenant_id() answers "what entity does DCL show right now" — the default when
# a query names no entity. But NLQ also answers ANY named entity, and each entity
# (entity↔tenant 1:1, ContextOS) resolves to exactly one tenant: the one its
# CURRENT data lives under. This index is the single source for both the operator's
# entity list AND tenant-from-entity resolution, so the two can never disagree
# (entities[0] is always queryable under the tenant we'd resolve for it). NLQ never
# derives or string-mangles a tenant (I6); it reads the pairing DCL recorded.

_entity_index: Optional[list] = None  # list[tuple[entity_id, tenant_id, size]], richest first
_entity_index_ts: float = 0.0
# entity↔tenant is stable, so a longer TTL than the current-entity follow; still
# short enough that a newly-ingested entity becomes nameable within a minute.
_ENTITY_INDEX_TTL_S = 60.0


def _build_entity_index_from_dcl(dcl_url: Optional[str] = None) -> Optional[list]:
    """Build {entity → (tenant, current-data size)} from DCL's ACTIVE ingest runs.

    Runs come back most-recent-first. The first ACTIVE run that names an entity is
    its current data: that run's tenant is where the entity is queryable, and that
    run's size ranks the entity. Ranking by current-run size (not the raw is_active
    triple count) keeps stale, superseded "ghost" entities — flagged-active triples
    no longer in any current run — from dominating the list (a pre-rebuild dev-store
    artifact; see SCHEMA_CONTRACT.md "SE-path cutover readiness").

    dcl_url overrides the DCL_API_URL env target — so a registry constructed against
    a specific DCL (a test pointing at an unreachable one, a non-default deployment)
    reads from THAT DCL, not whatever the env happens to hold.

    Returns None if DCL is unreachable (the caller decides) — never a fabricated
    pairing. "combined" is skipped (not a single entity).
    """
    import httpx

    url = (dcl_url or os.environ.get("DCL_API_URL", "")).rstrip("/")
    if not url:
        return None
    try:
        resp = httpx.get(f"{url}/api/dcl/triples/runs", timeout=5.0)
        resp.raise_for_status()
        runs = resp.json().get("runs", [])
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    seen: dict = {}
    for run in runs:
        if not run.get("is_active"):
            continue
        tid = run.get("tenant_id")
        if not tid:
            continue
        size = run.get("triple_count") or 0
        for eid in (run.get("entity_summary") or {}):
            if eid and eid != "combined" and eid not in seen:
                seen[eid] = (tid, size)
    ranked = sorted(seen.items(), key=lambda kv: -kv[1][1])
    return [(eid, tid, size) for eid, (tid, size) in ranked]


def _get_entity_index() -> list:
    """Cached accessor for the DCL entity index. Empty list if DCL never resolved."""
    global _entity_index, _entity_index_ts
    now = time.monotonic()
    if _entity_index is None or (now - _entity_index_ts) >= _ENTITY_INDEX_TTL_S:
        idx = _build_entity_index_from_dcl()
        if idx is not None:
            _entity_index, _entity_index_ts = idx, now
    return _entity_index or []


def tenant_for_entity(entity_id: Optional[str]) -> Optional[str]:
    """Resolve a named entity's tenant — "NLQ answers any named entity".

    Returns the tenant the entity's CURRENT data lives under (entity↔tenant 1:1),
    from the same active-run index that backs the entity list. Returns None when:
      - entity_id is empty or "combined" (caller uses the DCL-current default via
        get_tenant_id() instead), or
      - the entity has no current data in DCL / DCL is unreachable — the caller
        fails loud (the /query boundary 422s) rather than silently scoping to
        another tenant's data (A1).

    Refreshes once on a miss so a just-ingested entity resolves without waiting out
    the TTL.
    """
    if not entity_id or entity_id == "combined":
        return None
    for eid, tid, _ in _get_entity_index():
        if eid == entity_id:
            return tid
    # Miss → the entity may have been ingested since the last refresh. One fresh
    # build before giving up (still None if genuinely unknown).
    idx = _build_entity_index_from_dcl()
    if idx is not None:
        global _entity_index, _entity_index_ts
        _entity_index, _entity_index_ts = idx, time.monotonic()
        for eid, tid, _ in idx:
            if eid == entity_id:
                return tid
    return None


def dcl_entities_ranked(dcl_url: Optional[str] = None) -> list:
    """[(entity_id, tenant_id)] for every entity DCL can currently answer, richest
    first — the nameable universe and each entity's tenant from one source, so the
    entity list and tenant-from-entity resolution can never disagree. Empty list if
    DCL is unreachable (the caller fails loud rather than serving a stale roster).

    dcl_url targets a specific DCL. When it is None or matches the env default, the
    shared cached index is used (the same one tenant_for_entity reads). A non-default
    url does a fresh, uncached build against THAT DCL — so a registry pointed at an
    unreachable DCL gets an empty roster (and fails loud), not the env DCL's data."""
    default = os.environ.get("DCL_API_URL", "").rstrip("/")
    if not dcl_url or dcl_url.rstrip("/") == default:
        return [(eid, tid) for eid, tid, _ in _get_entity_index()]
    idx = _build_entity_index_from_dcl(dcl_url) or []
    return [(eid, tid) for eid, tid, _ in idx]


def tenant_for_query(entity_id: Optional[str]) -> Optional[str]:
    """The tenant a single entity-scoped DCL read should use — the ONE rule applied
    everywhere NLQ browses for an entity (query path, dashboard breakdowns, etc.):

      - entity named → that entity's tenant (1:1), so its data is visible no matter
        which entity DCL currently shows;
      - none named → DCL's current entity (get_tenant_id()).

    A None return is only possible for a named-but-unknown entity, and the caller
    treats that as fail-loud, never a silent scope to the current tenant's data (A1).
    (Multi-entity batches can't use this — they group entities by tenant themselves.)
    """
    return tenant_for_entity(entity_id) if entity_id else get_tenant_id()


def get_available_snapshots() -> list:
    """Fetch available DCL snapshots for the current tenant.

    Calls GET {DCL_API_URL}/api/dcl/snapshots?tenant_id={tenant_id}.
    Returns list of snapshot dicts with dcl_ingest_id, snapshot_name,
    run_timestamp, total_rows, is_current.

    Raises RuntimeError if DCL_API_URL is not set or tenant_id is missing.
    Raises ConnectionError if DCL is unreachable.
    """
    import httpx

    dcl_url = os.environ.get("DCL_API_URL", "").rstrip("/")
    if not dcl_url:
        raise RuntimeError(
            "DCL_API_URL is not configured — cannot fetch snapshots. "
            "Set DCL_API_URL in environment or render.yaml."
        )

    tenant_id = get_tenant_id()
    if not tenant_id:
        raise RuntimeError(
            "Cannot fetch snapshots — tenant_id is not configured. "
            "Set AOS_TENANT_ID in environment."
        )

    url = f"{dcl_url}/api/dcl/snapshots"
    try:
        resp = httpx.get(url, params={"tenant_id": tenant_id}, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("snapshots", [])
    except httpx.ConnectError as e:
        raise ConnectionError(
            f"DCL unreachable at {url} — cannot fetch snapshots: {e}"
        ) from e
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"DCL returned {e.response.status_code} for snapshots: {e.response.text}"
        ) from e


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Required — reads bare ANTHROPIC_API_KEY (no NLQ_ prefix) to match
    # render.yaml and direct os.environ.get() call sites in llm/client.py.
    anthropic_api_key: str = Field(
        ...,
        validation_alias="ANTHROPIC_API_KEY",
        description="Anthropic API key for Claude"
    )

    # Optional with defaults
    reference_date: Optional[date] = Field(
        default=None,
        description="Reference date for relative period resolution. Defaults to today."
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )

    api_host: str = Field(
        default="0.0.0.0",
        description="API host to bind to"
    )

    api_port: int = Field(
        default=8000,
        description="API port to listen on"
    )

    # Paths
    test_questions_path: str = Field(
        default="data/nlq_test_questions.json",
        description="Path to the test questions JSON file"
    )

    class Config:
        env_prefix = "NLQ_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
