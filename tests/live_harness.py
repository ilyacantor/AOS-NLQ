#!/usr/bin/env python3
"""
NLQ Live Mode Structural Test Harness
======================================
Tests all 30 ground truth questions against the NLQ API in live mode (DCL).
Validates **structural shape** only — not numeric accuracy — because live
DCL data changes.

4 shape categories:
  POINT         — success=True, numeric value, non-empty answer
  BREAKDOWN     — success=True, dashboard_data with 2+ labeled items
  RANKING       — success=True, entity name in answer, value present
  INGEST_STATUS — success=True, answer has digits, not "no live ingest data"

All requests: POST /api/v1/query  {data_mode: "live", mode: "ai"}

Run:
    python tests/live_harness.py
    python tests/live_harness.py --verbose
    python tests/live_harness.py --md          # write LIVE_TEST_RESULTS.md
"""

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:8005"
NLQ_ENDPOINT = "/api/v1/query"
TIMEOUT = 45.0  # generous — LLM calls can be slow

BAD_DATA_SOURCES = {"demo", "local_fallback", "fact_base", "local"}

# ---------------------------------------------------------------------------
# Shape categories
# ---------------------------------------------------------------------------
POINT = "POINT"
BREAKDOWN = "BREAKDOWN"
RANKING = "RANKING"
INGEST_STATUS = "INGEST_STATUS"
REPORT_ENTITY = "REPORT_ENTITY"
BRIDGE_FORMAT = "BRIDGE_FORMAT"
BRIDGE_SOURCE = "BRIDGE_SOURCE"


# ---------------------------------------------------------------------------
# Test case definition
# ---------------------------------------------------------------------------
@dataclass
class TestCase:
    qid: str           # e.g. "Q01"
    persona: str
    question: str
    shape: str          # POINT | BREAKDOWN | RANKING | INGEST_STATUS | ...
    entity_id: Optional[str] = None       # sent as entity_id in payload
    consolidate: bool = False             # sent as consolidate in payload


# ---------------------------------------------------------------------------
# 30 ground truth questions organized by expected response shape
# ---------------------------------------------------------------------------
QUESTIONS: List[TestCase] = [
    # POINT (10): Q01, Q03, Q05-Q08, Q11, Q18, Q27, Q28
    TestCase("Q01", "CFO",  "What is our current ARR?",              POINT),
    TestCase("Q03", "CRO",  "What is our win rate?",                 POINT),
    TestCase("Q05", "CTO",  "What is our current uptime?",           POINT),
    TestCase("Q06", "CTO",  "What is MTTR for P1 incidents?",        POINT),
    TestCase("Q07", "CHRO", "What is our current headcount?",        POINT),
    TestCase("Q08", "CHRO", "What is our attrition rate?",           POINT),
    TestCase("Q11", "CFO",  "What is our gross margin?",             POINT),
    TestCase("Q18", "CRO",  "What is our NRR?",                      POINT),
    TestCase("Q27", "CHRO", "What is our engagement score?",         POINT),
    TestCase("Q28", "CHRO", "What is our offer acceptance rate?",    POINT),

    # BREAKDOWN (12): Q02, Q12-Q13, Q15-Q17, Q19, Q21-Q22, Q24, Q26, Q29
    TestCase("Q02", "CFO",  "Show revenue by region",                BREAKDOWN),
    TestCase("Q12", "CFO",  "Show revenue by segment",               BREAKDOWN),
    TestCase("Q13", "CFO",  "What is DSO by segment?",               BREAKDOWN),
    TestCase("Q15", "CFO",  "What is our cloud spend by category?",  BREAKDOWN),
    TestCase("Q16", "CRO",  "Show pipeline by stage",                BREAKDOWN),
    TestCase("Q17", "CRO",  "What is churn rate by segment?",        BREAKDOWN),
    TestCase("Q19", "CRO",  "Show NRR by cohort",                    BREAKDOWN),
    TestCase("Q21", "CTO",  "What is deploy frequency by service?",  BREAKDOWN),
    TestCase("Q22", "CTO",  "Show uptime by service",                BREAKDOWN),
    TestCase("Q24", "CTO",  "What is SLA compliance by team?",       BREAKDOWN),
    TestCase("Q26", "CHRO", "What is headcount by department?",      BREAKDOWN),
    TestCase("Q29", "COO",  "What is throughput by team?",           BREAKDOWN),

    # RANKING (5): Q04, Q14, Q20, Q23, Q25
    TestCase("Q04", "CRO",  "Which customer has the highest churn risk?", RANKING),
    TestCase("Q14", "CFO",  "Which product has the highest gross margin?", RANKING),
    TestCase("Q20", "CRO",  "Which segment has the highest churn?",  RANKING),
    TestCase("Q23", "CTO",  "Which service deploys the most?",       RANKING),
    TestCase("Q25", "CTO",  "Which team has the lowest SLA compliance?", RANKING),

    # INGEST_STATUS (3): Q09, Q10, Q30
    TestCase("Q09", "COO",  "How many data sources are connected?",              INGEST_STATUS),
    TestCase("Q10", "COO",  "Which source system has the most ingested rows?",   INGEST_STATUS),
    TestCase("Q30", "COO",  "How many total rows have been ingested?",           INGEST_STATUS),

    # UF (user-fix) tests: entity-scoped reports + bridge chart
    TestCase("UF_040", "CFO", "Show me the P&L actual vs prior year",            REPORT_ENTITY, entity_id="cascadia"),
    TestCase("UF_042", "CFO", "why did revenue increase",                        BRIDGE_FORMAT),
    TestCase("UF_043", "CFO", "why did revenue increase",                        BRIDGE_SOURCE),
]


