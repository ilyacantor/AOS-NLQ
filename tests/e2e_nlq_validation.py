#!/usr/bin/env python3
"""NLQ E2E Test Harness - 100 questions, real HTTP requests, no cheating.

Anti-cheat rules enforced:
- Every test is a real HTTP POST
- No mocks, stubs, or fixtures
- No assertion weakening
- Full request/response logging
- Sequential with 2s delay
- 30s timeout per request
- No cache manipulation
- Self-contained: stdlib + requests only
"""

import requests
import json
import time
import sys
import os
import re
from datetime import datetime


PROD_URL = "https://aos-nlq.onrender.com/api/v1/query"
LOCAL_URL = "http://localhost:8005/api/v1/query"
TIMEOUT = 30
DELAY = 2


# ── Helper functions for assertions ──────────────────────────────────────

def has_success(data):
    return data.get("success") is True


def get_answer(data):
    """Extract answer text from response, handling nested structures."""
    answer = data.get("answer", "")
    if isinstance(answer, dict):
        return json.dumps(answer)
    return str(answer) if answer else ""


def get_response_type(data):
    return data.get("response_type", "")


def answer_contains_any(data, terms):
    """Check if answer contains any of the given terms (case insensitive)."""
    answer = get_answer(data).lower()
    resp_str = json.dumps(data).lower()
    return any(t.lower() in answer or t.lower() in resp_str for t in terms)


def answer_not_contains(data, terms):
    """Check answer does NOT contain any of the given terms."""
    answer = get_answer(data).lower()
    return all(t.lower() not in answer for t in terms)


def has_number(data):
    answer = get_answer(data)
    return bool(re.search(r'\d', answer))


# ── Test Definitions ─────────────────────────────────────────────────────

