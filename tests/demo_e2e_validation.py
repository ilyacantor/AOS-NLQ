#!/usr/bin/env python3
"""
Demo Experience Harness — 100 Questions Your Prospects Will Ask
================================================================

Tests the demo experience — what a VP of Data, CIO, or SI partner actually
sees when they sit down with AOS for the first time. Every test goes through
NLQ. Every assertion checks answer QUALITY, not just "did it return something."

Guardrails:
  - Every test is a real HTTP POST to the NLQ endpoint
  - No modifying assertions to match broken output
  - Full request/response logged to disk
  - Sequential execution, 2s delay, 30s timeout
  - Outputs tests/demo_e2e_results.json and tests/demo_e2e_summary.txt

Run:
    python tests/demo_e2e_validation.py
    python tests/demo_e2e_validation.py --url http://localhost:8005
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "http://127.0.0.1:8005"
NLQ_ENDPOINT = "/api/v1/query"
TIMEOUT = 30
DELAY = 2

RESULTS_DIR = Path(__file__).resolve().parent
RESULTS_JSON = RESULTS_DIR / "demo_e2e_results.json"
SUMMARY_TXT = RESULTS_DIR / "demo_e2e_summary.txt"

# ---------------------------------------------------------------------------
# Quality check helpers
# ---------------------------------------------------------------------------

def has_data(answer, resp):
    bad = ["n/a", "no data", "i'm stumped", "i'm not sure", "head-scratcher",
           "insufficient data", "not available", "don't have data"]
    lower = answer.lower()
    for b in bad:
        if b in lower:
            return False, f"contains '{b}'"
    if not any(c.isdigit() for c in answer):
        return False, "no numeric data in answer"
    return True, "has data"


def professional(answer, resp):
    bad = ["TypeError", "Traceback", "{'concept'", "NoneType", "KeyError",
           "Exception", "error_code", "500"]
    for b in bad:
        if b in answer:
            return False, f"contains '{b}'"
    return True, "professional"


def has_dollar(answer, resp):
    if "$" not in answer:
        return False, "missing $ sign"
    return True, "has dollar sign"


def has_percent(answer, resp):
    if "%" not in answer:
        return False, "missing % sign"
    return True, "has percentage"


def responsive(answer, resp):
    ms = resp.get("response_time_ms", 99999)
    if ms > 15000:
        return False, f"took {ms}ms (>15s)"
    return True, f"{ms}ms"


def not_about(wrong_topics):
    def check(answer, resp):
        lower = answer.lower()
        for topic in wrong_topics:
            if topic.lower() in lower and len(answer) < 200:
                return False, f"answer is about '{topic}' instead of the question"
        return True, "on topic"
    return check


def mentions_all(required_terms):
    def check(answer, resp):
        lower = answer.lower()
        missing = [t for t in required_terms if t.lower() not in lower]
        if missing:
            return False, f"missing: {missing}"
        return True, f"contains all: {required_terms}"
    return check


def mentions_any(terms):
    def check(answer, resp):
        lower = answer.lower()
        found = [t for t in terms if t.lower() in lower]
        if not found:
            return False, f"none of {terms} found"
        return True, f"found: {found}"
    return check


def is_dashboard(answer, resp):
    rt = resp.get("response_type", "")
    if rt != "dashboard":
        return False, f"response_type='{rt}', expected 'dashboard'"
    return True, "is dashboard"


def no_empty_widgets(answer, resp):
    body = str(resp)
    if "No data" in body or "no data" in body:
        return False, "dashboard has 'No data' widgets"
    return True, "all widgets populated"


def indicates_direction(answer, resp):
    direction_words = ["up", "down", "increase", "decrease", "grew", "declined",
                       "rose", "fell", "higher", "lower", "growth", "drop",
                       "improved", "worsened", "rising", "falling"]
    lower = answer.lower()
    if any(w in lower for w in direction_words):
        return True, "indicates direction"
    return False, "no directional language"


def multi_value(answer, resp):
    numbers = re.findall(r'[\d]+\.?\d*', answer)
    unique = set(numbers)
    if len(unique) < 2:
        return False, f"only {len(unique)} distinct number(s)"
    return True, f"{len(unique)} distinct values"


def no_crash(answer, resp):
    """Passes as long as we got a non-error response."""
    if resp.get("_http_error"):
        return False, f"HTTP error: {resp['_http_error']}"
    return True, "no crash"


def has_data_or_dashboard(answer, resp):
    """Passes if has_data OR is_dashboard."""
    d_pass, _ = is_dashboard(answer, resp)
    if d_pass:
        return True, "is dashboard"
    h_pass, h_detail = has_data(answer, resp)
    if h_pass:
        return True, "has data"
    return False, f"neither dashboard nor data: {h_detail}"


def has_data_or_professional(answer, resp):
    """Passes if has_data OR at least professional response."""
    h_pass, _ = has_data(answer, resp)
    if h_pass:
        return True, "has data"
    p_pass, _ = professional(answer, resp)
    if p_pass and len(answer) > 20:
        return True, "professional explanation (no raw data)"
    return False, "no data and not a professional explanation"


def has_data_or_guidance(answer, resp):
    """Passes if has_data OR provides thoughtful response (>50 chars, professional)."""
    h_pass, _ = has_data(answer, resp)
    if h_pass:
        return True, "has data"
    p_pass, _ = professional(answer, resp)
    if p_pass and len(answer) > 50:
        return True, "thoughtful guidance"
    return False, "no data and no substantive guidance"


def has_dollar_or_number(answer, resp):
    if "$" in answer:
        return True, "has dollar sign"
    if any(c.isdigit() for c in answer):
        return True, "has number"
    return False, "no dollar sign or number"


def formatted_number(answer, resp):
    """Check that large numbers aren't raw 9-digit strings without formatting."""
    raw_big = re.findall(r'(?<!\d)\d{7,}(?!\d)', answer)
    if raw_big:
        return False, f"unformatted large number: {raw_big[0]}"
    return True, "numbers formatted"