# ---------------------------------------------------------------------------
# Structural validators — each returns (pass: bool, reason: str)
# ---------------------------------------------------------------------------

def validate_point(body: Dict) -> Tuple[bool, str]:
    """POINT: success=True, value is numeric, answer non-empty, not demo."""
    if not body.get("success"):
        err = body.get("error_message") or body.get("error_code") or "success=false"
        return False, f"NOT_SUCCESS: {err}"

    answer = (body.get("answer") or "").strip()
    if not answer:
        return False, "EMPTY_ANSWER"

    value = body.get("value")
    if value is None:
        # Try extracting from answer text
        m = re.search(r'[\$]?([\d,]+\.?\d*)', answer)
        if m:
            try:
                value = float(m.group(1).replace(",", ""))
            except ValueError:
                pass

    if value is None:
        return False, f"NO_NUMERIC_VALUE (answer='{answer[:80]}')"

    if not isinstance(value, (int, float)):
        try:
            float(value)
        except (TypeError, ValueError):
            return False, f"VALUE_NOT_NUMERIC: {value!r}"

    ds = (body.get("data_source") or "").lower()
    if ds in BAD_DATA_SOURCES:
        return False, f"BAD_DATA_SOURCE: {ds}"

    return True, f"OK (value={value}, source={ds or 'n/a'})"


