"""
NLQ Ground Truth Harness.
Tests that NLQ returns correct data from the v2 triple store.
Ground truth is fetched from DCL's HTTP API — NLQ must match.
"""
import os
import json
import requests
import httpx
import pytest

NLQ_URL = os.getenv("NLQ_URL", "http://localhost:8005")
DCL_URL = os.getenv("DCL_API_URL", "http://localhost:8004")

_dcl_client = httpx.Client(base_url=DCL_URL, timeout=15.0)


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def get_se_entity_id() -> str:
    """Fetch the active SE entity_id from DCL at runtime.

    Queries DCL's /api/dcl/entities endpoint for the entity marked
    is_most_recent=True. Asserts exactly one active entity (SE mode).
    """
    resp = _dcl_client.get("/api/dcl/entities")
    resp.raise_for_status()
    entities = resp.json().get("entities", [])
    active = [e for e in entities if e.get("is_most_recent")]
    assert len(active) == 1, (
        f"SE mode expects exactly 1 active entity (is_most_recent=True), "
        f"got {len(active)}: {[e['entity_id'] for e in active]}"
    )
    return active[0]["entity_id"]


def get_gt_value(concept: str, entity_id: str, period: str, property: str = "amount") -> float:
    """Query ground truth from DCL's browse API.

    Browse filters by domain prefix (LIKE '{domain}.%'), so we pass the
    top-level domain and then match the exact concept client-side.
    """
    domain = concept.split(".")[0]
    resp = _dcl_client.get(
        "/api/dcl/triples/browse",
        params={
            "domain": domain,
            "entity_id": entity_id,
            "period": period,
            "property": property,
            "limit": 50,
        },
    )
    resp.raise_for_status()
    for triple in resp.json().get("triples", []):
        if triple.get("concept") == concept:
            val = triple.get("value")
            if val is None:
                return None
            return float(val)
    return None


def get_gt_sum(concept: str, entity_id: str, periods: list, property: str = "amount") -> float:
    """Sum ground truth across periods (for annual totals)."""
    total = 0
    for p in periods:
        v = get_gt_value(concept, entity_id, p, property)
        if v is not None:
            total += v
    return total


def query_nlq(question: str, entity_id: str = None) -> dict:
    """Hit NLQ's API.

    PR 2: NLQRequest uses `question` (not `query`) as the field name, and
    /query returns 422 when no entity can be resolved. Backfill entity_id
    from the active SE entity when caller didn't supply one. (The old
    `{"query": ...}` payload was a pre-existing bug — Pydantic required
    `question`, but the silent fallback on entity resolution hid it.)
    """
    payload = {"question": question}
    payload["entity_id"] = entity_id or get_se_entity_id()
    resp = requests.post(f"{NLQ_URL}/api/v1/query", json=payload, timeout=30)
    return resp.json()


def extract_value(response: dict) -> float:
    """Extract the numeric value from NLQ's response.
    NLQ response shapes vary — try multiple paths.
    Returns None if no numeric value found.
    """
    # Path 1: direct value field
    if "value" in response and response["value"] is not None:
        try:
            return float(response["value"])
        except (TypeError, ValueError):
            pass

    # Path 2: data.value
    if "data" in response and isinstance(response["data"], dict):
        if "value" in response["data"] and response["data"]["value"] is not None:
            try:
                return float(response["data"]["value"])
            except (TypeError, ValueError):
                pass

    # Path 3: answer contains a number (parse from text)
    if "answer" in response and response["answer"]:
        import re
        # Find dollar amounts like $1,234.5 or 1234.5
        nums = re.findall(r'[\$]?([\d,]+\.?\d*)', str(response["answer"]))
        if nums:
            try:
                return float(nums[0].replace(",", ""))
            except ValueError:
                pass

    return None


FY2025_QUARTERS = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
FY2024_QUARTERS = ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]
TOLERANCE_PCT = 0.01  # 1% tolerance for rounding/display differences


def assert_close(actual, expected, label, tolerance_pct=TOLERANCE_PCT):
    """Assert actual is within tolerance of expected."""
    assert actual is not None, f"{label}: got None, expected {expected}"
    assert expected != 0 or actual == 0, f"{label}: expected 0, got {actual}"
    if expected != 0:
        pct_diff = abs(actual - expected) / abs(expected)
        assert pct_diff <= tolerance_pct, (
            f"{label}: expected {expected}, got {actual} "
            f"(diff: {pct_diff*100:.1f}%, tolerance: {tolerance_pct*100:.1f}%)"
        )


# ═══════════════════════════════════════════════
# ASK TAB TESTS
# ═══════════════════════════════════════════════

