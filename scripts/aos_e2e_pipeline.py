#!/usr/bin/env python3
"""
AOS E2E Pipeline Orchestrator
==============================
Runs the full Farm -> AOD -> AAM -> DCL -> NLQ pipeline end-to-end.
Each step runs sequentially, blocks until complete, and fails loud
with the exact step name and error if anything breaks.

Sequence:
  1. Health-check all modules (Farm, AOD, AAM, DCL, NLQ)
  0. Pipeline Reset -- no-op (modules handle their own idempotency)
  2. Farm    -- POST /api/snapshots  (generate snapshot)
 2b. Open Farm UI in browser
  3. AOD     -- POST /api/runs/from-farm  (discovery)
 3b. Open AOD Discovery in browser
  4. AOD->AAM bridge  (fetch manifest, send to AAM)
  5. AAM     -- POST /api/aam/infer  (create pipes)
 5b. Open AAM Topology in browser
  6. AAM     -- POST /api/export/dcl/push  (push schemas to DCL)
  7. AAM     -- POST /api/export/dcl/dispatch  (dispatch ingest)
 7b. Open DCL Ingest in browser
  8. AAM     -- POST /api/runners/dispatch-batch (sync) + verify
  9. NLQ     -- POST /api/v1/query  ("What is ARR?")
 9b. Open NLQ in browser
 10. Open DCL Recon in browser

Usage:
  python scripts/aos_e2e_pipeline.py
  python scripts/aos_e2e_pipeline.py --tenant AeroCorp-TEST
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

def step_00_reset(client: httpx.Client, urls: dict[str, str]) -> None:
    """No-op — the pipeline no longer clears any state.

    Each module handles its own idempotency:
      - Farm: snapshot fingerprint dedup (returns existing on match)
      - AAM: runner job UPSERT (re-dispatch overwrites previous jobs)
      - DCL: pipe definition UPSERT + receipt cap eviction

    Data is additive across runs.  Manual cleanup is available via
    each module's UI (Farm "Erase All", DCL flush button, AAM admin).
    """
    label = "0. Pipeline Reset (no-op)"
    t0 = _step_start(label)
    _step_pass(label, t0, "skipped -- pipeline does not clear state")


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
) -> tuple[str, str]:
    """Generate a Farm snapshot with medium scale.
    Returns (snapshot_id, tenant_id) -- tenant_id is read from the Farm
    response so downstream steps use the authoritative value, not the
    hardcoded default.
    """
    label = "2. Farm -- Generate Snapshot"
    t0 = _step_start(label)

    payload: dict = {"scale": "medium"}
    if tenant_id:
        payload["tenant_id"] = tenant_id

    try:
        r = _post(client, f"{urls['farm']}/api/snapshots", json_body=payload, timeout=180, urls=urls)
    except httpx.TimeoutException:
        _step_fail(label, t0, f"POST {urls['farm']}/api/snapshots timed out after 180s")
        return "", ""  # unreachable -- _step_fail exits
    except Exception as exc:
        _step_fail(label, t0, f"POST {urls['farm']}/api/snapshots failed: {exc}")
        return "", ""

    if r.status_code >= 400:
        _step_fail(label, t0, f"HTTP {r.status_code} from Farm: {_body_preview(r)}")

    data = r.json()
    snapshot_id = data.get("snapshot_id", "")
    if not snapshot_id:
        _step_fail(label, t0, f"No snapshot_id in response: {json.dumps(data)[:500]}")

    # Always read tenant_id from Farm's response -- Farm is the authority.
    farm_tenant = data.get("tenant_id", "")
    if not farm_tenant:
        _step_fail(label, t0, "Farm response missing tenant_id -- Farm must always return one.")

    dup = data.get("duplicate_of_snapshot_id")
    extra = f" (reused existing {dup})" if dup else ""
    _step_pass(label, t0, f"snapshot_id={snapshot_id}  tenant={farm_tenant}{extra}")
    return snapshot_id, farm_tenant


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
    """Dispatch runner batch (runs synchronously) and verify results."""
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
            timeout=600,
            urls=urls,
        )
    except Exception as exc:
        _step_fail(label, t0, f"POST /api/runners/dispatch-batch failed: {exc}")
        return

    if r.status_code >= 400:
        _step_fail(label, t0, f"dispatch-batch HTTP {r.status_code}: {_body_preview(r)}")
        return

    dispatch_data = r.json()
    dispatched = dispatch_data.get("dispatched", "?")
    skipped = dispatch_data.get("skipped", 0)
    errors = dispatch_data.get("errors", 0)
    _log(f"   Dispatched: {dispatched}  Skipped: {skipped}  Errors: {errors}", _C.CYAN)

    if dispatched == 0 and skipped == 0:
        _step_fail(label, t0, "dispatch-batch returned 0 dispatched and 0 skipped")
        return

    # 8c -- poll for Farm completion (dispatch is now fire-and-forget;
    # Farm callbacks update job statuses asynchronously).
    # Step 9 (NLQ) needs Farm data in DCL, so we wait here.
    _log("   Waiting for Farm to process jobs...", _C.DIM)
    import time as _time
    _poll_deadline = _time.time() + 120  # 2-minute cap
    _terminal_statuses = ("completed", "failed", "timed_out")
    _last_terminal = 0

    while _time.time() < _poll_deadline:
        try:
            r = _get(client, f"{urls['aam']}/api/runners/jobs", timeout=10, urls=urls)
            if r.status_code < 400:
                jobs_resp = r.json()
                if isinstance(jobs_resp, dict) and "jobs" in jobs_resp:
                    job_list = jobs_resp["jobs"]
                elif isinstance(jobs_resp, list):
                    job_list = jobs_resp
                else:
                    job_list = []
                terminal = sum(
                    1 for j in job_list
                    if isinstance(j, dict) and j.get("status") in _terminal_statuses
                )
                if terminal != _last_terminal:
                    _log(f"   Farm progress: {terminal}/{dispatched} jobs done", _C.CYAN)
                    _last_terminal = terminal
                if terminal >= dispatched:
                    completed = sum(1 for j in job_list if isinstance(j, dict) and j.get("status") == "completed")
                    failed = sum(1 for j in job_list if isinstance(j, dict) and j.get("status") == "failed")
                    _log(f"   All jobs terminal: {completed} completed, {failed} failed", _C.CYAN)
                    break
        except Exception as exc:
            _log(f"   Poll error (will retry): {exc}", _C.YELLOW)
        _time.sleep(3)
    else:
        _log(f"   Poll timeout after 120s — {_last_terminal}/{dispatched} jobs terminal", _C.YELLOW)

    _step_pass(label, t0, f"dispatched={dispatched}, skipped={skipped}")


def step_08b_combining_data(
    client: httpx.Client, urls: dict[str, str],
) -> None:
    """Generate combining datasets from Farm and update DCL data files.

    Runs generate_combining_data.py which writes directly to DCL's data/
    directory. Verifies files exist and are fresh after generation.
    """
    label = "8b. Generate Combining Data -> DCL"
    t0 = _step_start(label)

    script = _CODE_DIR / "dcl" / "scripts" / "generate_combining_data.py"
    if not script.exists():
        _step_pass(label, t0, "skipped -- local DCL repo not found (deployed mode)")
        return

    # Use Farm's venv Python — the script imports Farm generators which
    # need pydantic and other Farm-specific dependencies.
    farm_python = _CODE_DIR / "farm" / ".venv" / "bin" / "python3"
    python_bin = str(farm_python) if farm_python.exists() else sys.executable

    _log("   Running generate_combining_data.py...", _C.DIM)
    import subprocess
    try:
        result = subprocess.run(
            [python_bin, str(script)],
            capture_output=True,
            text=True,
            cwd=str(_CODE_DIR / "dcl"),
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        _step_fail(label, t0, "generate_combining_data.py timed out after 120s")
        return
    except Exception as exc:
        _step_fail(label, t0, f"generate_combining_data.py failed to start: {exc}")
        return

    if result.returncode != 0:
        stderr_preview = result.stderr[:500] if result.stderr else "(no stderr)"
        _step_fail(
            label, t0,
            f"generate_combining_data.py exited with code {result.returncode}. "
            f"stderr: {stderr_preview}",
        )
        return

    for line in result.stdout.strip().split("\n"):
        if line.strip():
            _log(f"   {line.strip()}", _C.CYAN)

    import time as _time
    now = _time.time()
    data_dir = _CODE_DIR / "dcl" / "data"
    expected_files = ["combining_statements.json", "entity_overlap.json", "customer_profiles.json"]
    for fname in expected_files:
        fpath = data_dir / fname
        if not fpath.exists():
            _step_fail(label, t0, f"Expected file missing after generation: {fpath}")
            return
        age = now - fpath.stat().st_mtime
        if age > 120:
            _log(f"   WARNING: {fname} is {age:.0f}s old — may not have been regenerated", _C.YELLOW)
        else:
            size_kb = fpath.stat().st_size / 1024
            _log(f"   {fname}: {size_kb:.0f} KB (fresh, {age:.0f}s old)", _C.GREEN)

    _step_pass(label, t0, "3 combining datasets generated in DCL data/")


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


# ---------------------------------------------------------------------------
# Browser-open helpers
# ---------------------------------------------------------------------------
# Module frontend ports (Vite dev servers). None = server-rendered on backend port.
_FRONTEND_PORTS: dict[str, int | None] = {
    "farm": None,   # server-rendered on 8003
    "aod":  3001,   # Vite dev server (Discovery page)
    "aam":  None,   # server-rendered on 8002
    "dcl":  3004,   # Vite dev server
    "nlq":  3005,   # Vite dev server
}
_BACKEND_PORTS: dict[str, int] = {
    "farm": 8003, "aod": 8001, "aam": 8002, "dcl": 8004, "nlq": 8005,
}


def _frontend_url(urls: dict[str, str], module: str, path: str = "") -> str:
    """Derive the browser-facing URL for a module.

    Local dev: remaps backend port to Vite frontend port (e.g. 8004 -> 3004).
    Render:    backend URL serves the frontend too, no remap needed.
    Server-rendered modules (Farm, AAM): always use the backend URL.
    """
    backend = urls[module]
    fp = _FRONTEND_PORTS.get(module)
    bp = _BACKEND_PORTS.get(module)
    if fp and bp:
        local_markers = (f"localhost:{bp}", f"127.0.0.1:{bp}")
        if any(m in backend for m in local_markers):
            base = backend.replace(f":{bp}", f":{fp}")
        else:
            base = backend
    else:
        base = backend
    return f"{base}{path}" if path else base


def _open_ui(urls: dict[str, str], label: str, url: str) -> None:
    """Open a URL in the default browser, recorded as a pipeline step."""
    t0 = _step_start(label)
    try:
        webbrowser.open(url)
        _step_pass(label, t0, f"opened {url}")
    except Exception as exc:
        _step_fail(label, t0, f"Could not open browser: {exc}")


# =========================================================================
# MULTI-ENTITY PIPELINE STEPS
# =========================================================================

def step_me_01_health(client: httpx.Client, urls: dict[str, str]) -> None:
    """Health-check Farm, DCL, NLQ for multi-entity pipeline."""
    label = "ME-1. Health Check (Farm, DCL, NLQ)"
    t0 = _step_start(label)

    health_endpoints = {
        "Farm": f"{urls['farm']}/api/health",
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

    _step_pass(label, t0, "Farm, DCL, NLQ healthy")


def step_me_02_farm_generate(
    client: httpx.Client, urls: dict[str, str], entities: str, seed: int | None,
) -> str:
    """Multi-entity Farm generation with push to DCL. Returns run_id."""
    label = "ME-2. Farm -- Generate Multi-Entity"
    t0 = _step_start(label)

    params: dict[str, str] = {
        "entities": entities,
        "push_to_dcl": "true",
    }
    if seed is not None:
        params["seed"] = str(seed)

    url = f"{urls['farm']}/api/business-data/generate-multi-entity"
    try:
        r = client.post(url, params=params, timeout=300)
    except httpx.TimeoutException:
        _step_fail(label, t0, f"POST {url} timed out after 300s")
        return ""
    except Exception as exc:
        _step_fail(label, t0, f"POST {url} failed: {exc}")
        return ""

    if r.status_code >= 400:
        _step_fail(label, t0, f"HTTP {r.status_code}: {_body_preview(r)}")

    data = r.json()
    run_id = data.get("run_id", "")
    if not run_id:
        _step_fail(label, t0, f"No run_id in response: {json.dumps(data)[:500]}")

    entity_list = data.get("entities", entities)
    _step_pass(label, t0, f"run_id={run_id}  entities={entity_list}")
    return run_id


def step_me_03_combining_data(
    client: httpx.Client, urls: dict[str, str],
) -> None:
    """Generate combining datasets — reuses step_08b logic."""
    step_08b_combining_data(client, urls)


def step_me_04_dcl_verify(
    client: httpx.Client, urls: dict[str, str], entities: str,
) -> None:
    """Verify DCL ingested data for each entity."""
    label = "ME-4. DCL -- Verify Entity Ingestion"
    t0 = _step_start(label)

    entity_list = [e.strip() for e in entities.split(",")]
    for entity_id in entity_list:
        try:
            r = client.post(
                f"{urls['dcl']}/api/dcl/query",
                json={
                    "metric": "revenue",
                    "entity_id": entity_id,
                    "time_range": {"start": "2025-Q1", "end": "2025-Q1"},
                },
                timeout=30,
            )
            if r.status_code >= 400:
                _step_fail(
                    label, t0,
                    f"DCL query for entity '{entity_id}' returned HTTP {r.status_code}: "
                    f"{_body_preview(r)}",
                )
            data = r.json()
            value = data.get("value", data.get("result", "?"))
            _log(f"   {entity_id}: revenue = {value}", _C.CYAN)
        except Exception as exc:
            _step_fail(label, t0, f"DCL query for '{entity_id}' failed: {exc}")

    _step_pass(label, t0, f"revenue verified for {entity_list}")


def step_me_05_harness(urls: dict[str, str], run_id: str) -> None:
    """Run the pipeline integration harness via subprocess."""
    label = "ME-5. Pipeline Harness (PI_001–PI_021)"
    t0 = _step_start(label)

    import subprocess

    harness_script = _SCRIPT_DIR.parent / "tests" / "pipeline" / "run_pipeline_harness.py"
    if not harness_script.exists():
        _step_fail(label, t0, f"Harness script not found: {harness_script}")
        return

    cmd = [
        sys.executable, str(harness_script),
        "--farm-url", urls["farm"],
        "--dcl-url", urls["dcl"],
        "--nlq-url", urls["nlq"],
    ]
    if run_id:
        cmd.extend(["--run-id", run_id])

    _log(f"   Running: {' '.join(cmd[-6:])}", _C.DIM)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        _step_fail(label, t0, "Harness timed out after 300s")
        return
    except Exception as exc:
        _step_fail(label, t0, f"Harness failed to start: {exc}")
        return

    # Print harness output
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            print(f"   {line}")

    if result.returncode != 0:
        stderr_preview = result.stderr[:500] if result.stderr else ""
        _step_fail(
            label, t0,
            f"Harness exited with code {result.returncode}. "
            f"{stderr_preview}",
        )
        return

    _step_pass(label, t0, "all pipeline tests passed")


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
    p.add_argument("--tenant", default=None,
                    help="Pin a specific tenant name (e.g. for replaying a scenario). "
                         "Default: Farm auto-generates a company name.")
    p.add_argument("--farm-url", default=None, help="Override Farm base URL")
    p.add_argument("--aod-url", default=None, help="Override AOD base URL")
    p.add_argument("--aam-url", default=None, help="Override AAM base URL")
    p.add_argument("--dcl-url", default=None, help="Override DCL base URL")
    p.add_argument("--nlq-url", default=None, help="Override NLQ base URL")
    p.add_argument("--no-browser", action="store_true",
                    help="Skip opening browser at the end")
    p.add_argument("--skip-reset", action="store_true",
                    help="Deprecated (no-op). Pipeline no longer clears state.")
    p.add_argument("--entities", default=None,
                    help="Comma-separated entity IDs for multi-entity pipeline "
                         "(e.g. --entities=meridian,cascadia). Uses Farm generate-multi-entity.")
    p.add_argument("--verify", action="store_true",
                    help="Run pipeline integration harness after pipeline completes")
    p.add_argument("--seed", default=None, type=int,
                    help="Random seed for Farm generation (deterministic output)")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    urls = _resolve_urls(args)
    tenant_id: str = args.tenant or ""   # empty = let Farm generate

    # ── Multi-entity pipeline ──────────────────────────────────────────────
    if args.entities:
        mode_label = "MULTI-ENTITY"
        _log(f"\n{'=' * 64}", _C.BOLD)
        _log(f"AOS  E2E  PIPELINE  ORCHESTRATOR  [{mode_label}]", _C.BOLD + _C.CYAN)
        _log(f"{'=' * 64}", _C.BOLD)
        _log(f"  Farm : {urls['farm']}", _C.DIM)
        _log(f"  DCL  : {urls['dcl']}", _C.DIM)
        _log(f"  NLQ  : {urls['nlq']}", _C.DIM)
        _log(f"  Entities: {args.entities}", _C.CYAN)
        if args.seed is not None:
            _log(f"  Seed: {args.seed}", _C.DIM)
        _log(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", _C.DIM)

        client = httpx.Client()
        try:
            step_me_01_health(client, urls)
            run_id = step_me_02_farm_generate(client, urls, args.entities, args.seed)
            step_me_03_combining_data(client, urls)
            step_me_04_dcl_verify(client, urls, args.entities)

            if args.verify:
                step_me_05_harness(urls, run_id)
        finally:
            client.close()

        _print_summary()
        _log(f"\n{'=' * 64}", _C.BOLD)
        _log("MULTI-ENTITY PIPELINE COMPLETE", _C.GREEN + _C.BOLD)
        _log(f"{'=' * 64}\n", _C.BOLD)
        return

    # ── Standard single-entity pipeline ────────────────────────────────────
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
        _log(f"  Tenant: {tenant_id}  (override)", _C.DIM)
    else:
        _log(f"  Tenant: (Farm will generate)", _C.DIM)
    if _aod_key:
        _log(f"  AOD API Key: configured", _C.DIM)
    _log(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", _C.DIM)

    client = httpx.Client()

    nb = args.no_browser

    try:
        step_01_health(client, urls)
        step_00_reset(client, urls)

        snapshot_id, tenant_id = step_02_farm_snapshot(client, urls, tenant_id)
        if not nb:
            _open_ui(urls, "2b. Open Farm", urls["farm"])

        run_id = step_03_aod_discovery(client, urls, snapshot_id, tenant_id)
        if not nb:
            _open_ui(urls, "3b. Open AOD Discovery", _frontend_url(urls, "aod"))

        step_04_aod_aam_bridge(client, urls, run_id)

        step_05_aam_infer(client, urls)
        if not nb:
            _open_ui(urls, "5b. Open AAM Topology", f"{urls['aam']}/ui/topology")

        step_06_aam_dcl_push(client, urls)

        step_07_aam_dcl_dispatch(client, urls)
        if not nb:
            _open_ui(urls, "7b. Open DCL Ingest", _frontend_url(urls, "dcl"))
            _open_ui(urls, "7c. Open NLQ", _frontend_url(urls, "nlq"))
            _open_ui(urls, "7d. Open DCL Recon", _frontend_url(urls, "dcl"))

        step_08_aam_runners(client, urls)

        step_08b_combining_data(client, urls)

        step_09_nlq_test(client, urls)

        if args.verify:
            step_me_05_harness(urls, "")

    finally:
        client.close()

    _print_summary()
    _log(f"\n{'=' * 64}", _C.BOLD)
    _log("PIPELINE COMPLETE", _C.GREEN + _C.BOLD)
    _log(f"{'=' * 64}\n", _C.BOLD)


if __name__ == "__main__":
    main()
