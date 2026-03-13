"""
Dashboard & Provenance Test Harness

Tests the CFO dashboard widget path and provenance badge through /api/v1/query
with natural language queries. All assertions follow HARNESS_RULES.md.

Ground truth: DCL is queried at startup to confirm revenue-by-customer data exists.

Run:
    python tests/test_dashboard_harness.py
    python tests/test_dashboard_harness.py --verbose
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NLQ_BASE = os.environ.get("NLQ_BASE_URL", "http://127.0.0.1:8005")
NLQ_ENDPOINT = f"{NLQ_BASE}/api/v1/query"
PIPELINE_ENDPOINT = f"{NLQ_BASE}/api/v1/pipeline/status"
TIMEOUT = 90.0  # dashboards are slow (LLM + multiple DCL calls)

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


# ---------------------------------------------------------------------------
# Ground truth: fetch from DCL at startup
# ---------------------------------------------------------------------------
def fetch_ground_truth() -> Dict[str, Any]:
    """Query NLQ for revenue by customer to establish ground truth data."""
    resp = requests.post(
        NLQ_ENDPOINT,
        json={"question": "show me revenue by customer", "entity": "meridian"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    dd = data.get("dashboard_data", {})
    # Find the breakdown widget
    for key, widget in dd.items():
        if isinstance(widget, dict) and widget.get("series"):
            series_data = widget["series"][0].get("data", [])
            if len(series_data) >= 5:
                return {
                    "customer_count": len(series_data),
                    "customers": {item["label"]: item["value"] for item in series_data},
                    "total": round(sum(item["value"] for item in series_data), 2),
                }
    return {"customer_count": 0, "customers": {}, "total": 0}


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------
@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    expected: str = ""
    got: str = ""


def query_nlq(question: str, entity: str = "meridian") -> Dict[str, Any]:
    """POST to /api/v1/query and return JSON response."""
    resp = requests.post(
        NLQ_ENDPOINT,
        json={"question": question, "entity": entity},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def fail(name: str, expected: str, got: str, user_sees: str) -> TestResult:
    return TestResult(
        name=name,
        passed=False,
        message=f"User asked and expected {expected}. Got: {got}. User sees: {user_sees}",
        expected=expected,
        got=got,
    )


def ok(name: str, msg: str = "") -> TestResult:
    return TestResult(name=name, passed=True, message=msg)


# ---------------------------------------------------------------------------
# Health check (D2: verify health first)
# ---------------------------------------------------------------------------
def check_health() -> Optional[str]:
    """Return error string if services are unhealthy, else None."""
    try:
        resp = requests.get(PIPELINE_ENDPOINT, timeout=10.0)
        resp.raise_for_status()
        status = resp.json()
    except Exception as e:
        return f"NLQ health check failed: {e}"

    if not status.get("dcl_connected"):
        return "DCL not connected to NLQ"
    mode = status.get("dcl_mode", "")
    if mode.lower() not in ("ingest", "live"):
        return f"DCL mode is '{mode}', expected Ingest/Live (B9/B15: pipeline must run first)"
    return None


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_breakdown_revenue_by_customer(ground_truth: Dict) -> TestResult:
    """T1: 'show me revenue by customer' returns live data with correct provenance."""
    name = "breakdown_revenue_by_customer"
    d = query_nlq("show me revenue by customer")

    # B12: source field checked on every data test
    ds = d.get("data_source")
    if ds != "live":
        return fail(name, "data_source=='live'", f"data_source=={ds!r}", "Badge shows wrong source")

    # B4: assert positive outcome for provenance mode
    prov = d.get("provenance") or {}
    mode = prov.get("mode")
    if not mode or mode.lower() not in ("ingest", "live"):
        return fail(name, "provenance.mode in (Ingest, Live)", f"mode={mode!r}", "Grey 'Local Data' badge")

    # Check item count
    dd = d.get("dashboard_data", {})
    items = []
    for widget in dd.values():
        if isinstance(widget, dict) and widget.get("series"):
            items = widget["series"][0].get("data", [])
            break
    if len(items) < 10:
        return fail(name, ">=10 customer items", f"{len(items)} items", "Empty or sparse chart")

    return ok(name, f"{len(items)} customers, data_source=live, mode={mode}")


def test_basic_metric_provenance() -> TestResult:
    """T2: 'what is revenue?' returns live data with Ingest provenance."""
    name = "basic_metric_provenance"
    d = query_nlq("what is revenue?")

    ds = d.get("data_source")
    if ds != "live":
        return fail(name, "data_source=='live'", f"data_source=={ds!r}", "Wrong source badge")

    prov = d.get("provenance") or {}
    mode = prov.get("mode")
    if not mode or mode.lower() not in ("ingest", "live"):
        return fail(name, "provenance.mode in (Ingest, Live)", f"mode={mode!r}", "Grey 'Local Data' badge")

    value = d.get("value")
    if value is None or (isinstance(value, (int, float)) and value <= 0):
        return fail(name, "positive revenue value", f"value={value}", "No value shown")

    return ok(name, f"revenue={value}, mode={mode}")


def test_dashboard_has_customer_widget(ground_truth: Dict) -> TestResult:
    """T3: CFO dashboard includes a customer revenue widget with real data."""
    name = "dashboard_has_customer_widget"
    d = query_nlq("build me a CFO dashboard")
    dd = d.get("dashboard_data", {})

    # Find customer widget
    customer_widget = None
    customer_key = None
    for key, widget in dd.items():
        if "customer" in key.lower() and isinstance(widget, dict):
            customer_widget = widget
            customer_key = key
            break

    if not customer_widget:
        return fail(name, "dashboard contains customer widget", f"widgets: {list(dd.keys())}", "No customer breakdown in dashboard")

    # Check it has data, not an error
    err = customer_widget.get("error")
    if err:
        return fail(name, "customer widget has data", f"error={err!r}", f"Widget shows error: {err}")

    series = customer_widget.get("series", [])
    if not series or not series[0].get("data"):
        return fail(name, "customer widget has series data", "empty series", "Empty chart shown")

    items = series[0]["data"]
    if len(items) < 5:
        return fail(name, ">=5 customer items", f"{len(items)} items", "Nearly empty chart")

    # Cross-check with ground truth
    gt_customers = ground_truth.get("customers", {})
    if gt_customers:
        widget_customers = {item["label"]: item["value"] for item in items}
        mismatches = []
        for cust, gt_val in list(gt_customers.items())[:5]:
            widget_val = widget_customers.get(cust)
            if widget_val is None:
                mismatches.append(f"{cust}: missing")
            elif abs(widget_val - gt_val) > 0.1:
                mismatches.append(f"{cust}: expected {gt_val}, got {widget_val}")
        if mismatches:
            return fail(name, "widget values match ground truth", "; ".join(mismatches), "Dashboard shows wrong values")

    return ok(name, f"{len(items)} customers in widget '{customer_key}'")


def test_dashboard_provenance() -> TestResult:
    """T4: CFO dashboard response has correct provenance badge data."""
    name = "dashboard_provenance"
    d = query_nlq("build me a CFO dashboard")

    ds = d.get("data_source")
    if ds != "live":
        return fail(name, "data_source=='live'", f"data_source=={ds!r}", "Wrong source badge")

    prov = d.get("provenance") or {}
    mode = prov.get("mode")
    if not mode or mode.lower() not in ("ingest", "live"):
        return fail(name, "provenance.mode in (Ingest, Live)", f"mode={mode!r}", "Grey 'Local Data' badge on dashboard")

    run_id = prov.get("run_id")
    if not run_id:
        return fail(name, "provenance.run_id present", "run_id=None", "No run traceability")

    return ok(name, f"mode={mode}, run_id={run_id[:30]}...")


def test_dashboard_kpi_cards_work() -> TestResult:
    """T5: Dashboard KPI widgets have numeric values and formatted strings (proves time-series/KPI path still uses granularity)."""
    name = "dashboard_kpi_cards_work"
    d = query_nlq("build me a CFO dashboard")
    dd = d.get("dashboard_data", {})

    kpi_widgets = {k: v for k, v in dd.items() if k.startswith("kpi_") and isinstance(v, dict)}
    if not kpi_widgets:
        return fail(name, ">=1 KPI widget", "no kpi_ widgets found", "Dashboard has no KPI cards")

    errors = []
    for key, widget in kpi_widgets.items():
        value = widget.get("value")
        formatted = widget.get("formatted_value")
        if value is None:
            errors.append(f"{key}: value=None")
        elif not isinstance(value, (int, float)):
            errors.append(f"{key}: value={value!r} (not numeric)")
        if not formatted or not isinstance(formatted, str):
            errors.append(f"{key}: formatted_value={formatted!r} (not a string)")

    if errors:
        return fail(name, "all KPI widgets have numeric value + formatted string", "; ".join(errors), "KPI cards show blanks or errors")

    summary = ", ".join(f"{k}={v.get('formatted_value')}" for k, v in kpi_widgets.items())
    return ok(name, f"{len(kpi_widgets)} KPIs: {summary}")


def test_dashboard_trend_charts_work() -> TestResult:
    """T6: Dashboard trend/line/area chart widgets have >=2 data points (proves time-series granularity still works)."""
    name = "dashboard_trend_charts_work"
    d = query_nlq("build me a CFO dashboard")
    dd = d.get("dashboard_data", {})

    trend_widgets = {k: v for k, v in dd.items() if k.startswith("trend_") and isinstance(v, dict)}
    if not trend_widgets:
        return fail(name, ">=1 trend widget", "no trend_ widgets found", "Dashboard has no trend charts")

    errors = []
    for key, widget in trend_widgets.items():
        series = widget.get("series", [])
        if not series:
            errors.append(f"{key}: no series")
            continue
        data = series[0].get("data", [])
        if len(data) < 2:
            errors.append(f"{key}: only {len(data)} data points (need >=2)")
            continue
        # Check that data points have labels (categories/periods)
        if not data[0].get("label"):
            errors.append(f"{key}: data points missing 'label' field")

    if errors:
        return fail(name, "all trend widgets have >=2 data points with labels", "; ".join(errors), "Trend charts empty or flat")

    summary = ", ".join(f"{k}={len(v.get('series', [{}])[0].get('data', []))}pts" for k, v in trend_widgets.items())
    return ok(name, f"{len(trend_widgets)} trends: {summary}")


def test_cascadia_dashboard() -> TestResult:
    """T7: Cascadia CFO dashboard has no breakdown errors."""
    name = "cascadia_dashboard"
    d = query_nlq("build me a CFO dashboard", entity="cascadia")
    dd = d.get("dashboard_data", {})

    if not dd:
        return fail(name, "dashboard_data present", "dashboard_data is empty/null", "No dashboard generated for cascadia")

    errors_found = []
    for key, widget in dd.items():
        if isinstance(widget, dict) and widget.get("error"):
            errors_found.append(f"{key}: {widget['error']}")

    if errors_found:
        return fail(name, "no widget errors", "; ".join(errors_found), f"Cascadia dashboard has errors: {errors_found[0]}")

    ds = d.get("data_source")
    if ds not in ("live", "dcl"):
        return fail(name, "data_source in (live, dcl)", f"data_source={ds!r}", "Wrong data source for cascadia")

    return ok(name, f"{len(dd)} widgets, data_source={ds}")


def test_fact_base_independence() -> TestResult:
    """T8: fact_base.json is not present, all queries succeed with data_source=='live'."""
    name = "fact_base_independence"

    # Confirm fact_base.json is absent
    fb_path = Path(__file__).parent.parent / "data" / "fact_base.json"
    if fb_path.exists():
        return fail(name, "fact_base.json absent", "fact_base.json exists", "System may silently fall back to demo data")

    # Run a simple query and verify source
    d = query_nlq("what is revenue?")
    ds = d.get("data_source")
    if ds != "live":
        return fail(name, "data_source=='live' without fact_base", f"data_source={ds!r}", "System not using live DCL data")

    return ok(name, "fact_base.json absent, data_source=live")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_all() -> List[TestResult]:
    # D2: health first
    health_err = check_health()
    if health_err:
        print(f"\n[ABORT] {health_err}")
        print("Harness cannot run. Fix service health first.")
        sys.exit(1)

    # Fetch ground truth (B10: from live system, not hardcoded)
    print("Fetching ground truth from NLQ (revenue by customer)...")
    ground_truth = fetch_ground_truth()
    print(f"  Ground truth: {ground_truth['customer_count']} customers, total={ground_truth['total']}")
    if ground_truth["customer_count"] < 5:
        print("[ABORT] Ground truth has <5 customers — DCL data may be stale or missing")
        sys.exit(1)

    results: List[TestResult] = []

    # Tests that share dashboard responses are called independently (B16: no caching)
    tests = [
        ("T1", lambda: test_breakdown_revenue_by_customer(ground_truth)),
        ("T2", lambda: test_basic_metric_provenance()),
        ("T3", lambda: test_dashboard_has_customer_widget(ground_truth)),
        ("T4", lambda: test_dashboard_provenance()),
        ("T5", lambda: test_dashboard_kpi_cards_work()),
        ("T6", lambda: test_dashboard_trend_charts_work()),
        ("T7", lambda: test_cascadia_dashboard()),
        ("T8", lambda: test_fact_base_independence()),
    ]

    for label, test_fn in tests:
        print(f"\nRunning {label}: {test_fn.__name__ if hasattr(test_fn, '__name__') else ''}...", end=" ", flush=True)
        try:
            result = test_fn()
            results.append(result)
            status = "[PASS]" if result.passed else "[FAIL]"
            print(status)
            if VERBOSE or not result.passed:
                print(f"  {result.message}")
        except Exception as e:
            results.append(TestResult(name=label, passed=False, message=f"Exception: {e}"))
            print("[FAIL]")
            print(f"  Exception: {e}")

    return results


def main():
    print("=" * 60)
    print("Dashboard & Provenance Test Harness")
    print("=" * 60)

    results = run_all()

    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed")
    if passed < total:
        print("\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  [FAIL] {r.name}: {r.message}")
        print("=" * 60)
        sys.exit(1)
    else:
        print("All tests passed.")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