TESTS = [
    # ─── Category A: Known Bugs (15 tests) ───────────────────────────────
    {
        "id": 1, "category": "A: Known Bugs", "name": "A1: 'why did rev incr' (CFO)",
        "query": "why did rev incr", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "no_typeerror": lambda d: "TypeError" not in json.dumps(d),
            "has_answer": lambda d: get_answer(d) not in ("", "None", "null"),
            "no_raw_dict": lambda d: "{'concept'" not in get_answer(d),
        }
    },
    {
        "id": 2, "category": "A: Known Bugs", "name": "A2: 'why did revenue increase' (CFO)",
        "query": "why did revenue increase", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "no_typeerror": lambda d: "TypeError" not in json.dumps(d),
            "has_answer": lambda d: len(get_answer(d)) > 10,
        }
    },
    {
        "id": 3, "category": "A: Known Bugs", "name": "A3: 'whats the margin' (CFO)",
        "query": "whats the margin", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_percent": lambda d: "%" in get_answer(d),
            "no_clarification": lambda d: "which margin" not in get_answer(d).lower(),
        }
    },
    {
        "id": 4, "category": "A: Known Bugs", "name": "A4: 'are we profitable' (CFO)",
        "query": "are we profitable", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "no_ar": lambda d: "accounts receivable" not in get_answer(d).lower(),
            "references_profit": lambda d: answer_contains_any(d, ["profit", "income", "margin", "yes", "no", "ebitda", "revenue"]),
        }
    },
    {
        "id": 5, "category": "A: Known Bugs", "name": "A5: 'build me a dashboard' (CRO)",
        "query": "build me a dashboard", "persona": "CRO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
            "has_cro_metrics": lambda d: answer_contains_any(d, ["pipeline", "win_rate", "conversion", "quota", "bookings", "sales_cycle", "win rate", "sales"]),
        }
    },
    {
        "id": 6, "category": "A: Known Bugs", "name": "A6: 'build me a dashboard' (CFO)",
        "query": "build me a dashboard", "persona": "CFO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
            "has_cfo_metrics": lambda d: answer_contains_any(d, ["revenue", "margin", "ebitda", "net_income", "cash", "arr"]),
        }
    },
    {
        "id": 7, "category": "A: Known Bugs", "name": "A7: 'build me a dashboard' (COO)",
        "query": "build me a dashboard", "persona": "COO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
            "has_coo_metrics": lambda d: answer_contains_any(d, ["utilization", "headcount", "efficiency", "capacity", "throughput", "operational"]),
        }
    },
    {
        "id": 8, "category": "A: Known Bugs", "name": "A8: 'how are we doing' (CRO)",
        "query": "how are we doing", "persona": "CRO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
            "has_cro_metrics": lambda d: answer_contains_any(d, ["pipeline", "bookings", "win_rate", "quota", "sales", "conversion", "win rate"]),
        }
    },
    {
        "id": 9, "category": "A: Known Bugs", "name": "A9: 'how are we doing' (CFO)",
        "query": "how are we doing", "persona": "CFO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
        }
    },
    {
        "id": 10, "category": "A: Known Bugs", "name": "A10: 'how are we doing' (COO)",
        "query": "how are we doing", "persona": "COO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
            "has_coo_metrics": lambda d: answer_contains_any(d, ["utilization", "headcount", "efficiency", "capacity", "throughput", "operational"]),
        }
    },
    {
        "id": 11, "category": "A: Known Bugs", "name": "A11: 'how's the business' (CRO)",
        "query": "how's the business", "persona": "CRO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
        }
    },
    {
        "id": 12, "category": "A: Known Bugs", "name": "A12: '2025 KPIs in dash' (CFO)",
        "query": "2025 KPIs in dash", "persona": "CFO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
        }
    },
    {
        "id": 13, "category": "A: Known Bugs", "name": "A13: 'platform stable?' (CTO)",
        "query": "platform stable?", "persona": "CTO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_platform": lambda d: answer_contains_any(d, ["uptime", "incident", "stability", "platform", "reliable", "available", "sla"]),
            "not_ar": lambda d: "accounts receivable" not in get_answer(d).lower(),
        }
    },
    {
        "id": 14, "category": "A: Known Bugs", "name": "A14: 'what's our headcount' (COO)",
        "query": "what's our headcount", "persona": "COO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_number": lambda d: has_number(d),
        }
    },
    {
        "id": 15, "category": "A: Known Bugs", "name": "A15: 'show me attrition trends' (CHRO)",
        "query": "show me attrition trends", "persona": "CHRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_attrition": lambda d: answer_contains_any(d, ["attrition", "turnover", "retention"]),
        }
    },

    # ─── Category B: Hard Queries - Routing Stress Tests (20 tests) ──────
    {
        "id": 16, "category": "B: Hard Queries", "name": "B1: churn rate by segment (CRO)",
        "query": "What's our churn rate by segment?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_churn": lambda d: answer_contains_any(d, ["churn"]),
            "references_segment": lambda d: answer_contains_any(d, ["segment", "enterprise", "mid-market", "smb", "small"]),
        }
    },
    {
        "id": 17, "category": "B: Hard Queries", "name": "B2: P1 incidents last quarter (CTO)",
        "query": "How many P1 incidents did we have last quarter?", "persona": "CTO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_incidents": lambda d: answer_contains_any(d, ["incident", "P1", "outage", "critical"]),
            "not_ar": lambda d: answer_not_contains(d, ["accounts receivable"]),
        }
    },
    {
        "id": 18, "category": "B: Hard Queries", "name": "B3: churn vs NRR 3 years (CRO)",
        "query": "Compare churn vs NRR over the last 3 years", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_churn": lambda d: answer_contains_any(d, ["churn"]),
            "references_nrr": lambda d: answer_contains_any(d, ["nrr", "net revenue retention", "net retention"]),
            "has_temporal": lambda d: answer_contains_any(d, ["year", "quarter", "2023", "2024", "2025", "annual"]),
        }
    },
    {
        "id": 19, "category": "B: Hard Queries", "name": "B4: worst churn segment (CRO)",
        "query": "Which segment has the worst churn?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "identifies_segment": lambda d: answer_contains_any(d, ["segment", "enterprise", "mid-market", "smb", "small", "mid market"]),
        }
    },
    {
        "id": 20, "category": "B: Hard Queries", "name": "B5: full P&L 2025 (CFO)",
        "query": "Show me the full P&L for 2025", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "multiple_pl_items": lambda d: sum(1 for t in ["revenue", "cogs", "cost of", "gross profit", "gross margin", "operating", "opex", "net income", "ebitda"] if t in get_answer(d).lower() or t in json.dumps(d).lower()) >= 3,
        }
    },
    {
        "id": 21, "category": "B: Hard Queries", "name": "B6: opex drivers (CFO)",
        "query": "What's driving the increase in opex?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_opex": lambda d: answer_contains_any(d, ["opex", "operating expense", "operating cost", "expense"]),
            "no_typeerror": lambda d: "TypeError" not in json.dumps(d),
        }
    },
    {
        "id": 22, "category": "B: Hard Queries", "name": "B7: revenue by region (CRO)",
        "query": "Break down revenue by region", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_revenue": lambda d: answer_contains_any(d, ["revenue"]),
            "references_region": lambda d: answer_contains_any(d, ["region", "north america", "emea", "apac", "americas", "europe", "asia"]),
        }
    },
    {
        "id": 23, "category": "B: Hard Queries", "name": "B8: YoY revenue growth (CFO)",
        "query": "Year over year revenue growth", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_growth": lambda d: answer_contains_any(d, ["%", "growth", "increase", "grew"]),
            "references_revenue": lambda d: answer_contains_any(d, ["revenue"]),
        }
    },
    {
        "id": 24, "category": "B: Hard Queries", "name": "B9: top 5 customers by ARR (CRO)",
        "query": "Top 5 customers by ARR", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_customers": lambda d: answer_contains_any(d, ["customer", "client", "account"]),
            "references_arr": lambda d: answer_contains_any(d, ["arr", "revenue", "annual"]),
        }
    },
    {
        "id": 25, "category": "B: Hard Queries", "name": "B10: burn rate (CFO)",
        "query": "What's our burn rate?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_burn": lambda d: answer_contains_any(d, ["burn", "cash", "runway", "spend", "expense", "operating"]),
        }
    },
    {
        "id": 26, "category": "B: Hard Queries", "name": "B11: pipeline next quarter (CRO)",
        "query": "How's pipeline looking for next quarter?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_pipeline": lambda d: answer_contains_any(d, ["pipeline"]),
            "has_temporal": lambda d: answer_contains_any(d, ["quarter", "Q1", "Q2", "Q3", "Q4", "next"]),
        }
    },
    {
        "id": 27, "category": "B: Hard Queries", "name": "B12: hitting quota (CRO)",
        "query": "Are we hitting quota?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_quota": lambda d: answer_contains_any(d, ["quota", "attainment"]),
            "not_ar": lambda d: answer_not_contains(d, ["accounts receivable"]),
        }
    },
    {
        "id": 28, "category": "B: Hard Queries", "name": "B13: customer satisfaction trend (COO)",
        "query": "What's the trend in customer satisfaction?", "persona": "COO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_satisfaction": lambda d: answer_contains_any(d, ["satisfaction", "nps", "csat", "customer", "score"]),
        }
    },
    {
        "id": 29, "category": "B: Hard Queries", "name": "B14: engineering velocity (CTO)",
        "query": "Engineering velocity this quarter", "persona": "CTO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_engineering": lambda d: answer_contains_any(d, ["velocity", "engineering", "sprint", "delivery", "deploy", "throughput"]),
        }
    },
    {
        "id": 30, "category": "B: Hard Queries", "name": "B15: compare Q1 vs Q2 revenue (CFO)",
        "query": "Compare Q1 vs Q2 revenue", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_q1": lambda d: answer_contains_any(d, ["Q1", "q1", "first quarter"]),
            "references_q2": lambda d: answer_contains_any(d, ["Q2", "q2", "second quarter"]),
            "references_revenue": lambda d: answer_contains_any(d, ["revenue"]),
        }
    },
    {
        "id": 31, "category": "B: Hard Queries", "name": "B16: gross margin trend (CFO)",
        "query": "What's our gross margin trend?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_gross_margin": lambda d: answer_contains_any(d, ["gross margin"]),
            "has_trend": lambda d: answer_contains_any(d, ["trend", "change", "over", "quarter", "increase", "decrease", "up", "down", "%"]),
        }
    },
    {
        "id": 32, "category": "B: Hard Queries", "name": "B17: hiring metrics (CHRO)",
        "query": "Show me hiring metrics", "persona": "CHRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_hiring": lambda d: answer_contains_any(d, ["hiring", "recruiting", "headcount", "open_roles", "time_to_fill", "offer", "candidate", "open role"]),
        }
    },
    {
        "id": 33, "category": "B: Hard Queries", "name": "B18: revenue per employee (COO)",
        "query": "Revenue per employee", "persona": "COO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_revenue": lambda d: answer_contains_any(d, ["revenue"]),
            "references_employee": lambda d: answer_contains_any(d, ["employee", "headcount", "per", "capita", "staff", "people"]),
        }
    },
    {
        "id": 34, "category": "B: Hard Queries", "name": "B19: what did we close last month (CRO)",
        "query": "What did we close last month?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_closed": lambda d: answer_contains_any(d, ["closed", "bookings", "revenue", "deals", "won"]),
            "has_temporal": lambda d: answer_contains_any(d, ["month", "last", "period", "recent"]),
        }
    },
    {
        "id": 35, "category": "B: Hard Queries", "name": "B20: cost of revenue breakdown (CFO)",
        "query": "Cost of revenue breakdown", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_cogs": lambda d: answer_contains_any(d, ["cost of revenue", "cogs", "cost of goods", "hosting", "infrastructure", "support"]),
        }
    },

    # ─── Category C: Persona Fidelity (15 tests) ────────────────────────
    {
        "id": 36, "category": "C: Persona Fidelity", "name": "C1: 'give me an overview' (CFO)",
        "query": "give me an overview", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_financial_metrics": lambda d: sum(1 for t in ["revenue", "margin", "cash", "ebitda", "income", "arr", "expense", "profit"] if t in json.dumps(d).lower()) >= 2,
        }
    },
    {
        "id": 37, "category": "C: Persona Fidelity", "name": "C2: 'give me an overview' (CRO)",
        "query": "give me an overview", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_sales_metrics": lambda d: sum(1 for t in ["pipeline", "bookings", "win_rate", "quota", "win rate", "sales", "conversion", "churn"] if t in json.dumps(d).lower()) >= 2,
        }
    },
    {
        "id": 38, "category": "C: Persona Fidelity", "name": "C3: 'give me an overview' (COO)",
        "query": "give me an overview", "persona": "COO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_ops_metrics": lambda d: sum(1 for t in ["utilization", "headcount", "efficiency", "capacity", "throughput", "operational", "employee"] if t in json.dumps(d).lower()) >= 1,
        }
    },
    {
        "id": 39, "category": "C: Persona Fidelity", "name": "C4: 'give me an overview' (CTO)",
        "query": "give me an overview", "persona": "CTO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_tech_metrics": lambda d: sum(1 for t in ["uptime", "incident", "velocity", "deployment", "deploy", "availability", "sla", "infrastructure"] if t in json.dumps(d).lower()) >= 1,
        }
    },
    {
        "id": 40, "category": "C: Persona Fidelity", "name": "C5: 'give me an overview' (CHRO)",
        "query": "give me an overview", "persona": "CHRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_people_metrics": lambda d: sum(1 for t in ["attrition", "hiring", "headcount", "engagement", "retention", "turnover", "employee"] if t in json.dumps(d).lower()) >= 1,
        }
    },
    {
        "id": 41, "category": "C: Persona Fidelity", "name": "C6: 'what should I worry about?' (CFO)",
        "query": "what should I worry about?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_financial": lambda d: answer_contains_any(d, ["revenue", "margin", "cash", "expense", "cost", "profit", "burn", "budget", "ebitda", "financial"]),
        }
    },
    {
        "id": 42, "category": "C: Persona Fidelity", "name": "C7: 'what should I worry about?' (CRO)",
        "query": "what should I worry about?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_sales": lambda d: answer_contains_any(d, ["pipeline", "sales", "quota", "churn", "bookings", "conversion", "win", "deal", "revenue"]),
        }
    },
    {
        "id": 43, "category": "C: Persona Fidelity", "name": "C8: 'what should I worry about?' (CTO)",
        "query": "what should I worry about?", "persona": "CTO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_tech": lambda d: answer_contains_any(d, ["platform", "incident", "uptime", "deploy", "infrastructure", "tech", "engineering", "security", "availability"]),
        }
    },
    {
        "id": 44, "category": "C: Persona Fidelity", "name": "C9: 'how did we do last quarter?' (CFO)",
        "query": "how did we do last quarter?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_financial": lambda d: answer_contains_any(d, ["revenue", "margin", "income", "cash", "ebitda", "profit", "arr", "financial"]),
            "has_quarter": lambda d: answer_contains_any(d, ["quarter", "Q1", "Q2", "Q3", "Q4"]),
        }
    },
    {
        "id": 45, "category": "C: Persona Fidelity", "name": "C10: 'how did we do last quarter?' (CRO)",
        "query": "how did we do last quarter?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_sales": lambda d: answer_contains_any(d, ["pipeline", "sales", "quota", "bookings", "conversion", "win", "deal", "revenue", "churn"]),
        }
    },
    {
        "id": 46, "category": "C: Persona Fidelity", "name": "C11: 'how did we do last quarter?' (COO)",
        "query": "how did we do last quarter?", "persona": "COO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_ops": lambda d: answer_contains_any(d, ["utilization", "headcount", "efficiency", "capacity", "operational", "throughput", "employee"]),
        }
    },
    {
        "id": 47, "category": "C: Persona Fidelity", "name": "C12: 'build me a CHRO dashboard' (CHRO)",
        "query": "build me a CHRO dashboard", "persona": "CHRO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
            "has_people_metrics": lambda d: answer_contains_any(d, ["attrition", "hiring", "headcount", "engagement", "retention", "turnover", "employee"]),
        }
    },
    {
        "id": 48, "category": "C: Persona Fidelity", "name": "C13: 'build me a CTO dashboard' (CTO)",
        "query": "build me a CTO dashboard", "persona": "CTO",
        "assertions": {
            "is_dashboard": lambda d: get_response_type(d) == "dashboard",
            "has_tech_metrics": lambda d: answer_contains_any(d, ["uptime", "incident", "velocity", "deployment", "deploy", "availability", "sla", "infrastructure"]),
        }
    },
    {
        "id": 49, "category": "C: Persona Fidelity", "name": "C14: 'what are our KPIs?' (CFO)",
        "query": "what are our KPIs?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_financial_kpis": lambda d: answer_contains_any(d, ["revenue", "margin", "ebitda", "cash", "arr", "income", "profit"]),
        }
    },
    {
        "id": 50, "category": "C: Persona Fidelity", "name": "C15: 'what are our KPIs?' (CRO)",
        "query": "what are our KPIs?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_sales_kpis": lambda d: answer_contains_any(d, ["pipeline", "conversion", "quota", "bookings", "win", "sales", "churn"]),
        }
    },

    # ─── Category D: Point Queries - Single Metric Resolution (15 tests) ─
    {
        "id": 51, "category": "D: Point Queries", "name": "D1: 'what's our revenue?' (CFO)",
        "query": "what's our revenue?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_value": lambda d: "$" in get_answer(d) or has_number(d),
        }
    },
    {
        "id": 52, "category": "D: Point Queries", "name": "D2: 'what's our ARR?' (CFO)",
        "query": "what's our ARR?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_value": lambda d: "$" in get_answer(d) or has_number(d),
        }
    },
    {
        "id": 53, "category": "D: Point Queries", "name": "D3: 'gross margin' (CFO)",
        "query": "gross margin", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_percent": lambda d: "%" in get_answer(d),
        }
    },
    {
        "id": 54, "category": "D: Point Queries", "name": "D4: 'operating margin' (CFO)",
        "query": "operating margin", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_percent": lambda d: "%" in get_answer(d),
        }
    },
    {
        "id": 55, "category": "D: Point Queries", "name": "D5: 'net margin' (CFO)",
        "query": "net margin", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_percent": lambda d: "%" in get_answer(d),
        }
    },
    {
        "id": 56, "category": "D: Point Queries", "name": "D6: 'what's EBITDA?' (CFO)",
        "query": "what's EBITDA?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_value": lambda d: "$" in get_answer(d) or has_number(d),
        }
    },
    {
        "id": 57, "category": "D: Point Queries", "name": "D7: 'cash position' (CFO)",
        "query": "cash position", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_value": lambda d: "$" in get_answer(d) or has_number(d),
        }
    },
    {
        "id": 58, "category": "D: Point Queries", "name": "D8: 'what's NRR?' (CRO)",
        "query": "what's NRR?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_value": lambda d: "%" in get_answer(d) or has_number(d),
        }
    },
    {
        "id": 59, "category": "D: Point Queries", "name": "D9: 'pipeline value' (CRO)",
        "query": "pipeline value", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_value": lambda d: "$" in get_answer(d) or has_number(d),
        }
    },
    {
        "id": 60, "category": "D: Point Queries", "name": "D10: 'win rate' (CRO)",
        "query": "win rate", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_percent": lambda d: "%" in get_answer(d),
        }
    },
    {
        "id": 61, "category": "D: Point Queries", "name": "D11: 'quota attainment' (CRO)",
        "query": "quota attainment", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_percent": lambda d: "%" in get_answer(d),
        }
    },
    {
        "id": 62, "category": "D: Point Queries", "name": "D12: 'sales cycle days' (CRO)",
        "query": "sales cycle days", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_number": lambda d: has_number(d),
            "references_days": lambda d: answer_contains_any(d, ["day", "days"]),
        }
    },
    {
        "id": 63, "category": "D: Point Queries", "name": "D13: 'what's our churn rate?' (CRO)",
        "query": "what's our churn rate?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_percent": lambda d: "%" in get_answer(d),
        }
    },
    {
        "id": 64, "category": "D: Point Queries", "name": "D14: 'customer count' (CRO)",
        "query": "customer count", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_number": lambda d: has_number(d),
        }
    },
    {
        "id": 65, "category": "D: Point Queries", "name": "D15: 'what's net income?' (CFO)",
        "query": "what's net income?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "has_value": lambda d: "$" in get_answer(d) or has_number(d),
        }
    },

    # ─── Category E: Comparison and Temporal Queries (10 tests) ──────────
    {
        "id": 66, "category": "E: Comparison/Temporal", "name": "E1: compare Q1 vs Q2 2025 revenue (CFO)",
        "query": "compare Q1 vs Q2 2025 revenue", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_q1": lambda d: answer_contains_any(d, ["Q1", "q1"]),
            "references_q2": lambda d: answer_contains_any(d, ["Q2", "q2"]),
        }
    },
    {
        "id": 67, "category": "E: Comparison/Temporal", "name": "E2: revenue trend last 4 quarters (CFO)",
        "query": "revenue trend last 4 quarters", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_quarters": lambda d: answer_contains_any(d, ["quarter", "Q1", "Q2", "Q3", "Q4"]),
        }
    },
    {
        "id": 68, "category": "E: Comparison/Temporal", "name": "E3: pipeline change this year (CRO)",
        "query": "how has pipeline changed this year?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_pipeline": lambda d: answer_contains_any(d, ["pipeline"]),
            "references_change": lambda d: answer_contains_any(d, ["change", "trend", "increase", "decrease", "grew", "growth", "up", "down"]),
        }
    },
    {
        "id": 69, "category": "E: Comparison/Temporal", "name": "E4: margin this quarter vs last (CFO)",
        "query": "margin this quarter vs last", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_comparison": lambda d: answer_contains_any(d, ["quarter", "vs", "compare", "Q1", "Q2", "Q3", "Q4", "change", "previous", "last"]),
        }
    },
    {
        "id": 70, "category": "E: Comparison/Temporal", "name": "E5: YoY growth in ARR (CFO)",
        "query": "YoY growth in ARR", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_yoy": lambda d: answer_contains_any(d, ["year-over-year", "yoy", "year over year", "annual", "growth"]),
            "references_arr": lambda d: answer_contains_any(d, ["arr", "annual recurring"]),
        }
    },
    {
        "id": 71, "category": "E: Comparison/Temporal", "name": "E6: churn rate last 3 quarters (CRO)",
        "query": "churn rate last 3 quarters", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_churn": lambda d: answer_contains_any(d, ["churn"]),
            "references_quarters": lambda d: answer_contains_any(d, ["quarter", "Q1", "Q2", "Q3", "Q4"]),
        }
    },
    {
        "id": 72, "category": "E: Comparison/Temporal", "name": "E7: is revenue going up or down (CFO)",
        "query": "is revenue going up or down?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "indicates_direction": lambda d: answer_contains_any(d, ["up", "down", "increase", "decrease", "growing", "declining", "grew", "risen", "fallen"]),
        }
    },
    {
        "id": 73, "category": "E: Comparison/Temporal", "name": "E8: pipeline trend since January (CRO)",
        "query": "pipeline trend since January", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_pipeline": lambda d: answer_contains_any(d, ["pipeline"]),
            "has_temporal": lambda d: answer_contains_any(d, ["january", "jan", "trend", "since", "quarter", "month"]),
        }
    },
    {
        "id": 74, "category": "E: Comparison/Temporal", "name": "E9: compare gross vs net margin (CFO)",
        "query": "compare gross vs net margin", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_gross": lambda d: answer_contains_any(d, ["gross"]),
            "references_net": lambda d: answer_contains_any(d, ["net"]),
        }
    },
    {
        "id": 75, "category": "E: Comparison/Temporal", "name": "E10: bookings this year vs last (CRO)",
        "query": "bookings this year vs last year", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_bookings": lambda d: answer_contains_any(d, ["bookings", "booking"]),
            "references_years": lambda d: answer_contains_any(d, ["year", "2024", "2025", "2026", "annual"]),
        }
    },

    # ─── Category F: Ambiguity and Edge Cases (10 tests) ─────────────────
    {
        "id": 76, "category": "F: Edge Cases", "name": "F1: 'hi' (no persona)",
        "query": "hi", "persona": None,
        "assertions": {
            "success": lambda d: has_success(d),
            "not_metric": lambda d: not (has_number(d) and "$" in get_answer(d)),
        }
    },
    {
        "id": 77, "category": "F: Edge Cases", "name": "F2: 'what's the weather?' (no persona)",
        "query": "what's the weather?", "persona": None,
        "assertions": {
            "success": lambda d: has_success(d),
            "off_topic_handled": lambda d: answer_contains_any(d, ["can't", "cannot", "don't", "unable", "outside", "not", "help", "business", "sorry", "weather"]),
        }
    },
    {
        "id": 78, "category": "F: Edge Cases", "name": "F3: 'asdfghjkl' (no persona)",
        "query": "asdfghjkl", "persona": None,
        "assertions": {
            "success": lambda d: has_success(d),
            "handled_gracefully": lambda d: answer_contains_any(d, ["understand", "rephrase", "help", "sorry", "clarif", "don't", "cannot", "can't", "not sure", "try"]),
        }
    },
    {
        "id": 79, "category": "F: Edge Cases", "name": "F4: 'tell me everything' (CFO)",
        "query": "tell me everything", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            # Main check: did not timeout (if we got here, no timeout)
            "responded": lambda d: len(get_answer(d)) > 0,
        }
    },
    {
        "id": 80, "category": "F: Edge Cases", "name": "F5: 'rev' (CFO)",
        "query": "rev", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_revenue": lambda d: answer_contains_any(d, ["revenue", "rev"]),
        }
    },
    {
        "id": 81, "category": "F: Edge Cases", "name": "F6: '$' (no persona)",
        "query": "$", "persona": None,
        "assertions": {
            "no_crash": lambda d: True,  # If we got a response at all, it didn't crash
        }
    },
    {
        "id": 82, "category": "F: Edge Cases", "name": "F7: empty string (no persona)",
        "query": "", "persona": None,
        "assertions": {
            "no_crash": lambda d: True,  # 400 or graceful error is acceptable
        }
    },
    {
        "id": 83, "category": "F: Edge Cases", "name": "F8: 'show me the data' (CFO)",
        "query": "show me the data", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "responded": lambda d: len(get_answer(d)) > 0,
        }
    },
    {
        "id": 84, "category": "F: Edge Cases", "name": "F9: 'more detail' (CFO)",
        "query": "more detail", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "no_crash": lambda d: True,
        }
    },
    {
        "id": 85, "category": "F: Edge Cases", "name": "F10: 'thanks' (no persona)",
        "query": "thanks", "persona": None,
        "assertions": {
            "no_crash": lambda d: True,
        }
    },

    # ─── Category G: Composite and Multi-Step Queries (10 tests) ─────────
    {
        "id": 86, "category": "G: Composite Queries", "name": "G1: full P&L 2025 (CFO)",
        "query": "full P&L for 2025", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "multiple_pl_items": lambda d: sum(1 for t in ["revenue", "cogs", "cost of", "gross profit", "gross margin", "operating", "opex", "net income", "ebitda"] if t in get_answer(d).lower() or t in json.dumps(d).lower()) >= 3,
        }
    },
    {
        "id": 87, "category": "G: Composite Queries", "name": "G2: executive summary (CFO)",
        "query": "executive summary", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "multiple_metrics": lambda d: sum(1 for t in ["revenue", "margin", "cash", "ebitda", "arr", "income", "profit", "growth"] if t in json.dumps(d).lower()) >= 2,
        }
    },
    {
        "id": 88, "category": "G: Composite Queries", "name": "G3: financial health (CFO)",
        "query": "what's our financial health?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "multiple_indicators": lambda d: sum(1 for t in ["revenue", "margin", "cash", "burn", "profit", "income", "growth", "ebitda", "arr"] if t in json.dumps(d).lower()) >= 2,
        }
    },
    {
        "id": 89, "category": "G: Composite Queries", "name": "G4: sales performance scorecard (CRO)",
        "query": "sales performance scorecard", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "multiple_sales_metrics": lambda d: sum(1 for t in ["pipeline", "bookings", "win_rate", "quota", "win rate", "conversion", "churn", "sales", "arr"] if t in json.dumps(d).lower()) >= 2,
        }
    },
    {
        "id": 90, "category": "G: Composite Queries", "name": "G5: operational efficiency report (COO)",
        "query": "operational efficiency report", "persona": "COO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_efficiency": lambda d: answer_contains_any(d, ["efficiency", "operational", "utilization", "headcount", "capacity", "throughput", "revenue per"]),
        }
    },
    {
        "id": 91, "category": "G: Composite Queries", "name": "G6: show me all the margins (CFO)",
        "query": "show me all the margins", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_gross": lambda d: answer_contains_any(d, ["gross"]),
            "references_operating": lambda d: answer_contains_any(d, ["operating"]),
            "references_net": lambda d: answer_contains_any(d, ["net"]),
        }
    },
    {
        "id": 92, "category": "G: Composite Queries", "name": "G7: revenue and EBITDA trend (CFO)",
        "query": "revenue and EBITDA trend", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_revenue": lambda d: answer_contains_any(d, ["revenue"]),
            "references_ebitda": lambda d: answer_contains_any(d, ["ebitda"]),
        }
    },
    {
        "id": 93, "category": "G: Composite Queries", "name": "G8: customer health overview (CRO)",
        "query": "customer health overview", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_customer_health": lambda d: answer_contains_any(d, ["churn", "nrr", "satisfaction", "retention", "customer", "nps"]),
        }
    },
    {
        "id": 94, "category": "G: Composite Queries", "name": "G9: unit economics (CFO)",
        "query": "what's our unit economics?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "references_unit": lambda d: answer_contains_any(d, ["unit", "per", "customer", "cac", "ltv", "cost", "revenue per"]),
        }
    },
    {
        "id": 95, "category": "G: Composite Queries", "name": "G10: board deck metrics (CFO)",
        "query": "board deck metrics", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "multiple_key_metrics": lambda d: sum(1 for t in ["revenue", "growth", "margin", "arr", "ebitda", "cash", "churn", "nrr"] if t in json.dumps(d).lower()) >= 2,
        }
    },

    # ─── Category H: Superlatives and Rankings (5 tests) ─────────────────
    {
        "id": 96, "category": "H: Superlatives", "name": "H1: worst churn segment (CRO)",
        "query": "which segment has the worst churn?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "identifies_segment": lambda d: answer_contains_any(d, ["segment", "enterprise", "mid-market", "smb", "small", "mid market"]),
        }
    },
    {
        "id": 97, "category": "H: Superlatives", "name": "H2: best performing region (CRO)",
        "query": "best performing region", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "identifies_region": lambda d: answer_contains_any(d, ["region", "north america", "emea", "apac", "americas", "europe", "asia"]),
        }
    },
    {
        "id": 98, "category": "H: Superlatives", "name": "H3: biggest expense (CFO)",
        "query": "what's our biggest expense?", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "identifies_expense": lambda d: answer_contains_any(d, ["expense", "cost", "salary", "personnel", "r&d", "sales", "marketing", "hosting", "opex", "payroll"]),
        }
    },
    {
        "id": 99, "category": "H: Superlatives", "name": "H4: largest customer (CRO)",
        "query": "who's our largest customer?", "persona": "CRO",
        "assertions": {
            "success": lambda d: has_success(d),
            "addresses_question": lambda d: answer_contains_any(d, ["customer", "client", "account", "data", "unavailable", "don't have", "not available"]),
        }
    },
    {
        "id": 100, "category": "H: Superlatives", "name": "H5: lowest margin product (CFO)",
        "query": "lowest margin product", "persona": "CFO",
        "assertions": {
            "success": lambda d: has_success(d),
            "addresses_question": lambda d: answer_contains_any(d, ["margin", "product", "segment", "lowest", "data", "unavailable"]),
        }
    },
]