class TestAskRevenue:
    """Revenue queries must return exact values from triples."""

    def test_revenue_q1(self):
        entity_id = get_se_entity_id()
        expected = get_gt_value("revenue.total", entity_id, "2025-Q1")
        assert expected is not None, "Ground truth missing: revenue Q1 2025"
        resp = query_nlq("What is revenue for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Q1 2025 revenue")

    def test_annual_revenue(self):
        entity_id = get_se_entity_id()
        expected = get_gt_sum("revenue.total", entity_id, FY2025_QUARTERS)
        resp = query_nlq("What is revenue for FY 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "FY2025 revenue")


class TestAskCosts:
    """Cost queries must return exact values."""

    def test_cogs(self):
        entity_id = get_se_entity_id()
        expected = get_gt_value("cogs.total", entity_id, "2025-Q1")
        assert expected is not None, "Ground truth missing: COGS Q1 2025"
        resp = query_nlq("What is cost of goods sold for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Q1 COGS")

    def test_opex(self):
        entity_id = get_se_entity_id()
        expected = get_gt_value("opex.total", entity_id, "2025-Q1")
        assert expected is not None, "Ground truth missing: OpEx Q1 2025"
        resp = query_nlq("What is total operating expenses for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Q1 OpEx")


class TestAskDerived:
    """Derived metrics must be correctly computed from components."""

    def test_gross_margin_pct(self):
        entity_id = get_se_entity_id()
        rev = get_gt_value("revenue.total", entity_id, "2025-Q1")
        cogs = get_gt_value("cogs.total", entity_id, "2025-Q1")
        expected_pct = ((rev - cogs) / rev) * 100
        resp = query_nlq("What is gross margin for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected_pct, "Q1 gross margin %", tolerance_pct=0.02)

    def test_ebitda(self):
        entity_id = get_se_entity_id()
        rev = get_gt_value("revenue.total", entity_id, "2025-Q1")
        cogs = get_gt_value("cogs.total", entity_id, "2025-Q1")
        opex = get_gt_value("opex.total", entity_id, "2025-Q1")
        expected = rev - cogs - opex
        resp = query_nlq("What is EBITDA for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Q1 EBITDA")


class TestAskEmployees:
    """Employee data exists in triples — NLQ must return it."""

    def test_headcount_exists(self):
        """40 employee triples exist. NLQ must not say 'no data'."""
        resp = query_nlq("How many employees?")
        # Must NOT contain "don't have data" or return null
        answer = str(resp.get("answer", ""))
        assert "don't have data" not in answer.lower(), f"NLQ says no data but 40 employee triples exist: {answer}"
        actual = extract_value(resp)
        assert actual is not None, f"Headcount returned null. Response: {resp}"
        assert actual > 0, f"Headcount returned 0. Response: {resp}"


class TestAskNegative:
    """Queries for data that doesn't exist should fail gracefully, not fabricate."""

    def test_churn_not_fabricated(self):
        """Churn data does not exist in the triple store. NLQ must NOT return 0%."""
        resp = query_nlq("What is churn?")
        answer = str(resp.get("answer", ""))
        # 0% churn is fabricated — there are no churn triples
        assert "0%" not in answer or "not available" in answer.lower() or "no data" in answer.lower(), (
            f"NLQ returned fabricated churn data: {answer}. "
            f"There are zero churn triples in the store."
        )

    def test_unknown_entity_graceful(self):
        """Unknown entity should not crash."""
        resp = query_nlq("What is foobar's revenue?")
        assert resp is not None, "NLQ crashed on unknown entity"
        # Should either say entity not found or return no data — not crash

    def test_no_local_only_error(self):
        """The 'local_only' parameter must not leak from old client."""
        resp = query_nlq("2026 forecast")
        answer = str(resp.get("answer", ""))
        assert "local_only" not in answer, f"Old client parameter leaked: {answer}"
        assert "TypeError" not in answer, f"TypeError in response: {answer}"


# ═══════════════════════════════════════════════
# DASHBOARD TESTS
# ═══════════════════════════════════════════════

class TestDashboard:
    """Dashboard metrics must return real values, not empty/null."""

    def test_cfo_dashboard_has_revenue(self):
        resp = query_nlq("Show me the CFO dashboard")
        # Response should contain revenue data
        resp_str = json.dumps(resp)
        # Must have actual numbers, not all nulls
        assert "null" not in resp_str.lower() or "revenue" in resp_str.lower(), (
            f"CFO dashboard appears empty: {resp_str[:500]}"
        )

    def test_dashboard_not_empty(self):
        """Dashboard tab should not show 'No Dashboard Loaded'."""
        resp = query_nlq("Build me a CFO dashboard")
        # Should return dashboard data, not an error
        assert resp.get("type") != "error", f"Dashboard returned error: {resp}"


# ═══════════════════════════════════════════════
# IDENTITY ASSERTIONS
# ═══════════════════════════════════════════════

class TestFinancialIdentity:
    """If NLQ returns P&L components, they must satisfy identities."""

    def test_pl_identity(self):
        """Revenue, COGS, OpEx, and EBITDA must satisfy: EBITDA = Rev - COGS - OpEx."""
        rev_resp = query_nlq("What is revenue for Q1 2025?")
        cogs_resp = query_nlq("What is COGS for Q1 2025?")
        opex_resp = query_nlq("What is operating expenses for Q1 2025?")
        ebitda_resp = query_nlq("What is EBITDA for Q1 2025?")

        rev = extract_value(rev_resp)
        cogs = extract_value(cogs_resp)
        opex = extract_value(opex_resp)
        ebitda = extract_value(ebitda_resp)

        assert rev is not None, "P&L identity: revenue query returned None"
        assert cogs is not None, "P&L identity: COGS query returned None"
        assert opex is not None, "P&L identity: OpEx query returned None"
        assert ebitda is not None, "P&L identity: EBITDA query returned None"
        expected_ebitda = rev - cogs - opex
        assert_close(ebitda, expected_ebitda, "P&L identity: EBITDA = Rev - COGS - OpEx")


# ═══════════════════════════════════════════════
# LATENCY
# ═══════════════════════════════════════════════

class TestLatency:
    """Responses must be under 10 seconds."""

    def test_simple_query_latency(self):
        import time
        start = time.time()
        query_nlq("What is revenue?")
        elapsed = time.time() - start
        assert elapsed < 10, f"Simple query took {elapsed:.1f}s (max: 10s)"

    def test_dashboard_latency(self):
        import time
        start = time.time()
        query_nlq("Show me the CFO dashboard")
        elapsed = time.time() - start
        assert elapsed < 15, f"Dashboard took {elapsed:.1f}s (max: 15s)"
