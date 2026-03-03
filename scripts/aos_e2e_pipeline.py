#!/usr/bin/env python3
"""
AOS E2E Pipeline Orchestrator
==============================
Runs the full Farm -> AOD -> AAM -> DCL -> NLQ pipeline end-to-end.
Each step runs sequentially, blocks until complete, and fails loud
with the exact step name and error if anything breaks.

Sequence:
  1. Health-check all modules (Farm, AOD, AAM, DCL, NLQ)
  2. Farm    -- POST /api/snapshots  (generate snapshot)
  3. AOD     -- POST /api/runs/from-farm  (discovery)
  4. AOD->AAM bridge  (fetch manifest, send to AAM)
  5. AAM     -- POST /api/aam/infer  (create pipes)
  6. AAM     -- POST /api/export/dcl/push  (push schemas to DCL)
  7. AAM     -- POST /api/export/dcl/dispatch  (dispatch ingest)
  8. AAM     -- POST /api/runners/dispatch-batch + poll progress
  9. NLQ     -- POST /api/v1/query  ("What is ARR?")
 10. Open DCL frontend in browser

Usage:
  python scripts/aos_e2e_pipeline.py
  python scripts/aos_e2e_pipeline.py --tenant-id <uuid>
  python scripts/aos_e2e_pipeline.py --nlq-url http://my-nlq:8005

Environment variables (override defaults):
  AOS_FARM_URL   default http://localhost:8003
  AOS_AOD_URL    default http://localhost:8001
  AOS_AAM_URL    default http://localhost:8002
  AOS_DCL_URL    default http://localhost:8004  (also reads DCL_API_URL)
  AOS_NLQ_URL    default http://localhost:8005
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env from every module repo (first-write wins, shell env wins over all)
# ---------------------------------------------------------------------------
# Works from both locations:
#   C:\Users\ilyac\code\aos_e2e.py              -> parent IS code dir
#   C:\Users\ilyac\code\AOS-NLQ\scripts\*.py    -> parent.parent.parent is code dir
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR / "ecosystem.config.js").exists():
    _CODE_DIR = _SCRIPT_DIR                         # running from code root
else:
    _CODE_DIR = _SCRIPT_DIR.parent.parent           # running from AOS-NLQ/scripts/
_MODULE_DIRS = ["AOS-NLQ", "AODv3", "AOS_AAM", "AOS-Farm", "AOS-DCLv2"]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            # Don't overwrite env vars already set by the shell or a previous .env
            if key not in os.environ:
                os.environ[key] = val


for _mod in _MODULE_DIRS:
    _load_dotenv(_CODE_DIR / _mod / ".env")

# ---------------------------------------------------------------------------
# httpx import  (project dependency -- pip install httpx if missing)
# ---------------------------------------------------------------------------
try:
    import httpx
except ImportError:
    sys.exit(
        "ERROR: httpx is not installed. "
        "Run:  pip install httpx   (it's already a project dependency)"
    )

# ---------------------------------------------------------------------------
# Module URL configuration
# Priority: CLI arg  >  AOS_*_URL env  >  module-specific env  >  default
# ---------------------------------------------------------------------------
LOCAL_URLS: dict[str, str] = {
    "farm": "http://localhost:8003",
    "aod": "http://localhost:8001",
    "aam": "http://localhost:8002",
    "dcl": os.environ.get("DCL_API_URL", "http://localhost:8004"),
    "nlq": "http://localhost:8005",
}

RENDER_URLS: dict[str, str] = {
    "farm": "https://farmv2.onrender.com",
    "aod": "https://aodv3-1.onrender.com",
    "aam": "https://aos-aam.onrender.com",
    "dcl": "https://aos-dclv2.onrender.com",
    "nlq": "https://aos-nlq.onrender.com",
}


def _resolve_urls(args: argparse.Namespace) -> dict[str, str]:
    """Build final URL map from CLI args > env vars > --deployed > defaults."""
    base = RENDER_URLS if getattr(args, "deployed", False) else LOCAL_URLS
    urls: dict[str, str] = {}
    for mod in ("farm", "aod", "aam", "dcl", "nlq"):
        cli_val = getattr(args, f"{mod}_url", None)
        env_val = os.environ.get(f"AOS_{mod.upper()}_URL")
        urls[mod] = (cli_val or env_val or base[mod]).rstrip("/")
    return urls


# ---------------------------------------------------------------------------
# Terminal colours (ANSI -- works on Win 10+ PowerShell and all Unix terms)
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    os.system("")  # enable ANSI escape processing on Windows


class _C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Logging & step tracking
# ---------------------------------------------------------------------------
_steps: list[dict] = []


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log(msg: str, color: str = _C.RESET) -> None:
    print(f"{_C.DIM}[{_ts()}]{_C.RESET} {color}{msg}{_C.RESET}", flush=True)


def _step_start(label: str) -> float:
    _log(f"{'-' * 64}", _C.DIM)
    _log(f">>  {label}", _C.CYAN + _C.BOLD)
    return time.time()


def _step_pass(label: str, t0: float, detail: str = "") -> None:
    elapsed = time.time() - t0
    _steps.append({"name": label, "status": "PASS", "elapsed": elapsed})
    suffix = f" -- {detail}" if detail else ""
    _log(f"[OK]  {label}  ({elapsed:.1f}s){suffix}", _C.GREEN)


def _step_fail(label: str, t0: float, error: str) -> None:
    elapsed = time.time() - t0
    _steps.append({"name": label, "status": "FAIL", "elapsed": elapsed, "error": error})
    _log(f"[FAIL]  {label}  ({elapsed:.1f}s)", _C.RED + _C.BOLD)
    _log(f"   ERROR: {error}", _C.RED)
    _print_summary()
    sys.exit(1)


def _print_summary() -> None:
    _log(f"\n{'=' * 64}", _C.BOLD)
    _log("PIPELINE SUMMARY", _C.CYAN + _C.BOLD)
    _log(f"{'=' * 64}", _C.BOLD)
    total_s = sum(s["elapsed"] for s in _steps)
    for s in _steps:
        ok = s["status"] == "PASS"
        icon = "[OK]" if ok else "[FAIL]"
        color = _C.GREEN if ok else _C.RED
        _log(f"  {icon:6s}  {s['name']:<46} {s['elapsed']:6.1f}s  {s['status']}", color)
    _log(f"{'-' * 64}", _C.DIM)
    passed = sum(1 for s in _steps if s["status"] == "PASS")
    failed = sum(1 for s in _steps if s["status"] == "FAIL")
    result_color = _C.GREEN if failed == 0 else _C.RED
    _log(
        f"  Total: {total_s:.1f}s  |  Passed: {passed}  |  Failed: {failed}",
        result_color,
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
# Module API keys -- read from env, injected as headers on matching requests.
# AOD requires X-API-Key on all /api/* routes when AOD_API_KEY is set.
_MODULE_AUTH: dict[str, dict[str, str]] = {}

_aod_key = os.environ.get("AOD_API_KEY", "")
if _aod_key:
    _MODULE_AUTH["aod"] = {"X-API-Key": _aod_key}


def _headers_for(url: str, urls: dict[str, str]) -> dict[str, str]:
    """Return auth headers if the URL belongs to a module that needs them."""
    for mod, auth in _MODULE_AUTH.items():
        base = urls.get(mod, "")
        if base and url.startswith(base):
            return dict(auth)
    return {}


def _post(
    client: httpx.Client,
    url: str,
    *,
    json_body: dict | None = None,
    timeout: float = 60,
    urls: dict[str, str] | None = None,
) -> httpx.Response:
    hdrs = _headers_for(url, urls or {})
    return client.post(url, json=json_body or {}, headers=hdrs, timeout=timeout)


def _get(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 30,
    urls: dict[str, str] | None = None,
) -> httpx.Response:
    hdrs = _headers_for(url, urls or {})
    return client.get(url, params=params, headers=hdrs, timeout=timeout)


def _body_preview(r: httpx.Response, limit: int = 600) -> str:
    """Truncated response text for error messages."""
    txt = r.text[:limit]
    if len(r.text) > limit:
        txt += "..."
    return txt


# =========================================================================
# PIPELINE STEPS
# =========================================================================

def step_01_health(client: httpx.Client, urls: dict[str, str]) -> None:
    """Health-check every module. Stop immediately if any are down."""
    label = "1. Health Check All Modules"
    t0 = _step_start(label)

    health_endpoints = {
        "Farm": f"{urls['farm']}/api/health",
        "AOD":  f"{urls['aod']}/health",       # root /health -- no auth required
        "AAM":  f"{urls['aam']}/api/health",
        "DCL":  f"{urls['dcl']}/api/health",
        "NLQ":  f"{urls['nlq']}/api/v1/health",
    }

    down: list[str] = []
    for module, endpoint in health_endpoints.items():
        try:
            r = _get(client, endpoint, timeout=10, urls=urls)
            if r.status_code >= 400:
                down.append(f"{module} -> {endpoint} -> HTTP {r.status_code}")
            else:
                _log(f"   {module:6s}  healthy", _C.GREEN)
        except httpx.ConnectError:
            down.append(f"{module} -> {endpoint} -> connection refused (is the service running?)")
        except httpx.TimeoutException:
            down.append(f"{module} -> {endpoint} -> timed out after 10s")
        except Exception as exc:
            down.append(f"{module} -> {endpoint} -> {exc}")

    if down:
        _step_fail(label, t0, "Modules DOWN:\n      " + "\n      ".join(down))

    _step_pass(label, t0, "all 5 modules healthy")


def step_02_farm_snapshot(
    client: httpx.Client, urls: dict[str, str], tenant_id: str,
) -> str:
    """Generate a Farm snapshot with medium scale. Returns snapshot_id."""
    label = "2. Farm -- Generate Snapshot"
    t0 = _step_start(label)

    if not tenant_id:
        _step_fail(
            label, t0,
            "tenant_id is required by Farm but was empty. "
            "Set NLQ_DEFAULT_TENANT_ID in your .env or pass --tenant-id.",
        )

    payload: dict = {"scale": "medium", "tenant_id": tenant_id}

    try:
        r = _post(client, f"{urls['farm']}/api/snapshots", json_body=payload, timeout=180, urls=urls)
    except httpx.TimeoutException:
        _step_fail(label, t0, f"POST {urls['farm']}/api/snapshots timed out after 180s")
        return ""  # unreachable -- _step_fail exits
    except Exception as exc:
        _step_fail(label, t0, f"POST {urls['farm']}/api/snapshots failed: {exc}")
        return ""

    if r.status_code >= 400:
        _step_fail(label, t0, f"HTTP {r.status_code} from Farm: {_body_preview(r)}")

    data = r.json()
    snapshot_id = data.get("snapshot_id", "")
    if not snapshot_id:
        _step_fail(label, t0, f"No snapshot_id in response: {json.dumps(data)[:500]}")

    dup = data.get("duplicate_of_snapshot_id")
    extra = f" (reused existing {dup})" if dup else ""
    _step_pass(label, t0, f"snapshot_id={snapshot_id}{extra}")
    return snapshot_id


def step_03_aod_discovery(
    client: httpx.Client, urls: dict[str, str], snapshot_id: str, tenant_id: str,
) -> str:
    """Run AOD discovery against the Farm snapshot. Returns run_id."""
    label = "3. AOD -- Discovery from Farm"
    t0 = _step_start(label)

    payload = {
        "snapshot_id": snapshot_id,
        "farm_base_url": urls["farm"],
        "tenant_id": tenant_id,
    }

    try:
        r = _post(client, f"{urls['aod']}/api/runs/from-farm", json_body=payload, timeout=180, urls=urls)
    except httpx.TimeoutException:
        _step_fail(label, t0, f"POST {urls['aod']}/api/runs/from-farm timed out after 180s")
        return ""
    except Exception as exc:
        _step_fail(label, t0, f"POST {urls['aod']}/api/runs/from-farm failed: {exc}")
        return ""

    if r.status_code >= 400:
        _step_fail(label, t0, f"HTTP {r.status_code} from AOD: {_body_preview(r)}")

    data = r.json()
    run_id = data.get("run_id", "")
    if not run_id:
        _step_fail(label, t0, f"No run_id in response: {json.dumps(data)[:500]}")

    status = data.get("status", "unknown")
    assets = data.get("counts", {}).get("assets_admitted", "?")
    _step_pass(label, t0, f"run_id={run_id}  status={status}  assets_admitted={assets}")
    return run_id


def step_04_aod_aam_bridge(
    client: httpx.Client, urls: dict[str, str], run_id: str,
) -> None:
    """Tell AOD to export candidates + fabric planes + SORs to AAM.

    Uses POST /api/handoff/aam/export which:
      - Formats AOD assets into AAM's expected candidate schema
      - Includes fabric planes and SOR declarations from Farm metadata
      - POSTs the full payload to AAM's /api/handoff/aod/receive internally
    Requires AAM_URL configured on the AOD service.
    """
    label = "4. AOD -> AAM Export"
    t0 = _step_start(label)

    try:
        # run_id is a query parameter, not body
        hdrs = _headers_for(f"{urls['aod']}/api/handoff/aam/export", urls)
        r = client.post(
            f"{urls['aod']}/api/handoff/aam/export",
            params={"run_id": run_id},
            headers=hdrs,
            timeout=60,
        )
    except Exception as exc:
        _step_fail(label, t0, f"POST /api/handoff/aam/export failed: {exc}")
        return

    if r.status_code >= 400:
        _step_fail(label, t0, f"HTTP {r.status_code}: {_body_preview(r)}")

    data = r.json()
    sent = data.get("candidates_sent", "?")
    success = data.get("success", False)
    aam_resp = data.get("aam_response", {})
    accepted = aam_resp.get("candidates_accepted", "?") if isinstance(aam_resp, dict) else "?"

    if not success:
        _step_fail(label, t0, f"AOD export reported failure: {data.get('message', 'unknown')}")

    _step_pass(label, t0, f"{sent} candidates sent -> {accepted} accepted by AAM")


def step_05_aam_infer(client: httpx.Client, urls: dict[str, str]) -> None:
    """AAM pipe inference -- creates pipe blueprints from accepted candidates."""
    label = "5. AAM -- Infer Pipes"
    t0 = _step_start(label)

    try:
        r = _post(client, f"{urls['aam']}/api/aam/infer", timeout=60, urls=urls)
    except Exception as exc:
        _step_fail(label, t0, f"POST /api/aam/infer failed: {exc}")
        return

    if r.status_code >= 400:
        _step_fail(label, t0, f"HTTP {r.status_code}: {_body_preview(r)}")

    data = r.json()
    pipes = data.get("pipes_created", "?")
    _step_pass(label, t0, f"{pipes} pipes created")


def step_06_aam_dcl_push(client: httpx.Client, urls: dict[str, str]) -> None:
    """Push pipe schemas from AAM to DCL."""
    label = "6. AAM -- Push to DCL"
    t0 = _step_start(label)

    try:
        r = _post(client, f"{urls['aam']}/api/export/dcl/push", timeout=60, urls=urls)
    except Exception as exc:
        _step_fail(label, t0, f"POST /api/export/dcl/push failed: {exc}")
        return

    if r.status_code >= 400:
        _step_fail(label, t0, f"HTTP {r.status_code}: {_body_preview(r)}")

    data = r.json()
    dcl_ok = data.get("dcl_accepted")

    # Surface full response on failure for diagnosis
    if dcl_ok is False:
        delivery = data.get("delivery", {})
        dcl_body = delivery.get("body", "") if isinstance(delivery, dict) else ""
        _step_fail(
            label, t0,
            f"DCL rejected pipe push (dcl_accepted=False). "
            f"Response: {json.dumps(data)[:600]}",
        )

    detail = f"dcl_accepted={dcl_ok}" if dcl_ok is not None else json.dumps(data)[:200]
    _step_pass(label, t0, detail)


def step_07_aam_dcl_dispatch(client: httpx.Client, urls: dict[str, str]) -> None:
    """Dispatch ingest rows from AAM to DCL."""
    label = "7. AAM -- Dispatch to DCL"
    t0 = _step_start(label)

    try:
        r = _post(client, f"{urls['aam']}/api/export/dcl/dispatch", timeout=60, urls=urls)
    except Exception as exc:
        _step_fail(label, t0, f"POST /api/export/dcl/dispatch failed: {exc}")
        return

    if r.status_code >= 400:
        _step_fail(label, t0, f"HTTP {r.status_code}: {_body_preview(r)}")

    data = r.json()
    dispatch = data.get("dispatch", {})
    dispatch_ok = dispatch.get("ok") if isinstance(dispatch, dict) else None
    detail = f"ok={dispatch_ok}" if dispatch_ok is not None else json.dumps(data)[:200]
    _step_pass(label, t0, detail)


def step_08_aam_runners(client: httpx.Client, urls: dict[str, str]) -> None:
    """Dispatch runner batch, then poll progress until all jobs complete."""
    label = "8. AAM -- Dispatch & Run Batch"
    t0 = _step_start(label)

    # 8a -- get pipe IDs from AAM
    _log("   Fetching pipe list from AAM...", _C.DIM)
    try:
        r = _get(client, f"{urls['aam']}/api/pipes", timeout=15, urls=urls)
        if r.status_code >= 400:
            _step_fail(label, t0, f"GET /api/aam/pipes HTTP {r.status_code}: {_body_preview(r)}")
            return
        pipes_data = r.json()
        # Handle both list-of-dicts and other shapes
        if isinstance(pipes_data, list):
            pipe_ids = [
                p.get("pipe_id") or p.get("id", "")
                for p in pipes_data
                if isinstance(p, dict)
            ]
            pipe_ids = [pid for pid in pipe_ids if pid]
        elif isinstance(pipes_data, dict) and "pipes" in pipes_data:
            pipe_ids = [
                p.get("pipe_id") or p.get("id", "")
                for p in pipes_data["pipes"]
                if isinstance(p, dict)
            ]
            pipe_ids = [pid for pid in pipe_ids if pid]
        else:
            pipe_ids = []
    except Exception as exc:
        _step_fail(label, t0, f"GET /api/aam/pipes failed: {exc}")
        return

    if not pipe_ids:
        _step_fail(label, t0, "No pipes found in AAM -- nothing to dispatch")
        return

    _log(f"   Found {len(pipe_ids)} pipes to dispatch", _C.CYAN)

    # 8b -- dispatch batch
    _log("   Dispatching batch...", _C.DIM)
    try:
        r = _post(
            client,
            f"{urls['aam']}/api/runners/dispatch-batch",
            json_body={"pipe_ids": pipe_ids, "trigger": "e2e_pipeline"},
            timeout=300,
            urls=urls,
        )
    except Exception as exc:
        _step_fail(label, t0, f"POST /api/runners/dispatch-batch failed: {exc}")
        return

    if r.status_code >= 400:
        _step_fail(label, t0, f"dispatch-batch HTTP {r.status_code}: {_body_preview(r)}")

    dispatch_data = r.json()
    dispatched = dispatch_data.get("dispatched", "?")
    skipped = dispatch_data.get("skipped", 0)
    _log(f"   Dispatched: {dispatched}  Skipped: {skipped}", _C.CYAN)

    # 8c -- poll progress every 2s, timeout 120s
    _log("   Polling runner progress...", _C.DIM)
    deadline = time.time() + 120
    last_log = 0.0

    while time.time() < deadline:
        try:
            r = _get(client, f"{urls['aam']}/api/runners/progress", timeout=10, urls=urls)
            if r.status_code >= 400:
                _log(f"   Progress poll HTTP {r.status_code}", _C.YELLOW)
                time.sleep(2)
                continue
            prog = r.json()
        except Exception as exc:
            _log(f"   Progress poll error: {exc}", _C.YELLOW)
            time.sleep(2)
            continue

        completed = prog.get("completed", 0)
        failed = prog.get("failed", 0)
        running = prog.get("running", 0)
        queued = prog.get("queued", 0)
        dispatched_n = prog.get("dispatched", 0)
        still_active = running + queued + dispatched_n

        # Log at most once per 4s to avoid spam
        now = time.time()
        if now - last_log >= 4:
            _log(
                f"   completed={completed}  running={running}  "
                f"queued={queued}  failed={failed}",
                _C.DIM,
            )
            last_log = now

        if still_active == 0 and (completed > 0 or failed > 0):
            if failed > 0:
                _step_fail(
                    label, t0,
                    f"{failed} runner jobs FAILED (completed={completed}). "
                    f"Check GET {urls['aam']}/api/runners/jobs?status=failed for details.",
                )
            _step_pass(label, t0, f"{completed} jobs completed, {failed} failed")
            return

        time.sleep(2)

    # Timed out
    _step_fail(
        label, t0,
        f"Runner progress poll timed out after 120s. "
        f"Last state: completed={completed} running={running} "
        f"queued={queued} failed={failed}",
    )


def step_09_nlq_test(client: httpx.Client, urls: dict[str, str]) -> None:
    """Fire a test NLQ query to verify the full chain end-to-end."""
    label = "9. NLQ -- Test Query"
    t0 = _step_start(label)

    payload = {
        "question": "What is ARR?",
        "data_mode": "live",
    }

    try:
        r = _post(client, f"{urls['nlq']}/api/v1/query", json_body=payload, timeout=30, urls=urls)
    except Exception as exc:
        _step_fail(label, t0, f"POST /api/v1/query failed: {exc}")
        return

    if r.status_code >= 400:
        _step_fail(label, t0, f"HTTP {r.status_code}: {_body_preview(r)}")

    data = r.json()
    source = data.get("data_source", "unknown")
    value = data.get("value")
    answer = data.get("answer", "")
    metric = data.get("resolved_metric", "")

    # Reject silent fallbacks -- the whole point of this pipeline
    if source in ("local_fallback", "demo", "local"):
        _step_fail(
            label, t0,
            f"NLQ returned data_source='{source}' -- the DCL chain is broken. "
            f"Expected 'dcl' or 'live'. Full chain must be verified.",
        )

    detail_parts = [f"source={source}"]
    if metric:
        detail_parts.append(f"metric={metric}")
    if value is not None:
        unit = data.get("unit", "")
        detail_parts.append(f"value={value} {unit}".strip())
    else:
        detail_parts.append(f"answer={answer[:80]}")

    _step_pass(label, t0, "  ".join(detail_parts))


def step_10_open_dcl(urls: dict[str, str]) -> None:
    """Open the DCL frontend in the default browser."""
    label = "10. Open DCL Recon Tab"
    t0 = _step_start(label)

    # DCL frontend runs on port 3004 in local dev (backend is 8004)
    # Derive frontend URL: if backend is localhost:8004, frontend is localhost:3004
    dcl_backend = urls["dcl"]
    if "localhost:8004" in dcl_backend or "127.0.0.1:8004" in dcl_backend:
        dcl_frontend = dcl_backend.replace(":8004", ":3004")
    else:
        # Render or custom -- use the backend URL (serves frontend too)
        dcl_frontend = dcl_backend

    try:
        webbrowser.open(dcl_frontend)
        _step_pass(label, t0, f"opened {dcl_frontend}")
    except Exception as exc:
        _step_fail(label, t0, f"Could not open browser: {exc}")


# =========================================================================
# MAIN
# =========================================================================

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AOS E2E Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--deployed", action="store_true",
                    help="Use Render (production) URLs instead of localhost")
    p.add_argument("--tenant-id", default=os.environ.get("NLQ_DEFAULT_TENANT_ID", ""),
                    help="Tenant UUID (default: from NLQ_DEFAULT_TENANT_ID env var)")
    p.add_argument("--farm-url", default=None, help="Override Farm base URL")
    p.add_argument("--aod-url", default=None, help="Override AOD base URL")
    p.add_argument("--aam-url", default=None, help="Override AAM base URL")
    p.add_argument("--dcl-url", default=None, help="Override DCL base URL")
    p.add_argument("--nlq-url", default=None, help="Override NLQ base URL")
    p.add_argument("--no-browser", action="store_true",
                    help="Skip opening browser at the end")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    urls = _resolve_urls(args)
    tenant_id: str = args.tenant_id

    mode_label = "DEPLOYED (Render)" if args.deployed else "LOCAL"
    _log(f"\n{'=' * 64}", _C.BOLD)
    _log(f"AOS  E2E  PIPELINE  ORCHESTRATOR  [{mode_label}]", _C.BOLD + _C.CYAN)
    _log(f"{'=' * 64}", _C.BOLD)
    _log(f"  Farm : {urls['farm']}", _C.DIM)
    _log(f"  AOD  : {urls['aod']}", _C.DIM)
    _log(f"  AAM  : {urls['aam']}", _C.DIM)
    _log(f"  DCL  : {urls['dcl']}", _C.DIM)
    _log(f"  NLQ  : {urls['nlq']}", _C.DIM)
    if tenant_id:
        _log(f"  Tenant: {tenant_id}", _C.DIM)
    if _aod_key:
        _log(f"  AOD API Key: configured", _C.DIM)
    _log(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", _C.DIM)

    client = httpx.Client()

    try:
        step_01_health(client, urls)
        snapshot_id = step_02_farm_snapshot(client, urls, tenant_id)
        run_id = step_03_aod_discovery(client, urls, snapshot_id, tenant_id)
        step_04_aod_aam_bridge(client, urls, run_id)
        step_05_aam_infer(client, urls)
        step_06_aam_dcl_push(client, urls)
        step_07_aam_dcl_dispatch(client, urls)
        step_08_aam_runners(client, urls)
        step_09_nlq_test(client, urls)

        if not args.no_browser:
            step_10_open_dcl(urls)
        else:
            _steps.append({"name": "10. Open DCL Recon Tab", "status": "PASS", "elapsed": 0.0})
            _log("   Skipped (--no-browser)", _C.DIM)

    finally:
        client.close()

    _print_summary()
    _log(f"\n{'=' * 64}", _C.BOLD)
    _log("PIPELINE COMPLETE", _C.GREEN + _C.BOLD)
    _log(f"{'=' * 64}\n", _C.BOLD)


if __name__ == "__main__":
    main()