# ---------------------------------------------------------------------------
# Quality check runner
# ---------------------------------------------------------------------------

def quality_check(response, checks):
    answer = str(response.get("answer", "") or "")
    results = {}
    for name, fn in checks.items():
        try:
            passed, detail = fn(answer, response)
            results[name] = {"passed": passed, "detail": detail}
        except Exception as e:
            results[name] = {"passed": False, "detail": f"assertion error: {e}"}
    return results


# ---------------------------------------------------------------------------
# 100 Tests
# ---------------------------------------------------------------------------

TESTS = [
    # ===== Category A: CFO Point Queries (10) =====
    {"id": 1, "name": "A1: revenue this quarter", "category": "A: CFO Point Queries",
     "query": "What's our revenue this quarter?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "has_dollar": has_dollar, "responsive": responsive}},

    {"id": 2, "name": "A2: margins", "category": "A: CFO Point Queries",
     "query": "What are our margins?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent,
                "mentions_all": mentions_all(["gross", "operating", "net"]),
                "not_about": not_about(["accounts receivable", "ar "])}},

    {"id": 3, "name": "A3: EBITDA", "category": "A: CFO Point Queries",
     "query": "What's EBITDA?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "has_dollar": has_dollar, "responsive": responsive}},

    {"id": 4, "name": "A4: net income", "category": "A: CFO Point Queries",
     "query": "What's net income?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "has_dollar": has_dollar, "formatted": formatted_number}},

    {"id": 5, "name": "A5: cash position", "category": "A: CFO Point Queries",
     "query": "What's our cash position?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "has_dollar": has_dollar}},

    {"id": 6, "name": "A6: ARR", "category": "A: CFO Point Queries",
     "query": "What's ARR?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "has_dollar": has_dollar}},

    {"id": 7, "name": "A7: are we profitable", "category": "A: CFO Point Queries",
     "query": "Are we profitable?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["yes", "no", "profitable", "profit", "margin", "income"]),
                "not_about": not_about(["accounts receivable", "n/a"])}},

    {"id": 8, "name": "A8: burn rate", "category": "A: CFO Point Queries",
     "query": "What's our burn rate?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "not_about": not_about(["accounts receivable"])}},

    {"id": 9, "name": "A9: cost structure", "category": "A: CFO Point Queries",
     "query": "What's our cost structure look like?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["cogs", "cost", "opex", "expense", "sg&a"])}},

    {"id": 10, "name": "A10: runway", "category": "A: CFO Point Queries",
     "query": "How much runway do we have?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["months", "runway", "cash", "burn"])}},

    # ===== Category B: CRO Point Queries (10) =====
    {"id": 11, "name": "B1: pipeline", "category": "B: CRO Point Queries",
     "query": "How's pipeline looking?", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional, "has_dollar_or_number": has_dollar_or_number}},

    {"id": 12, "name": "B2: win rate", "category": "B: CRO Point Queries",
     "query": "What's our win rate?", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent}},

    {"id": 13, "name": "B3: churn", "category": "B: CRO Point Queries",
     "query": "What's churn?", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent,
                "not_about": not_about(["accounts receivable"])}},

    {"id": 14, "name": "B4: NRR", "category": "B: CRO Point Queries",
     "query": "What's NRR?", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent}},

    {"id": 15, "name": "B5: quota attainment", "category": "B: CRO Point Queries",
     "query": "Are we hitting quota?", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent,
                "mentions_any": mentions_any(["quota", "attainment"]),
                "not_zero_attainment": lambda answer, resp: (False, "0% attainment cannot be 'Yes'") if "0%" in answer.replace(" ", "") and "yes" in answer.lower() else (True, "ok")}},

    {"id": 16, "name": "B6: sales cycle", "category": "B: CRO Point Queries",
     "query": "How long is our sales cycle?", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional, "mentions_any": mentions_any(["days", "cycle"])}},

    {"id": 17, "name": "B7: bookings last quarter", "category": "B: CRO Point Queries",
     "query": "What did we book last quarter?", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["booking", "closed", "deal", "booked"])}},

    {"id": 18, "name": "B8: customer count", "category": "B: CRO Point Queries",
     "query": "How many customers do we have?", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional}},

    {"id": 19, "name": "B9: expansion revenue", "category": "B: CRO Point Queries",
     "query": "What's our expansion revenue?", "persona": "CRO",
     "checks": {"professional": professional, "responsive": responsive}},

    {"id": 20, "name": "B10: sales scorecard", "category": "B: CRO Point Queries",
     "query": "Show me the sales scorecard", "persona": "CRO",
     "checks": {"professional": professional, "responsive": responsive, "has_data_or_dashboard": has_data_or_dashboard,
                "not_about": not_about(["accounts receivable"])}},

    # ===== Category C: COO/CTO/CHRO Point Queries (10) =====
    {"id": 21, "name": "C1: headcount", "category": "C: COO/CTO/CHRO Queries",
     "query": "What's our headcount?", "persona": "COO",
     "checks": {"has_data": has_data, "professional": professional}},

    {"id": 22, "name": "C2: revenue per employee", "category": "C: COO/CTO/CHRO Queries",
     "query": "Revenue per employee?", "persona": "COO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["per employee", "per head", "$"]),
                "value_in_range": lambda answer, resp: (False, f"value {resp.get('value')} too large for per-employee metric") if resp.get("value") and resp.get("value", 0) > 1.0 and resp.get("unit") == "usd_millions" else (True, "value in range")}},

    {"id": 23, "name": "C3: platform uptime", "category": "C: COO/CTO/CHRO Queries",
     "query": "What's platform uptime?", "persona": "CTO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent}},

    {"id": 24, "name": "C4: P1 incidents", "category": "C: COO/CTO/CHRO Queries",
     "query": "How many P1 incidents this quarter?", "persona": "CTO",
     "checks": {"has_data": has_data, "professional": professional, "not_about": not_about(["accounts receivable"])}},

    {"id": 25, "name": "C5: MTTR", "category": "C: COO/CTO/CHRO Queries",
     "query": "What's our MTTR?", "persona": "CTO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["hours", "minutes", "time", "resolve"])}},

    {"id": 26, "name": "C6: attrition", "category": "C: COO/CTO/CHRO Queries",
     "query": "What's attrition looking like?", "persona": "CHRO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent}},

    {"id": 27, "name": "C7: employee engagement", "category": "C: COO/CTO/CHRO Queries",
     "query": "How's employee engagement?", "persona": "CHRO",
     "checks": {"has_data": has_data, "professional": professional}},

    {"id": 28, "name": "C8: open roles", "category": "C: COO/CTO/CHRO Queries",
     "query": "How many open roles do we have?", "persona": "CHRO",
     "checks": {"has_data": has_data, "professional": professional}},

    {"id": 29, "name": "C9: time to hire", "category": "C: COO/CTO/CHRO Queries",
     "query": "What's our time to hire?", "persona": "CHRO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["days", "time", "hire"])}},

    {"id": 30, "name": "C10: deployment frequency", "category": "C: COO/CTO/CHRO Queries",
     "query": "Deployment frequency this quarter?", "persona": "CTO",
     "checks": {"has_data": has_data, "professional": professional}},

    # ===== Category D: Dashboards That Work (10) =====
    {"id": 31, "name": "D1: CFO dashboard", "category": "D: Dashboards That Work",
     "query": "Build me a CFO dashboard", "persona": "CFO",
     "checks": {"is_dashboard": is_dashboard, "no_empty_widgets": no_empty_widgets, "responsive": responsive}},

    {"id": 32, "name": "D2: CRO dashboard", "category": "D: Dashboards That Work",
     "query": "Build me a CRO dashboard", "persona": "CRO",
     "checks": {"is_dashboard": is_dashboard, "no_empty_widgets": no_empty_widgets, "responsive": responsive}},

    {"id": 33, "name": "D3: COO dashboard", "category": "D: Dashboards That Work",
     "query": "Build me a COO dashboard", "persona": "COO",
     "checks": {"is_dashboard": is_dashboard, "no_empty_widgets": no_empty_widgets, "responsive": responsive}},

    {"id": 34, "name": "D4: CTO dashboard", "category": "D: Dashboards That Work",
     "query": "Build me a CTO dashboard", "persona": "CTO",
     "checks": {"is_dashboard": is_dashboard, "no_empty_widgets": no_empty_widgets, "responsive": responsive}},

    {"id": 35, "name": "D5: CHRO dashboard", "category": "D: Dashboards That Work",
     "query": "Build me a CHRO dashboard", "persona": "CHRO",
     "checks": {"is_dashboard": is_dashboard, "no_empty_widgets": no_empty_widgets, "responsive": responsive}},

    {"id": 36, "name": "D6: how are we doing (CFO)", "category": "D: Dashboards That Work",
     "query": "How are we doing?", "persona": "CFO",
     "checks": {"is_dashboard": is_dashboard, "no_empty_widgets": no_empty_widgets, "responsive": responsive}},

    {"id": 37, "name": "D7: how are we doing (CRO)", "category": "D: Dashboards That Work",
     "query": "How are we doing?", "persona": "CRO",
     "checks": {"is_dashboard": is_dashboard, "no_empty_widgets": no_empty_widgets, "responsive": responsive}},

    {"id": 38, "name": "D8: how are we doing (COO)", "category": "D: Dashboards That Work",
     "query": "How are we doing?", "persona": "COO",
     "checks": {"is_dashboard": is_dashboard, "no_empty_widgets": no_empty_widgets, "responsive": responsive}},

    {"id": 39, "name": "D9: 2025 KPIs dashboard", "category": "D: Dashboards That Work",
     "query": "2025 KPIs in a dashboard", "persona": "CFO",
     "checks": {"is_dashboard": is_dashboard, "responsive": responsive}},

    {"id": 40, "name": "D10: executive summary", "category": "D: Dashboards That Work",
     "query": "Show me the executive summary", "persona": "CFO",
     "checks": {"has_data_or_dashboard": has_data_or_dashboard, "professional": professional, "responsive": responsive}},

    # ===== Category E: Comparisons and Trends (15) =====
    {"id": 41, "name": "E1: Q1 vs Q2 revenue", "category": "E: Comparisons and Trends",
     "query": "Compare Q1 vs Q2 2025 revenue", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "multi_value": multi_value}},

    {"id": 42, "name": "E2: revenue trend this year", "category": "E: Comparisons and Trends",
     "query": "How has revenue trended this year?", "persona": "CFO",
     "checks": {"has_data_or_dashboard": has_data_or_dashboard, "professional": professional, "responsive": responsive}},

    {"id": 43, "name": "E3: revenue growth YoY", "category": "E: Comparisons and Trends",
     "query": "Revenue growth year over year", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["growth", "%", "increase", "grew"])}},

    {"id": 44, "name": "E4: gross vs net margin", "category": "E: Comparisons and Trends",
     "query": "Compare gross vs net margin", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "multi_value": multi_value, "has_percent": has_percent}},

    {"id": 45, "name": "E5: margin this vs last quarter", "category": "E: Comparisons and Trends",
     "query": "Margin this quarter vs last", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "multi_value": multi_value, "has_percent": has_percent}},

    {"id": 46, "name": "E6: pipeline change this year", "category": "E: Comparisons and Trends",
     "query": "How has pipeline changed this year?", "persona": "CRO",
     "checks": {"has_data_or_dashboard": has_data_or_dashboard, "professional": professional, "responsive": responsive}},

    {"id": 47, "name": "E7: revenue direction", "category": "E: Comparisons and Trends",
     "query": "Is revenue going up or down?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "indicates_direction": indicates_direction}},

    {"id": 48, "name": "E8: churn rate last 3 quarters", "category": "E: Comparisons and Trends",
     "query": "Churn rate last 3 quarters", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent}},

    {"id": 49, "name": "E9: ARR trend since Q1 2025", "category": "E: Comparisons and Trends",
     "query": "ARR trend since Q1 2025", "persona": "CFO",
     "checks": {"has_data_or_dashboard": has_data_or_dashboard, "professional": professional, "responsive": responsive}},

    {"id": 50, "name": "E10: bookings this vs last year", "category": "E: Comparisons and Trends",
     "query": "Bookings this year vs last year", "persona": "CRO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive}},

    {"id": 51, "name": "E11: best revenue quarter", "category": "E: Comparisons and Trends",
     "query": "Which quarter had the best revenue?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["q1", "q2", "q3", "q4"])}},

    {"id": 52, "name": "E12: headcount growth YoY", "category": "E: Comparisons and Trends",
     "query": "Year over year headcount growth", "persona": "COO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive}},

    {"id": 53, "name": "E13: pipeline trend 4 quarters", "category": "E: Comparisons and Trends",
     "query": "Pipeline trend last 4 quarters", "persona": "CRO",
     "checks": {"has_data_or_dashboard": has_data_or_dashboard, "professional": professional, "responsive": responsive}},

    {"id": 54, "name": "E14: margins 2024 to 2025", "category": "E: Comparisons and Trends",
     "query": "How did margins change from 2024 to 2025?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent}},

    {"id": 55, "name": "E15: NRR trend", "category": "E: Comparisons and Trends",
     "query": "NRR trend", "persona": "CRO",
     "checks": {"has_data_or_dashboard": has_data_or_dashboard, "professional": professional, "responsive": responsive}},

    # ===== Category F: Causal and Analytical (10) =====
    {"id": 56, "name": "F1: why did revenue increase", "category": "F: Causal and Analytical",
     "query": "Why did revenue increase?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive,
                "not_about": not_about(["accounts receivable"])}},

    {"id": 57, "name": "F2: margin improvement driver", "category": "F: Causal and Analytical",
     "query": "What's driving margin improvement?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive}},

    {"id": 58, "name": "F3: biggest cost driver", "category": "F: Causal and Analytical",
     "query": "What's our biggest cost driver?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional,
                "mentions_any": mentions_any(["cost", "cogs", "opex", "expense"])}},

    {"id": 59, "name": "F4: why is churn going up", "category": "F: Causal and Analytical",
     "query": "Why is churn going up?", "persona": "CRO",
     "checks": {"professional": professional, "responsive": responsive}},

    {"id": 60, "name": "F5: win rate impact", "category": "F: Causal and Analytical",
     "query": "What's impacting win rate?", "persona": "CRO",
     "checks": {"professional": professional, "responsive": responsive}},

    {"id": 61, "name": "F6: revenue by segment", "category": "F: Causal and Analytical",
     "query": "Break down revenue by segment", "persona": "CRO",
     "checks": {"has_data_or_professional": has_data_or_professional, "responsive": responsive}},

    {"id": 62, "name": "F7: top performing region", "category": "F: Causal and Analytical",
     "query": "Top performing region", "persona": "CRO",
     "checks": {"has_data_or_professional": has_data_or_professional, "responsive": responsive}},

    {"id": 63, "name": "F8: highest attrition dept", "category": "F: Causal and Analytical",
     "query": "Which department has the highest attrition?", "persona": "CHRO",
     "checks": {"has_data_or_professional": has_data_or_professional, "responsive": responsive}},

    {"id": 64, "name": "F9: biggest risk", "category": "F: Causal and Analytical",
     "query": "What's the biggest risk to the business?", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive, "has_data_or_guidance": has_data_or_guidance}},

    {"id": 65, "name": "F10: what to focus on", "category": "F: Causal and Analytical",
     "query": "What should I focus on this quarter?", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive, "has_data_or_guidance": has_data_or_guidance}},

    # ===== Category G: P&L and Financials (10) =====
    {"id": 66, "name": "G1: show P&L", "category": "G: P&L and Financials",
     "query": "Show me the P&L", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive,
                "mentions_all": mentions_all(["revenue", "gross"]), "multi_value": multi_value}},

    {"id": 67, "name": "G2: full P&L 2025", "category": "G: P&L and Financials",
     "query": "Full P&L for 2025", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive,
                "mentions_any": mentions_any(["revenue", "cogs", "gross"]), "multi_value": multi_value}},

    {"id": 68, "name": "G3: P&L Q1 2026", "category": "G: P&L and Financials",
     "query": "P&L for Q1 2026", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive, "multi_value": multi_value}},

    {"id": 69, "name": "G4: all margins", "category": "G: P&L and Financials",
     "query": "Show me all the margins", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "has_percent": has_percent,
                "mentions_all": mentions_all(["gross", "operating", "net"])}},

    {"id": 70, "name": "G5: gross margin trend", "category": "G: P&L and Financials",
     "query": "What's the gross margin trend?", "persona": "CFO",
     "checks": {"has_data_or_dashboard": has_data_or_dashboard, "professional": professional, "responsive": responsive}},

    {"id": 71, "name": "G6: revenue COGS gross profit", "category": "G: P&L and Financials",
     "query": "Revenue, COGS, and gross profit", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "multi_value": multi_value, "has_dollar": has_dollar}},

    {"id": 72, "name": "G7: opex breakdown", "category": "G: P&L and Financials",
     "query": "Operating expenses breakdown", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive}},

    {"id": 73, "name": "G8: EBITDA and net income", "category": "G: P&L and Financials",
     "query": "EBITDA and net income", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "multi_value": multi_value, "has_dollar": has_dollar,
                "mentions_all": mentions_all(["ebitda", "net income"])}},

    {"id": 74, "name": "G9: financial health", "category": "G: P&L and Financials",
     "query": "What's our financial health?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive,
                "mentions_any": mentions_any(["revenue", "margin", "profit", "cash"])}},

    {"id": 75, "name": "G10: board deck metrics", "category": "G: P&L and Financials",
     "query": "Board deck metrics", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive, "multi_value": multi_value,
                "no_none": lambda answer, resp: (False, "answer contains 'None'") if "None" in answer else (True, "no None")}},

    # ===== Category H: Demo Showstoppers (15) =====
    {"id": 76, "name": "H1: quick overview", "category": "H: Demo Showstoppers",
     "query": "Give me a quick overview", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive, "multi_value": multi_value}},

    {"id": 77, "name": "H2: how's the business", "category": "H: Demo Showstoppers",
     "query": "How's the business doing?", "persona": "CFO",
     "checks": {"has_data_or_dashboard": has_data_or_dashboard, "professional": professional, "responsive": responsive}},

    {"id": 78, "name": "H3: what should I worry about", "category": "H: Demo Showstoppers",
     "query": "What should I worry about?", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive, "has_data_or_guidance": has_data_or_guidance}},

    {"id": 79, "name": "H4: TL;DR", "category": "H: Demo Showstoppers",
     "query": "Give me the TL;DR", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive}},

    {"id": 80, "name": "H5: KPIs", "category": "H: Demo Showstoppers",
     "query": "What are our KPIs?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive}},

    {"id": 81, "name": "H6: show me something interesting", "category": "H: Demo Showstoppers",
     "query": "Show me something interesting", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive}},

    {"id": 82, "name": "H7: last quarter", "category": "H: Demo Showstoppers",
     "query": "How did last quarter go?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive, "multi_value": multi_value,
                "not_about": not_about(["accounts receivable"]),
                "mentions_any": mentions_any(["revenue", "margin", "profit", "ebitda", "growth"])}},

    {"id": 83, "name": "H8: what changed since last quarter", "category": "H: Demo Showstoppers",
     "query": "What's changed since last quarter?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive,
                "indicates_direction": indicates_direction}},

    {"id": 84, "name": "H9: are we on track", "category": "H: Demo Showstoppers",
     "query": "Are we on track?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive}},

    {"id": 85, "name": "H10: what does the data tell us", "category": "H: Demo Showstoppers",
     "query": "What does the data tell us?", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive,
                "mentions_any": mentions_any(["revenue", "margin", "profit", "cash", "ebitda", "growth", "financial"])}},

    {"id": 86, "name": "H11: run through the numbers", "category": "H: Demo Showstoppers",
     "query": "Run me through the numbers", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive, "multi_value": multi_value}},

    {"id": 87, "name": "H12: new CRO catch me up", "category": "H: Demo Showstoppers",
     "query": "I'm the new CRO, catch me up", "persona": "CRO",
     "checks": {"has_data_or_dashboard": has_data_or_dashboard, "professional": professional, "responsive": responsive,
                "no_dollar_on_pct": lambda answer, resp: (False, "Win Rate shown with $ sign") if re.search(r'\$[\d.]+[MmBb]?\s*(?:win\s*rate|churn|nrr|attainment)', answer, re.IGNORECASE) or re.search(r'(?:win\s*rate|churn|nrr|attainment)[^.]{0,20}\$[\d.]+[MmBb]', answer, re.IGNORECASE) else (True, "no dollar on pct metrics")}},

    {"id": 88, "name": "H13: quick health check", "category": "H: Demo Showstoppers",
     "query": "Quick health check", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "responsive": responsive}},

    {"id": 89, "name": "H14: anything unusual", "category": "H: Demo Showstoppers",
     "query": "Anything unusual in the data?", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive}},

    {"id": 90, "name": "H15: let's start with revenue", "category": "H: Demo Showstoppers",
     "query": "Let's start with revenue", "persona": "CFO",
     "checks": {"has_data": has_data, "professional": professional, "has_dollar": has_dollar, "responsive": responsive,
                "not_about": not_about(["accounts receivable"]),
                "mentions_any": mentions_any(["revenue"])}},

    # ===== Category I: Edge Cases (10) =====
    {"id": 91, "name": "I1: hi", "category": "I: Edge Cases",
     "query": "hi", "persona": None,
     "checks": {"professional": professional, "responsive": responsive, "no_crash": no_crash}},

    {"id": 92, "name": "I2: thanks", "category": "I: Edge Cases",
     "query": "thanks", "persona": None,
     "checks": {"professional": professional, "responsive": responsive, "no_crash": no_crash}},

    {"id": 93, "name": "I3: go back", "category": "I: Edge Cases",
     "query": "go back", "persona": None,
     "checks": {"professional": professional, "responsive": responsive, "no_crash": no_crash}},

    {"id": 94, "name": "I4: more detail", "category": "I: Edge Cases",
     "query": "more detail", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive, "no_crash": no_crash}},

    {"id": 95, "name": "I5: can you explain that", "category": "I: Edge Cases",
     "query": "can you explain that?", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive, "no_crash": no_crash}},

    {"id": 96, "name": "I6: what about last year", "category": "I: Edge Cases",
     "query": "what about last year?", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive}},

    {"id": 97, "name": "I7: break that down", "category": "I: Edge Cases",
     "query": "break that down", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive}},

    {"id": 98, "name": "I8: that doesn't look right", "category": "I: Edge Cases",
     "query": "hmm that doesn't look right", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive}},

    {"id": 99, "name": "I9: show me more", "category": "I: Edge Cases",
     "query": "show me more", "persona": "CFO",
     "checks": {"professional": professional, "responsive": responsive}},

    {"id": 100, "name": "I10: actually show CRO metrics", "category": "I: Edge Cases",
     "query": "actually show me CRO metrics", "persona": "CRO",
     "checks": {"professional": professional, "responsive": responsive,
                "mentions_any": mentions_any(["pipeline", "win", "churn", "booking", "quota"])}},
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_test(base_url, test):
    payload = {
        "question": test["query"],
        "data_mode": "live",
        "mode": "ai",
    }
    if test["persona"]:
        payload["persona"] = test["persona"]

    result = {
        "id": test["id"],
        "name": test["name"],
        "category": test["category"],
        "query": test["query"],
        "persona": test["persona"],
        "request_body": payload,
        "response_body": {},
        "response_time_ms": 0,
        "checks": {},
        "passed": False,
        "answer_preview": "",
    }

    try:
        start = time.monotonic()
        resp = requests.post(
            f"{base_url}{NLQ_ENDPOINT}",
            json=payload,
            timeout=TIMEOUT,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code >= 400:
            body = {"_http_error": f"HTTP {resp.status_code}", "answer": "", "response_time_ms": elapsed_ms}
        else:
            body = resp.json()
            body["response_time_ms"] = elapsed_ms

        result["response_body"] = body
        result["response_time_ms"] = elapsed_ms
        result["answer_preview"] = str(body.get("answer", "") or "")[:200]

        checks = quality_check(body, test["checks"])
        result["checks"] = checks
        result["passed"] = all(c["passed"] for c in checks.values())

    except requests.exceptions.Timeout:
        result["response_body"] = {"_http_error": "TIMEOUT", "answer": "", "response_time_ms": TIMEOUT * 1000}
        result["response_time_ms"] = TIMEOUT * 1000
        result["checks"] = {"timeout": {"passed": False, "detail": f"request timed out after {TIMEOUT}s"}}
    except requests.exceptions.ConnectionError as e:
        result["response_body"] = {"_http_error": f"CONNECTION_ERROR: {e}", "answer": ""}
        result["checks"] = {"connection": {"passed": False, "detail": str(e)[:200]}}
    except Exception as e:
        result["response_body"] = {"_http_error": f"ERROR: {e}", "answer": ""}
        result["checks"] = {"error": {"passed": False, "detail": str(e)[:200]}}

    return result


def run_all(base_url):
    print("=" * 70)
    print("  DEMO EXPERIENCE HARNESS -- 100 Questions")
    print(f"  Endpoint: POST {base_url}{NLQ_ENDPOINT}")
    print(f"  {len(TESTS)} tests | data_mode=live | mode=ai")
    print(f"  Timeout: {TIMEOUT}s | Delay: {DELAY}s")
    print("=" * 70)

    # Health check
    try:
        h = requests.get(f"{base_url}/api/v1/health", timeout=5)
        print(f"\n  Server healthy (HTTP {h.status_code})")
    except Exception as e:
        print(f"\n  ERROR: Cannot reach {base_url}: {e}")
        sys.exit(1)

    results = []
    print()

    for i, test in enumerate(TESTS):
        if i > 0:
            time.sleep(DELAY)

        r = run_test(base_url, test)
        results.append(r)

        icon = "PASS" if r["passed"] else "FAIL"
        tag = f"[{test['persona'] or '---':4s}]"
        print(f"  {test['id']:3d}. {icon} {tag} {test['name']}")

        if not r["passed"]:
            failed_checks = {k: v["detail"] for k, v in r["checks"].items() if not v["passed"]}
            print(f"        -> {failed_checks}")

    return results


# ---------------------------------------------------------------------------
# Summary and output
# ---------------------------------------------------------------------------

CATEGORY_ORDER = [
    "A: CFO Point Queries",
    "B: CRO Point Queries",
    "C: COO/CTO/CHRO Queries",
    "D: Dashboards That Work",
    "E: Comparisons and Trends",
    "F: Causal and Analytical",
    "G: P&L and Financials",
    "H: Demo Showstoppers",
    "I: Edge Cases",
]

CATEGORY_TOTALS = {
    "A: CFO Point Queries": 10,
    "B: CRO Point Queries": 10,
    "C: COO/CTO/CHRO Queries": 10,
    "D: Dashboards That Work": 10,
    "E: Comparisons and Trends": 15,
    "F: Causal and Analytical": 10,
    "G: P&L and Financials": 10,
    "H: Demo Showstoppers": 15,
    "I: Edge Cases": 10,
}


def classify_failures(results):
    """Classify failures into buckets."""
    counts = {
        "No data (N/A / stumped)": 0,
        "Wrong metric": 0,
        "Unprofessional (errors)": 0,
        "Too slow (>15s)": 0,
        "Missing formatting": 0,
        "Incomplete (partial answer)": 0,
        "Connection/timeout": 0,
    }
    for r in results:
        if r["passed"]:
            continue
        checks = r["checks"]
        if "timeout" in checks or "connection" in checks or "error" in checks:
            counts["Connection/timeout"] += 1
            continue
        if not checks.get("has_data", {}).get("passed", True):
            counts["No data (N/A / stumped)"] += 1
        if not checks.get("professional", {}).get("passed", True):
            counts["Unprofessional (errors)"] += 1
        if not checks.get("responsive", {}).get("passed", True):
            counts["Too slow (>15s)"] += 1
        if not checks.get("not_about", {}).get("passed", True):
            counts["Wrong metric"] += 1
        formatting_checks = ["has_dollar", "has_percent", "formatted", "has_dollar_or_number"]
        if any(not checks.get(fc, {}).get("passed", True) for fc in formatting_checks):
            counts["Missing formatting"] += 1
        partial_checks = ["multi_value", "mentions_all", "mentions_any", "indicates_direction"]
        if any(not checks.get(pc, {}).get("passed", True) for pc in partial_checks):
            counts["Incomplete (partial answer)"] += 1
    return counts


def build_summary(results, base_url):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    # Category breakdown
    cat_pass = {}
    for r in results:
        cat = r["category"]
        cat_pass.setdefault(cat, 0)
        if r["passed"]:
            cat_pass[cat] += 1

    lines = []
    lines.append(f"DEMO EXPERIENCE HARNESS -- {ts}")
    lines.append(f"Endpoint: {base_url}{NLQ_ENDPOINT}")
    lines.append("=" * 60)
    lines.append(f"OVERALL: {passed}/{total} ({passed*100//total}%)")
    lines.append("")
    lines.append("CATEGORY BREAKDOWN:")
    for cat in CATEGORY_ORDER:
        p = cat_pass.get(cat, 0)
        t = CATEGORY_TOTALS[cat]
        lines.append(f"  {cat:30s} {p}/{t}")

    # Failed tests
    failures = [r for r in results if not r["passed"]]
    if failures:
        lines.append("")
        lines.append("FAILED TESTS:")
        for r in failures:
            lines.append(f"  [{r['id']:3d}] {r['name']}")
            lines.append(f"    Query: \"{r['query']}\"")
            lines.append(f"    Answer (preview): \"{r['answer_preview'][:150]}\"")
            failed_checks = [(k, v["detail"]) for k, v in r["checks"].items() if not v["passed"]]
            lines.append(f"    Failed checks: {', '.join(f'{k} ({d})' for k, d in failed_checks)}")
            lines.append("")

    # Failure classification
    fc = classify_failures(results)
    lines.append("FAILURE CLASSIFICATION:")
    for label, count in fc.items():
        lines.append(f"  {label:30s} {count}")

    return "\n".join(lines)


def print_category_detail(results, category_name):
    """Print every answer for a given category, pass or fail."""
    cat_results = [r for r in results if r["category"] == category_name]
    print(f"\n{'=' * 70}")
    print(f"  {category_name} -- FULL DETAIL")
    print(f"{'=' * 70}")
    for r in cat_results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"\n  [{r['id']}] {r['name']} -- {status}")
        print(f"  Query: \"{r['query']}\"")
        print(f"  Answer: \"{r['answer_preview']}\"")
        print(f"  Time: {r['response_time_ms']}ms")
        for ck, cv in r["checks"].items():
            icon = "OK" if cv["passed"] else "XX"
            print(f"    {icon} {ck}: {cv['detail']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    base_url = DEFAULT_BASE_URL
    for arg in sys.argv[1:]:
        if arg.startswith("--url"):
            if "=" in arg:
                base_url = arg.split("=", 1)[1]
            else:
                idx = sys.argv.index(arg)
                if idx + 1 < len(sys.argv):
                    base_url = sys.argv[idx + 1]

    results = run_all(base_url)

    # Write results JSON (full request + response bodies)
    with open(RESULTS_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Wrote {RESULTS_JSON}")

    # Build and write summary
    summary = build_summary(results, base_url)
    with open(SUMMARY_TXT, "w") as f:
        f.write(summary)
    print(f"  Wrote {SUMMARY_TXT}")

    # Print summary
    print(f"\n{summary}")

    # Print Category H and G in full
    print_category_detail(results, "H: Demo Showstoppers")
    print_category_detail(results, "G: P&L and Financials")

    # Exit code
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
