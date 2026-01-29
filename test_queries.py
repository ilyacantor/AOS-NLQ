#!/usr/bin/env python3
"""
Test script to validate NLQ queries against the fact base.
This bypasses the LLM parsing and tests the execution layer directly.
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.nlq.knowledge.fact_base import FactBase
from src.nlq.core.executor import QueryExecutor
from src.nlq.models.query import ParsedQuery, QueryIntent, PeriodType

# Load the fact base
fact_base = FactBase()
fact_base.load(Path(__file__).parent / "data" / "fact_base.json")

# Test direct queries
print("=" * 80)
print("TESTING FACT BASE DIRECT QUERIES")
print("=" * 80)

# Test 2025 revenue
revenue_2025 = fact_base.query("revenue", "2025")
print(f"Revenue 2025: {revenue_2025} (expected: 150.0)")

# Test 2024 bookings
bookings_2024 = fact_base.query("bookings", "2024")
print(f"Bookings 2024: {bookings_2024} (expected: 115.0)")

# Test 2025 ARR
arr_2025 = fact_base.query("arr", "2025")
print(f"ARR 2025: {arr_2025} (expected: 142.5)")

# Test Q4 2025 bookings
bookings_q4_2025 = fact_base.query("bookings", "2025-Q4")
print(f"Bookings Q4 2025: {bookings_q4_2025} (expected: 55.725)")

# Test win rate 2024
win_rate_2024 = fact_base.query("win_rate", "2024")
print(f"Win Rate 2024: {win_rate_2024} (expected: 40)")

# Test customer count 2025
customer_count_2025 = fact_base.query("customer_count", "2025")
print(f"Customer Count 2025: {customer_count_2025} (expected: 950)")

# Test headcount 2025
headcount_2025 = fact_base.query("headcount", "2025")
print(f"Headcount 2025: {headcount_2025} (expected: 350)")

# Test engineering headcount 2025
eng_headcount_2025 = fact_base.query("engineering_headcount", "2025")
print(f"Engineering Headcount 2025: {eng_headcount_2025} (expected: 115)")

# Test uptime 2025
uptime_2025 = fact_base.query("uptime_pct", "2025")
print(f"Uptime 2025: {uptime_2025} (expected: 99.8)")

# Test features shipped 2025
features_2025 = fact_base.query("features_shipped", "2025")
print(f"Features Shipped 2025: {features_2025} (expected: 72)")

print("\n" + "=" * 80)
print("TESTING QUERY EXECUTOR")
print("=" * 80)

executor = QueryExecutor(fact_base)

# Test point query for revenue 2025
parsed = ParsedQuery(
    intent=QueryIntent.POINT_QUERY,
    metric="revenue",
    period_type=PeriodType.ANNUAL,
    period_reference="2025",
    resolved_period="2025"
)
result = executor.execute(parsed)
print(f"Revenue 2025 via executor: {result.value} (expected: 150.0)")

# Test point query for bookings Q4 2025
parsed = ParsedQuery(
    intent=QueryIntent.POINT_QUERY,
    metric="bookings",
    period_type=PeriodType.QUARTERLY,
    period_reference="Q4 2025",
    resolved_period="2025-Q4"
)
result = executor.execute(parsed)
print(f"Bookings Q4 2025 via executor: {result.value} (expected: 55.725)")

# Test comparison query
parsed = ParsedQuery(
    intent=QueryIntent.COMPARISON_QUERY,
    metric="revenue",
    period_type=PeriodType.ANNUAL,
    period_reference="2025",
    resolved_period="2025",
    comparison_period="2024"
)
result = executor.execute(parsed)
print(f"Revenue 2025 vs 2024: {result.value} (expected: ~50% growth)")

print("\n" + "=" * 80)
print("AVAILABLE METRICS IN FACT BASE")
print("=" * 80)
print(sorted(fact_base.available_metrics)[:30])

print("\n" + "=" * 80)
print("AVAILABLE PERIODS IN FACT BASE")
print("=" * 80)
print(sorted(fact_base.available_periods))

print("\n" + "=" * 80)
print("CFO QUESTIONS - GROUND TRUTH VALIDATION")
print("=" * 80)

# From test suite - CFO questions
cfo_tests = [
    # Annual queries
    ("revenue", "2024", 100.0),
    ("revenue", "2025", 150.0),
    ("net_income", "2025", None),  # Need to check what's in fact base
    ("gross_margin_pct", "2025", 65.0),
    ("operating_margin_pct", "2025", 35.0),
    ("cogs", "2025", 52.5),
    ("sga", "2025", 45.0),
    ("cash", "2025", 41.42),  # Q4 2025 balance
    ("ar", "2025", 20.71),
    # Quarterly
    ("revenue", "2025-Q4", 42.0),
    ("gross_profit", "2025-Q4", 27.3),
]

for metric, period, expected in cfo_tests:
    actual = fact_base.query(metric, period)
    status = "✓" if actual == expected else "✗"
    print(f"{status} {metric} {period}: {actual} (expected: {expected})")

print("\n" + "=" * 80)
print("CRO QUESTIONS - GROUND TRUTH VALIDATION")
print("=" * 80)

cro_tests = [
    ("bookings", "2024", 115.0),
    ("arr", "2025", 142.5),
    ("new_logo_revenue", "2024", 25.0),
    ("expansion_revenue", "2025", 25.0),
    ("win_rate", "2024", 40),
    ("pipeline", "2025", 431.25),
    ("customer_count", "2024", 800),
    ("nrr", "2025", 118),
    ("gross_churn_pct", "2024", 8),
    ("avg_deal_size", "2025", 0.15),
    # Quarterly
    ("bookings", "2025-Q4", 55.725),
    ("win_rate", "2025-Q3", 43),
    ("new_logos", "2025-Q4", 55),
    ("pipeline", "2025-Q2", 97.875),
    ("bookings", "2025-Q1", 34.5),
]

for metric, period, expected in cro_tests:
    actual = fact_base.query(metric, period)
    status = "✓" if actual == expected else "✗"
    print(f"{status} {metric} {period}: {actual} (expected: {expected})")

print("\n" + "=" * 80)
print("COO QUESTIONS - GROUND TRUTH VALIDATION")
print("=" * 80)

coo_tests = [
    ("headcount", "2024", 250),
    ("headcount", "2025", 350),
    ("engineering_headcount", "2025", 115),
    ("sales_headcount", "2024", 45),
    ("ga_headcount", "2025", 60),
    ("cs_headcount", "2025", 50),
    ("marketing_headcount", "2025", 35),
    ("product_headcount", "2025", 30),
    ("revenue_per_employee", "2024", 0.4),
    ("revenue_per_employee", "2025", 0.429),
    ("cost_per_employee", "2025", 0.175),
    ("magic_number", "2025", 0.85),
    ("cac_payback_months", "2024", 18),
    ("ltv_cac", "2025", 3.5),
    ("burn_multiple", "2025", 0.9),
    ("implementation_days", "2024", 45),
    ("time_to_value_days", "2025", 50),
    ("support_tickets", "2025", 15000),
    ("first_response_hours", "2025", 3.2),
    ("resolution_hours", "2024", 24),
    ("csat", "2025", 4.4),
    ("nps", "2025", 48),
    ("ps_utilization", "2025", 76),
    ("engineering_utilization", "2025", 80),
    ("support_utilization", "2024", 85),
    # Quarterly
    ("headcount", "2025-Q4", 350),
    ("hires", "2025-Q2", 30),
    ("attrition", "2025-Q3", 8),
    ("attrition_rate", "2025-Q1", 2.8),
]

for metric, period, expected in coo_tests:
    actual = fact_base.query(metric, period)
    status = "✓" if actual == expected else "✗"
    print(f"{status} {metric} {period}: {actual} (expected: {expected})")

print("\n" + "=" * 80)
print("CTO QUESTIONS - GROUND TRUTH VALIDATION")
print("=" * 80)

cto_tests = [
    ("engineering_headcount", "2024", 80),
    ("engineering_headcount", "2025", 115),
    ("features_shipped", "2025", 72),
    ("sprint_velocity", "2025", 60),
    ("story_points", "2024", 2400),
    ("product_headcount", "2025", 30),
    ("features_shipped", "2024", 48),
    ("uptime_pct", "2024", 99.5),
    ("uptime_pct", "2025", 99.8),
    ("p1_incidents", "2025", 6),
    ("p2_incidents", "2024", 36),
    ("mttr_p1_hours", "2025", 1.8),
    ("mttr_p2_hours", "2025", 6.0),
    ("downtime_hours", "2024", 43.8),
    ("tech_debt_pct", "2024", 35),
    ("tech_debt_pct", "2025", 28),
    ("code_coverage_pct", "2025", 75),
    ("bug_escape_rate", "2025", 5),
    ("critical_bugs", "2025", 8),
    ("security_vulns", "2024", 6),
    ("deploys_per_week", "2025", 15),
    ("deployment_success_pct", "2025", 97),
    ("lead_time_days", "2024", 14),
    ("lead_time_days", "2025", 7),
    ("change_failure_rate", "2025", 8),
    ("cloud_spend", "2024", 2.4),
    ("cloud_spend", "2025", 3.2),
    ("cloud_spend_pct_revenue", "2025", 2.1),
    ("cost_per_transaction", "2025", 0.009),
    ("api_requests_millions", "2025", 280),
    # Quarterly
    ("features_shipped", "2025-Q4", 21),
    ("story_points", "2025-Q2", 875),
    ("p1_incidents", "2025-Q3", 1),
]

for metric, period, expected in cto_tests:
    actual = fact_base.query(metric, period)
    status = "✓" if actual == expected else "✗"
    print(f"{status} {metric} {period}: {actual} (expected: {expected})")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