def get_endpoint():
    """Find a live endpoint. Try production first."""
    for url in [PROD_URL, LOCAL_URL]:
        try:
            health = url.replace("/api/v1/query", "/api/v1/health")
            r = requests.get(health, timeout=5)
            if r.status_code == 200:
                print(f"Using endpoint: {url}")
                return url
        except Exception:
            continue
    print("FATAL: No endpoint available")
    sys.exit(1)


def run_test(endpoint, test):
    """Execute one test. Returns result dict."""
    body = {"question": test["query"]}
    if test.get("persona"):
        body["persona"] = test["persona"]

    result = {
        "id": test["id"],
        "name": test["name"],
        "category": test["category"],
        "query": test["query"],
        "persona": test.get("persona"),
        "request_body": body,
        "response_body": None,
        "http_status": None,
        "response_time_ms": None,
        "assertions": {},
        "passed": False,
        "error": None,
    }

    try:
        start = time.time()
        r = requests.post(endpoint, json=body, timeout=TIMEOUT)
        elapsed = (time.time() - start) * 1000
        result["http_status"] = r.status_code
        result["response_time_ms"] = round(elapsed)

        if r.status_code >= 500:
            result["error"] = f"HTTP {r.status_code}"
            result["response_body"] = r.text[:2000]
            result["assertions"]["no_500"] = False
            return result

        # For edge cases like empty string, a 400 is acceptable
        if r.status_code == 400 and test["id"] in (82,):
            result["response_body"] = r.text[:2000]
            result["assertions"]["no_crash"] = True
            result["passed"] = True
            return result

        try:
            data = r.json()
        except Exception:
            result["error"] = "Invalid JSON response"
            result["response_body"] = r.text[:2000]
            return result

        result["response_body"] = data

        # Run all assertions
        all_pass = True
        for assert_name, assert_fn in test["assertions"].items():
            try:
                passed = assert_fn(data)
                result["assertions"][assert_name] = passed
                if not passed:
                    all_pass = False
            except Exception as e:
                result["assertions"][assert_name] = False
                result["error"] = f"Assertion '{assert_name}' threw: {str(e)}"
                all_pass = False

        result["passed"] = all_pass

    except requests.Timeout:
        result["error"] = "TIMEOUT (>30s) - possible infinite loop"
        result["assertions"]["no_timeout"] = False
    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    endpoint = get_endpoint()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Ensure tests dir exists
    os.makedirs("tests", exist_ok=True)

    results = []
    for i, test in enumerate(TESTS):
        print(f"[{i+1:3d}/100] {test['name']}...", end=" ", flush=True)
        result = run_test(endpoint, test)
        status = "PASS" if result["passed"] else "FAIL"
        ms = result.get("response_time_ms", "?")
        print(f"{status} ({ms}ms)")
        results.append(result)
        if i < len(TESTS) - 1:
            time.sleep(DELAY)

    # Write detailed results
    results_file = f"tests/e2e_results_{timestamp}.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)

    # Write summary
    summary_file = f"tests/e2e_summary_{timestamp}.txt"
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])

    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"NLQ E2E Test Results - {timestamp}\n")
        f.write(f"Endpoint: {endpoint}\n")
        f.write(f"{'='*60}\n")
        f.write(f"TOTAL: {len(results)} | PASSED: {passed} | FAILED: {failed}\n")
        f.write(f"Pass rate: {passed/len(results)*100:.1f}%\n")
        f.write(f"{'='*60}\n\n")

        # By category
        categories = {}
        for r in results:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = {"pass": 0, "fail": 0, "tests": []}
            if r["passed"]:
                categories[cat]["pass"] += 1
            else:
                categories[cat]["fail"] += 1
            categories[cat]["tests"].append(r)

        for cat in sorted(categories):
            info = categories[cat]
            total = info["pass"] + info["fail"]
            f.write(f"\n--- {cat} ({info['pass']}/{total} passed) ---\n")
            for r in info["tests"]:
                status = "PASS" if r["passed"] else "FAIL"
                f.write(f"  [{status}] {r['name']}")
                if not r["passed"]:
                    failed_assertions = [k for k, v in r["assertions"].items() if not v]
                    f.write(f" -- Failed: {', '.join(failed_assertions)}")
                    if r.get("error"):
                        f.write(f" -- Error: {r['error']}")
                    # Show the actual answer for failed tests
                    if r.get("response_body") and isinstance(r["response_body"], dict):
                        answer = str(r["response_body"].get("answer", ""))[:200]
                        f.write(f"\n         Actual answer: {answer}")
                f.write("\n")

        # Timing stats
        f.write(f"\n{'='*60}\n")
        f.write("TIMING STATS\n")
        times = [r["response_time_ms"] for r in results if r.get("response_time_ms")]
        if times:
            f.write(f"  Min: {min(times)}ms\n")
            f.write(f"  Max: {max(times)}ms\n")
            f.write(f"  Avg: {sum(times)/len(times):.0f}ms\n")
            f.write(f"  Median: {sorted(times)[len(times)//2]}ms\n")
            over_10s = sum(1 for t in times if t > 10000)
            f.write(f"  Over 10s: {over_10s}\n")

    # Also write a latest symlink / copy for easy access
    latest_results = "tests/e2e_results.json"
    latest_summary = "tests/e2e_summary.txt"
    with open(latest_results, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)
    with open(latest_summary, "w", encoding="utf-8") as fw:
        with open(summary_file, "r", encoding="utf-8") as fr:
            fw.write(fr.read())

    print(f"\nResults: {results_file}")
    print(f"Summary: {summary_file}")
    print(f"Latest:  {latest_results} / {latest_summary}")
    print(f"\n{'='*40}")
    print(f"PASSED: {passed}/100 | FAILED: {failed}/100")
    print(f"Pass rate: {passed/len(results)*100:.1f}%")


if __name__ == "__main__":
    main()
