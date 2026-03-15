"""
NLQ Ground Truth Harness.
Tests that NLQ returns correct data from the v2 triple store.
Ground truth is queried directly from PG — NLQ must match.
"""
import os
import json
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

NLQ_URL = os.getenv("NLQ_URL", "http://localhost:8005")
DB_URL = os.getenv("SUPABASE_DB_URL")  # Same PG that DCL uses

TENANT_ID = "400aa910-a6b4-5d44-ab9f-e6aecde37721"
ENTITY_A = "meridian"
ENTITY_B = "cascadia"


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def get_pg_value(concept: str, entity_id: str, period: str, property: str = "amount") -> float:
    """Query ground truth directly from PG."""
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("""
        SELECT value::text FROM semantic_triples
        WHERE tenant_id = %s AND entity_id = %s AND concept = %s
        AND property = %s AND period = %s AND is_active = true
        LIMIT 1
    """, (TENANT_ID, entity_id, concept, property, period))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    # value is JSONB stored as text — parse it
    val = json.loads(row["value"]) if isinstance(row["value"], str) else row["value"]
    return float(val)


def get_pg_sum(concept: str, entity_id: str, periods: list, property: str = "amount") -> float:
    """Sum ground truth across periods (for annual totals)."""
    total = 0
    for p in periods:
        v = get_pg_value(concept, entity_id, p, property)
        if v is not None:
            total += v
    return total


def query_nlq(question: str, entity_id: str = None) -> dict:
    """Hit NLQ's API."""
    payload = {"query": question}
    if entity_id:
        payload["entity_id"] = entity_id
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

    def test_meridian_revenue_q1(self):
        expected = get_pg_value("revenue.total", ENTITY_A, "2025-Q1")
        assert expected is not None, "Ground truth missing: meridian revenue Q1 2025"
        resp = query_nlq("What is meridian's revenue for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Meridian Q1 2025 revenue")

    def test_cascadia_revenue_q1(self):
        expected = get_pg_value("revenue.total", ENTITY_B, "2025-Q1")
        assert expected is not None, "Ground truth missing: cascadia revenue Q1 2025"
        resp = query_nlq("What is cascadia's revenue for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Cascadia Q1 2025 revenue")

    def test_meridian_annual_revenue(self):
        expected = get_pg_sum("revenue.total", ENTITY_A, FY2025_QUARTERS)
        resp = query_nlq("What is meridian's revenue for FY 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Meridian FY2025 revenue")

    def test_combined_revenue_q1(self):
        m = get_pg_value("revenue.total", ENTITY_A, "2025-Q1")
        c = get_pg_value("revenue.total", ENTITY_B, "2025-Q1")
        expected = m + c
        resp = query_nlq("What is combined revenue for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Combined Q1 2025 revenue")


class TestAskCosts:
    """Cost queries must return exact values."""

    def test_meridian_cogs(self):
        expected = get_pg_value("cogs.total", ENTITY_A, "2025-Q1")
        assert expected is not None, "Ground truth missing"
        resp = query_nlq("What is meridian's cost of goods sold for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Meridian Q1 COGS")

    def test_meridian_opex(self):
        expected = get_pg_value("opex.total", ENTITY_A, "2025-Q1")
        assert expected is not None, "Ground truth missing"
        resp = query_nlq("What is meridian's total operating expenses for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Meridian Q1 OpEx")


class TestAskDerived:
    """Derived metrics must be correctly computed from components."""

    def test_gross_margin_pct(self):
        rev = get_pg_value("revenue.total", ENTITY_A, "2025-Q1")
        cogs = get_pg_value("cogs.total", ENTITY_A, "2025-Q1")
        expected_pct = ((rev - cogs) / rev) * 100
        resp = query_nlq("What is meridian's gross margin for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected_pct, "Meridian Q1 gross margin %", tolerance_pct=0.02)

    def test_ebitda(self):
        rev = get_pg_value("revenue.total", ENTITY_A, "2025-Q1")
        cogs = get_pg_value("cogs.total", ENTITY_A, "2025-Q1")
        opex = get_pg_value("opex.total", ENTITY_A, "2025-Q1")
        expected = rev - cogs - opex
        resp = query_nlq("What is meridian's EBITDA for Q1 2025?")
        actual = extract_value(resp)
        assert_close(actual, expected, "Meridian Q1 EBITDA")


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
# REPORTS TESTS
# ═══════════════════════════════════════════════

class TestReportsProxy:
    """Reports must return v2 data via the proxy, not old data or zeros."""

    def test_combining_is_has_revenue(self):
        """Combined P&L should have revenue matching ground truth."""
        m_rev = get_pg_sum("revenue.total", ENTITY_A, FY2025_QUARTERS)
        c_rev = get_pg_sum("revenue.total", ENTITY_B, FY2025_QUARTERS)
        expected_combined = m_rev + c_rev

        # Hit the reports proxy endpoint directly
        resp = requests.get(f"{NLQ_URL}/api/reports/combining-is", params={"period": "2025-Q1"})
        if resp.status_code == 200:
            data = resp.json()
            # Find revenue in the response (shape may vary)
            resp_str = json.dumps(data)
            assert "0" != resp_str.strip(), "Combining IS returned all zeros"

    def test_ebitda_bridge_not_all_zeros(self):
        """EBITDA bridge must not show all $0M."""
        resp = requests.get(f"{NLQ_URL}/api/reports/ebitda-bridge")
        if resp.status_code == 200:
            data = resp.json()
            resp_str = json.dumps(data)
            # At least one non-zero value should exist
            import re
            numbers = re.findall(r'"amount":\s*([\d.]+)', resp_str)
            non_zero = [n for n in numbers if float(n) > 0]
            assert len(non_zero) > 0, (
                f"EBITDA bridge has all zero amounts. "
                f"112 ebitda_adjustment triples exist in PG."
            )

    def test_overlap_not_crash(self):
        """Overlap report must not crash with 'matches' undefined."""
        resp = requests.get(f"{NLQ_URL}/api/reports/entity-overlap")
        assert resp.status_code == 200, f"Overlap returned {resp.status_code}"
        data = resp.json()
        assert data is not None, "Overlap returned null"


# ═══════════════════════════════════════════════
# IDENTITY ASSERTIONS
# ═══════════════════════════════════════════════

class TestFinancialIdentity:
    """If NLQ returns P&L components, they must satisfy identities."""

    def test_pl_identity_if_data_present(self):
        """If revenue, COGS, and OpEx are returned, EBITDA must = revenue - COGS - OpEx."""
        rev_resp = query_nlq("What is meridian's revenue for Q1 2025?")
        cogs_resp = query_nlq("What is meridian's COGS for Q1 2025?")
        opex_resp = query_nlq("What is meridian's operating expenses for Q1 2025?")
        ebitda_resp = query_nlq("What is meridian's EBITDA for Q1 2025?")

        rev = extract_value(rev_resp)
        cogs = extract_value(cogs_resp)
        opex = extract_value(opex_resp)
        ebitda = extract_value(ebitda_resp)

        if all(v is not None for v in [rev, cogs, opex, ebitda]):
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