def validate_breakdown(body: Dict) -> Tuple[bool, str]:
    """BREAKDOWN: success=True, dashboard_data with 2+ labeled data points
    OR related_metrics with 2+ items. Not demo."""
    if not body.get("success"):
        err = body.get("error_message") or body.get("error_code") or "success=false"
        return False, f"NOT_SUCCESS: {err}"

    ds = (body.get("data_source") or "").lower()
    if ds in BAD_DATA_SOURCES:
        return False, f"BAD_DATA_SOURCE: {ds}"

    # Check dashboard_data
    dd = body.get("dashboard_data")
    if dd and isinstance(dd, dict):
        for widget_key, widget in dd.items():
            if not isinstance(widget, dict):
                continue
            series_list = widget.get("series", [])
            for series in (series_list if isinstance(series_list, list) else []):
                data_points = series.get("data", [])
                if isinstance(data_points, list) and len(data_points) >= 2:
                    labels = [dp.get("label") for dp in data_points if dp.get("label")]
                    if len(labels) >= 2:
                        return True, f"OK ({len(labels)} items in dashboard_data, source={ds or 'n/a'})"

    # Fallback: check related_metrics
    rm = body.get("related_metrics")
    if rm and isinstance(rm, list) and len(rm) >= 2:
        names = [m.get("metric") or m.get("display_name") for m in rm if isinstance(m, dict)]
        if len(names) >= 2:
            return True, f"OK ({len(names)} related_metrics, source={ds or 'n/a'})"

    # Neither path had 2+ items
    dd_summary = json.dumps(dd)[:150] if dd else "null"
    rm_count = len(rm) if rm and isinstance(rm, list) else 0
    return False, f"NO_BREAKDOWN_DATA (dashboard_data={dd_summary}, related_metrics_count={rm_count})"


def validate_ranking(body: Dict) -> Tuple[bool, str]:
    """RANKING: success=True, answer has entity name (**bold** or identifiable),
    value present, not demo."""
    if not body.get("success"):
        err = body.get("error_message") or body.get("error_code") or "success=false"
        return False, f"NOT_SUCCESS: {err}"

    ds = (body.get("data_source") or "").lower()
    if ds in BAD_DATA_SOURCES:
        return False, f"BAD_DATA_SOURCE: {ds}"

    answer = (body.get("answer") or "").strip()
    if not answer:
        return False, "EMPTY_ANSWER"

    # Look for entity name — bold markdown or quoted
    bold = re.search(r'\*\*([^*]+)\*\*', answer)
    quoted = re.search(r'"([^"]+)"', answer) if not bold else None
    entity = bold.group(1) if bold else (quoted.group(1) if quoted else None)

    # Also check dashboard_data for top ranked item
    value = body.get("value")
    dd = body.get("dashboard_data")
    if dd and isinstance(dd, dict):
        for widget_key, widget in dd.items():
            if not isinstance(widget, dict):
                continue
            for series in (widget.get("series", []) if isinstance(widget.get("series"), list) else []):
                data_points = series.get("data", [])
                if data_points and isinstance(data_points, list):
                    top = data_points[0]
                    if not entity:
                        entity = top.get("label")
                    if value is None:
                        value = top.get("value")

    if not entity:
        # Last resort: check if answer has a capitalized name-like word
        caps = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', answer)
        # Filter out common words
        stopwords = {"The", "Our", "Based", "This", "That", "With", "From", "What", "Which", "Has", "Have"}
        caps = [c for c in caps if c not in stopwords]
        if caps:
            entity = caps[0]

    if not entity:
        return False, f"NO_ENTITY_NAME (answer='{answer[:100]}')"

    # Check value exists — from response or extractable from answer
    if value is None:
        m = re.search(r'[\$]?([\d,]+\.?\d*)\s*[M%]?', answer)
        if m:
            try:
                value = float(m.group(1).replace(",", ""))
            except ValueError:
                pass

    if value is None:
        return False, f"ENTITY_OK ({entity}) but NO_VALUE (answer='{answer[:100]}')"

    return True, f"OK (entity='{entity}', value={value}, source={ds or 'n/a'})"


def validate_ingest_status(body: Dict) -> Tuple[bool, str]:
    """INGEST_STATUS: success=True, answer has digits, doesn't say
    'no live ingest data'."""
    if not body.get("success"):
        err = body.get("error_message") or body.get("error_code") or "success=false"
        return False, f"NOT_SUCCESS: {err}"

    answer = (body.get("answer") or "").strip()
    if not answer:
        return False, "EMPTY_ANSWER"

    lower_answer = answer.lower()
    bad_phrases = ["no live ingest", "not available", "no ingest data", "no data available"]
    for phrase in bad_phrases:
        if phrase in lower_answer:
            return False, f"INGEST_REJECTION: '{phrase}' found in answer"

    # Must contain at least one number
    if not re.search(r'\d', answer):
        return False, f"NO_DIGITS_IN_ANSWER (answer='{answer[:100]}')"

    ds = (body.get("data_source") or "").lower()
    return True, f"OK (answer has digits, source={ds or 'n/a'})"


def validate_report_entity(body: Dict) -> Tuple[bool, str]:
    """REPORT_ENTITY: success=True, financial_statement_data present with
    non-empty line_items, entity matches expected, source is not demo."""
    if not body.get("success"):
        err = body.get("error_message") or body.get("error_code") or "success=false"
        return False, f"NOT_SUCCESS: {err}"

    ds = (body.get("data_source") or "").lower()
    if ds in BAD_DATA_SOURCES:
        return False, f"BAD_DATA_SOURCE: {ds}"

    fs = body.get("financial_statement_data")
    if not fs or not isinstance(fs, dict):
        return False, "NO_FINANCIAL_STATEMENT_DATA"

    line_items = fs.get("line_items", [])
    if not line_items or len(line_items) < 3:
        return False, f"INSUFFICIENT_LINE_ITEMS: got {len(line_items)}"

    # At least one line item must have a non-null value
    has_value = False
    for li in line_items:
        vals = li.get("values", {})
        for v in vals.values():
            if v is not None:
                has_value = True
                break
        if has_value:
            break

    if not has_value:
        return False, "ALL_VALUES_NULL — report has line items but no data"

    entity = fs.get("entity", "")
    return True, f"OK (entity='{entity}', {len(line_items)} line items, source={ds or 'n/a'})"


def validate_bridge_format(body: Dict) -> Tuple[bool, str]:
    """BRIDGE_FORMAT: success=True, response_type='bridge_chart',
    bridge_chart_data with 3+ bars (start, at least one driver, end)."""
    if not body.get("success"):
        err = body.get("error_message") or body.get("error_code") or "success=false"
        return False, f"NOT_SUCCESS: {err}"

    rt = body.get("response_type", "")
    if rt != "bridge_chart":
        return False, f"WRONG_RESPONSE_TYPE: '{rt}' (expected 'bridge_chart')"

    bcd = body.get("bridge_chart_data")
    if not bcd or not isinstance(bcd, dict):
        return False, "NO_BRIDGE_CHART_DATA"

    bars = bcd.get("bars", [])
    if len(bars) < 3:
        return False, f"INSUFFICIENT_BARS: got {len(bars)} (need start + drivers + end)"

    # First and last bars should be totals
    if bars[0].get("type") != "total":
        return False, f"FIRST_BAR_NOT_TOTAL: type='{bars[0].get('type')}'"
    if bars[-1].get("type") != "total":
        return False, f"LAST_BAR_NOT_TOTAL: type='{bars[-1].get('type')}'"

    # At least one driver bar (increase or decrease)
    drivers = [b for b in bars if b.get("type") in ("increase", "decrease")]
    if not drivers:
        return False, "NO_DRIVER_BARS"

    driver_labels = [b.get("label", "?") for b in drivers[:3]]
    return True, f"OK ({len(bars)} bars, drivers: {driver_labels})"


def validate_bridge_source(body: Dict) -> Tuple[bool, str]:
    """BRIDGE_SOURCE: response_type='bridge_chart' AND data_source is NOT
    'Local', 'fact_base', 'demo', or null. Must be 'live' or 'dcl'."""
    if not body.get("success"):
        err = body.get("error_message") or body.get("error_code") or "success=false"
        return False, f"NOT_SUCCESS: {err}"

    rt = body.get("response_type", "")
    if rt != "bridge_chart":
        return False, f"WRONG_RESPONSE_TYPE: '{rt}' (expected 'bridge_chart')"

    ds = (body.get("data_source") or "").strip()
    if not ds:
        return False, "DATA_SOURCE_NULL — must be 'live' or 'dcl', got empty/null"

    bad_sources = BAD_DATA_SOURCES
    if ds.lower() in bad_sources:
        return False, f"BAD_DATA_SOURCE: '{ds}' — must be 'live' or 'dcl'"

    return True, f"OK (data_source='{ds}')"


# Map shape to validator
VALIDATORS = {
    POINT: validate_point,
    BREAKDOWN: validate_breakdown,
    RANKING: validate_ranking,
    INGEST_STATUS: validate_ingest_status,
    REPORT_ENTITY: validate_report_entity,
    BRIDGE_FORMAT: validate_bridge_format,
    BRIDGE_SOURCE: validate_bridge_source,
}


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
@dataclass
class TestResult:
    qid: str
    persona: str
    question: str
    shape: str
    passed: bool
    reason: str
    answer_excerpt: str = ""
    data_source: str = ""
    response_time_ms: float = 0.0
    raw: Optional[Dict] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_one(client: httpx.Client, tc: TestCase) -> TestResult:
    """Fire one question at NLQ in live mode, validate structural shape."""
    payload = {
        "question": tc.question,
        "data_mode": "live",
        "mode": "ai",
    }
    if tc.entity_id:
        payload["entity_id"] = tc.entity_id
    if tc.consolidate:
        payload["consolidate"] = True

    try:
        start = time.monotonic()
        resp = client.post(
            f"{BASE_URL}{NLQ_ENDPOINT}",
            json=payload,
            timeout=TIMEOUT,
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        if resp.status_code >= 400:
            return TestResult(
                qid=tc.qid, persona=tc.persona, question=tc.question,
                shape=tc.shape, passed=False,
                reason=f"HTTP_{resp.status_code}: {resp.text[:150]}",
                response_time_ms=elapsed_ms,
            )

        body = resp.json()
        validator = VALIDATORS[tc.shape]
        passed, reason = validator(body)

        answer = (body.get("answer") or "")[:120]
        ds = body.get("data_source") or ""

        return TestResult(
            qid=tc.qid, persona=tc.persona, question=tc.question,
            shape=tc.shape, passed=passed, reason=reason,
            answer_excerpt=answer, data_source=ds,
            response_time_ms=elapsed_ms, raw=body,
        )

    except httpx.TimeoutException:
        return TestResult(
            qid=tc.qid, persona=tc.persona, question=tc.question,
            shape=tc.shape, passed=False, reason="TIMEOUT",
        )
    except Exception as e:
        return TestResult(
            qid=tc.qid, persona=tc.persona, question=tc.question,
            shape=tc.shape, passed=False, reason=f"ERROR: {e}",
        )


def run_comparison_uf041(client: httpx.Client) -> TestResult:
    """UF_041: Cascadia revenue must differ from Meridian revenue.

    Queries revenue for both entities and asserts the values are different,
    proving entity-scoped data is not returning the same (default) result.
    """
    qid = "UF_041"
    question = "What is revenue for 2025?"
    results = {}

    for entity in ("meridian", "cascadia"):
        payload = {
            "question": question,
            "data_mode": "live",
            "mode": "ai",
            "entity_id": entity,
        }
        try:
            start = time.monotonic()
            resp = client.post(
                f"{BASE_URL}{NLQ_ENDPOINT}",
                json=payload,
                timeout=TIMEOUT,
            )
            elapsed_ms = (time.monotonic() - start) * 1000

            if resp.status_code >= 400:
                return TestResult(
                    qid=qid, persona="CFO", question=f"{question} [{entity}]",
                    shape="COMPARISON", passed=False,
                    reason=f"HTTP_{resp.status_code} for {entity}",
                    response_time_ms=elapsed_ms,
                )

            body = resp.json()
            if not body.get("success"):
                return TestResult(
                    qid=qid, persona="CFO", question=f"{question} [{entity}]",
                    shape="COMPARISON", passed=False,
                    reason=f"NOT_SUCCESS for {entity}: {body.get('error_message', '')}",
                )

            results[entity] = body.get("value")

        except Exception as e:
            return TestResult(
                qid=qid, persona="CFO", question=f"{question} [{entity}]",
                shape="COMPARISON", passed=False,
                reason=f"ERROR querying {entity}: {e}",
            )

    m_val = results.get("meridian")
    c_val = results.get("cascadia")

    if m_val is None or c_val is None:
        return TestResult(
            qid=qid, persona="CFO",
            question="Cascadia revenue != Meridian revenue",
            shape="COMPARISON", passed=False,
            reason=f"NULL_VALUE — meridian={m_val}, cascadia={c_val}",
        )

    if m_val == c_val:
        return TestResult(
            qid=qid, persona="CFO",
            question="Cascadia revenue != Meridian revenue",
            shape="COMPARISON", passed=False,
            reason=(
                f"VALUES_IDENTICAL — meridian={m_val}, cascadia={c_val}. "
                f"Entity scoping is broken (same data returned for both)."
            ),
        )

    return TestResult(
        qid=qid, persona="CFO",
        question="Cascadia revenue != Meridian revenue",
        shape="COMPARISON", passed=True,
        reason=f"OK (meridian={m_val}, cascadia={c_val} — values differ)",
    )


def run_all(verbose: bool = False) -> List[TestResult]:
    """Run all questions sequentially."""
    print("=" * 76)
    print("  NLQ Live Mode — Structural Test Harness")
    print(f"  {len(QUESTIONS)} questions + 1 comparison | data_mode=live | Validators: shape-only")
    print(f"  Endpoint: POST {BASE_URL}{NLQ_ENDPOINT}")
    print("=" * 76)

    # Health check
    try:
        check = httpx.get(f"{BASE_URL}/api/v1/health", timeout=5.0)
        health = check.json()
        live = health.get("live_data_available", False)
        print(f"\n  Server healthy | live_data_available={live}")
        if not live:
            print("  WARNING: live_data_available=false — tests may fail")
    except Exception as e:
        print(f"\n  ERROR: Cannot reach {BASE_URL}: {e}")
        sys.exit(1)

    results: List[TestResult] = []
    client = httpx.Client()

    print()
    for tc in QUESTIONS:
        r = run_one(client, tc)
        results.append(r)

        icon = "\u2713" if r.passed else "\u2717"
        status = "PASS" if r.passed else "FAIL"
        line = f"  {r.qid} [{r.persona:4s}] {icon} {status:4s} | {r.shape:14s} | {tc.question}"
        print(line)
        if not r.passed:
            print(f"         \u2192 {r.reason}")
        elif verbose:
            print(f"         \u2192 {r.reason}")

    # UF_041: comparison test — Cascadia revenue != Meridian revenue
    uf041 = run_comparison_uf041(client)
    results.append(uf041)
    icon = "\u2713" if uf041.passed else "\u2717"
    status = "PASS" if uf041.passed else "FAIL"
    line = f"  {uf041.qid} [{uf041.persona:4s}] {icon} {status:4s} | {'COMPARISON':14s} | {uf041.question}"
    print(line)
    if not uf041.passed:
        print(f"         \u2192 {uf041.reason}")
    elif verbose:
        print(f"         \u2192 {uf041.reason}")

    client.close()
    return results


# ---------------------------------------------------------------------------
# Summary + Markdown output
# ---------------------------------------------------------------------------

def print_summary(results: List[TestResult]):
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    by_shape: Dict[str, Dict[str, int]] = {}
    for r in results:
        bucket = by_shape.setdefault(r.shape, {"total": 0, "pass": 0, "fail": 0})
        bucket["total"] += 1
        if r.passed:
            bucket["pass"] += 1
        else:
            bucket["fail"] += 1

    print()
    print("=" * 76)
    print(f"  RESULTS: {passed}/{total} passed ({passed/total*100:.0f}%)")
    print()
    all_shapes = [POINT, BREAKDOWN, RANKING, INGEST_STATUS,
                   REPORT_ENTITY, BRIDGE_FORMAT, BRIDGE_SOURCE, "COMPARISON"]
    for shape in all_shapes:
        b = by_shape.get(shape, {"total": 0, "pass": 0, "fail": 0})
        if b["total"] > 0:
            print(f"    {shape:14s}  {b['pass']}/{b['total']}")
    print("=" * 76)


def write_markdown(results: List[TestResult], path: str = "LIVE_TEST_RESULTS.md"):
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    by_shape: Dict[str, Dict[str, int]] = {}
    for r in results:
        bucket = by_shape.setdefault(r.shape, {"total": 0, "pass": 0, "fail": 0})
        bucket["total"] += 1
        if r.passed:
            bucket["pass"] += 1
        else:
            bucket["fail"] += 1

    lines: List[str] = []
    lines.append("# NLQ Live Mode — Structural Test Results")
    lines.append("")
    lines.append(f"> Generated: {ts}")
    lines.append(f"> Endpoint: `POST {BASE_URL}{NLQ_ENDPOINT}` with `data_mode=live`")
    lines.append(f"> Validators: structural shape only (not numeric accuracy)")
    lines.append("")
    lines.append(f"## Summary: {passed}/{total} passed ({passed/total*100:.0f}%)")
    lines.append("")
    lines.append("| Shape | Pass | Total |")
    lines.append("|-------|------|-------|")
    all_shapes = [POINT, BREAKDOWN, RANKING, INGEST_STATUS,
                   REPORT_ENTITY, BRIDGE_FORMAT, BRIDGE_SOURCE, "COMPARISON"]
    for shape in all_shapes:
        b = by_shape.get(shape, {"total": 0, "pass": 0, "fail": 0})
        if b["total"] > 0:
            lines.append(f"| {shape} | {b['pass']} | {b['total']} |")
    lines.append("")

    # Full results table
    lines.append("## Detailed Results")
    lines.append("")
    lines.append("| # | Question | Shape | Result | Answer (excerpt) | data_source | Failure Reason |")
    lines.append("|---|----------|-------|--------|------------------|-------------|----------------|")

    for r in results:
        status = "PASS" if r.passed else "**FAIL**"
        answer = r.answer_excerpt.replace("|", "\\|").replace("\n", " ")[:80]
        ds = r.data_source or "—"
        reason = r.reason.replace("|", "\\|") if not r.passed else "—"
        lines.append(f"| {r.qid} | {r.question} | {r.shape} | {status} | {answer} | {ds} | {reason} |")

    lines.append("")

    # Failure analysis
    failures = [r for r in results if not r.passed]
    if failures:
        lines.append("## Failure Analysis")
        lines.append("")
        for r in failures:
            lines.append(f"### {r.qid} — {r.question}")
            lines.append(f"- **Shape**: {r.shape}")
            lines.append(f"- **Reason**: `{r.reason}`")
            lines.append(f"- **data_source**: `{r.data_source or 'n/a'}`")
            lines.append(f"- **answer**: {r.answer_excerpt[:200]}")
            if r.raw:
                lines.append(f"- **value**: `{r.raw.get('value')}`")
                lines.append(f"- **resolved_metric**: `{r.raw.get('resolved_metric')}`")
                lines.append(f"- **parsed_intent**: `{r.raw.get('parsed_intent')}`")
                dd = r.raw.get("dashboard_data")
                if dd:
                    lines.append(f"- **dashboard_data keys**: `{list(dd.keys()) if isinstance(dd, dict) else type(dd).__name__}`")
            lines.append("")

    md_text = "\n".join(lines) + "\n"
    Path(path).write_text(md_text)
    print(f"\n  Wrote {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    write_md = "--md" in sys.argv

    results = run_all(verbose=verbose)
    print_summary(results)

    if write_md or True:  # Always write MD for iteration tracking
        write_markdown(results)

    failed = sum(1 for r in results if not r.passed)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
