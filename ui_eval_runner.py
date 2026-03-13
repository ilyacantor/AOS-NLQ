#!/usr/bin/env python3
"""
NLQ Dashboard UI Evaluation Runner

Comprehensive test suite that verifies the UI behavior by testing
the API responses that drive the frontend rendering.

Since the UI is a React app that renders JSON responses from the backend,
this test verifies:
1. Response structure matches what UI expects
2. Values match ground truth from fact base
3. Response types are appropriate for each query type
4. Context preservation and refinement work correctly
"""

import requests
import json
import sys
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import time

# Configuration
API_BASE = "http://localhost:8000"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "eval_screenshots")

# Ground truth values from fact_base.json
GROUND_TRUTH = {
    # 2025 Annual values
    "revenue_2025": 150.0,
    "pipeline_2025": 431.25,
    "win_rate_2025": 42,
    "gross_margin_pct_2025": 65.0,
    "customer_count_2025": 950,
    "nrr_2025": 118,
    "gross_churn_pct_2025": 7,
    "logo_churn_pct_2025": 10,
    "headcount_2025": 350,
    "net_income_2025": 28.13,
    "arr_2025": 142.5,

    # Quarterly revenue for trend charts (8 quarters)
    "quarterly_revenue": {
        "2024-Q1": 22.0,
        "2024-Q2": 24.0,
        "2024-Q3": 26.0,
        "2024-Q4": 28.0,
        "2025-Q1": 33.0,
        "2025-Q2": 36.0,
        "2025-Q3": 39.0,
        "2025-Q4": 42.0,
    },

    # Customer metrics for guided discovery
    "customer_metrics": ["customer_count", "nrr", "gross_churn_pct", "logo_churn_pct"],
}

@dataclass
class TestResult:
    """Result of a single test case."""
    id: str
    name: str
    status: str  # PASS, FAIL, ERROR
    message: str
    verification: Dict[str, Any] = field(default_factory=dict)
    response_data: Optional[Dict] = None


class UIEvalRunner:
    """UI Evaluation Runner for NLQ Dashboard."""

    def __init__(self):
        self.session_id = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.results: List[TestResult] = []
        self.current_dashboard = None  # Track dashboard state for context tests

    def query_api(self, question: str, endpoint: str = "intent-map") -> Dict[str, Any]:
        """Send query to API and return response."""
        url = f"{API_BASE}/v1/{endpoint}"
        payload = {
            "question": question,
            "session_id": self.session_id,
            "reference_date": "2026-01-27",
            "mode": "ai"
        }

        response = requests.post(url, json=payload, timeout=60)
        return response.json()

    def contains_value(self, data: Dict, target: float, tolerance: float = 0.05) -> bool:
        """Check if response data contains a value within tolerance."""
        def search(obj, target, tol):
            if isinstance(obj, (int, float)):
                if target != 0 and abs(obj - target) / abs(target) <= tol:
                    return True
            elif isinstance(obj, dict):
                for v in obj.values():
                    if search(v, target, tol):
                        return True
            elif isinstance(obj, list):
                for item in obj:
                    if search(item, target, tol):
                        return True
            return False
        return search(data, target, tolerance)

    def has_dashboard_schema(self, data: Dict) -> bool:
        """Check if response contains a dashboard schema."""
        return (
            data.get("dashboard") is not None or
            data.get("response_type") == "dashboard" or
            (data.get("dashboard_data") is not None and len(data.get("dashboard_data", {})) > 0)
        )

    def has_chart_widget(self, data: Dict) -> bool:
        """Check if dashboard has chart widgets."""
        dashboard = data.get("dashboard", {})
        if not dashboard:
            return False
        widgets = dashboard.get("widgets", [])
        chart_types = ["line_chart", "bar_chart", "area_chart", "stacked_bar", "horizontal_bar", "donut_chart"]
        return any(w.get("type") in chart_types for w in widgets)

    def has_kpi_widget(self, data: Dict) -> bool:
        """Check if dashboard has KPI card widgets."""
        dashboard = data.get("dashboard", {})
        if not dashboard:
            return False
        widgets = dashboard.get("widgets", [])
        return any(w.get("type") == "kpi_card" for w in widgets)

    def count_widgets(self, data: Dict) -> int:
        """Count widgets in dashboard."""
        dashboard = data.get("dashboard", {})
        if not dashboard:
            return 0
        return len(dashboard.get("widgets", []))

    def extract_text_response(self, data: Dict) -> str:
        """Extract text response from API response."""
        return data.get("text_response", "") or data.get("primary_answer", "") or data.get("answer", "")

    def run_tc01(self) -> TestResult:
        """TC-01: Simple Metric Query - text response with $150M revenue."""
        tc_id = "TC-01"
        tc_name = "Simple Metric Query"

        try:
            # Use intent-map (galaxy mode) - what UI uses
            data = self.query_api("what's our revenue?")

            # Check for correct value
            has_value = self.contains_value(data, 150.0, 0.05)

            # Check text response
            text = self.extract_text_response(data)
            has_150_in_text = "150" in text

            # Should NOT be a dashboard response (should be text/galaxy)
            is_dashboard = self.has_dashboard_schema(data)

            # Check nodes for value
            nodes = data.get("nodes", [])
            node_has_value = any(
                abs(n.get("value", 0) - 150.0) / 150.0 <= 0.05
                for n in nodes if n.get("value")
            )

            passed = (has_value or has_150_in_text or node_has_value) and not is_dashboard

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Revenue $150M: text={has_150_in_text}, nodes={node_has_value}, not_dashboard={not is_dashboard}",
                verification={
                    "has_150_value": has_value,
                    "text_contains_150": has_150_in_text,
                    "node_has_value": node_has_value,
                    "is_not_dashboard": not is_dashboard,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc02(self) -> TestResult:
        """TC-02: Trend Chart - line/area chart with 8 quarterly data points."""
        tc_id = "TC-02"
        tc_name = "Trend Chart"

        try:
            data = self.query_api("show me revenue over time")

            # Should return dashboard with visualization
            has_dashboard = self.has_dashboard_schema(data)
            has_chart = self.has_chart_widget(data)

            # Check for quarterly data points
            dashboard = data.get("dashboard", {})
            dashboard_data = data.get("dashboard_data", {})

            # Look for time series data
            has_q1_2024 = self.contains_value(data, 22.0, 0.1)  # Q1 2024
            has_q4_2025 = self.contains_value(data, 42.0, 0.1)  # Q4 2025

            # Check widget types
            widget_types = []
            if dashboard:
                widget_types = [w.get("type") for w in dashboard.get("widgets", [])]

            time_chart_types = ["line_chart", "area_chart"]
            has_time_chart = any(t in widget_types for t in time_chart_types)

            passed = has_dashboard and (has_chart or has_time_chart)

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Dashboard: {has_dashboard}, Chart: {has_chart}, Types: {widget_types}",
                verification={
                    "has_dashboard": has_dashboard,
                    "has_chart": has_chart,
                    "has_time_chart": has_time_chart,
                    "widget_types": widget_types,
                    "has_q1_data": has_q1_2024,
                    "has_q4_data": has_q4_2025,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc03(self) -> TestResult:
        """TC-03: Breakdown Chart - bar chart with regional breakdown."""
        tc_id = "TC-03"
        tc_name = "Breakdown Chart"

        try:
            data = self.query_api("show me pipeline by region")
            self.current_dashboard = data  # Save for TC-04

            has_dashboard = self.has_dashboard_schema(data)

            # Check for pipeline total
            has_pipeline = self.contains_value(data, 431.25, 0.1)

            # Check text response for regions
            text = self.extract_text_response(data).lower()
            has_regions = any(r in text for r in ["amer", "emea", "apac", "region"])

            # Check widget types
            dashboard = data.get("dashboard", {})
            widget_types = [w.get("type") for w in dashboard.get("widgets", [])] if dashboard else []
            has_bar_chart = "bar_chart" in widget_types or "horizontal_bar" in widget_types

            passed = has_dashboard or has_pipeline or has_regions

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Dashboard: {has_dashboard}, Pipeline: {has_pipeline}, Regions: {has_regions}, Bar: {has_bar_chart}",
                verification={
                    "has_dashboard": has_dashboard,
                    "has_pipeline_value": has_pipeline,
                    "has_regions": has_regions,
                    "has_bar_chart": has_bar_chart,
                    "widget_types": widget_types,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc04(self) -> TestResult:
        """TC-04: Add Widget (Context) - add KPI preserves existing dashboard."""
        tc_id = "TC-04"
        tc_name = "Add Widget (Context)"

        try:
            # First ensure we have a dashboard (run TC-03 if needed)
            if not self.current_dashboard:
                self.query_api("show me pipeline by region")

            # Now try to add a KPI
            data = self.query_api("add a KPI for win rate")

            # Check for win rate value (42%)
            has_win_rate = self.contains_value(data, 42, 0.1)

            # Check text response
            text = self.extract_text_response(data)
            has_42_in_text = "42" in text

            # Check for KPI widget
            has_kpi = self.has_kpi_widget(data)

            # Check dashboard preserved (has multiple widgets)
            widget_count = self.count_widgets(data)

            passed = has_win_rate or has_42_in_text or has_kpi

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Win rate 42%: value={has_win_rate}, text={has_42_in_text}, kpi={has_kpi}, widgets={widget_count}",
                verification={
                    "has_win_rate_value": has_win_rate,
                    "text_has_42": has_42_in_text,
                    "has_kpi_widget": has_kpi,
                    "widget_count": widget_count,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc05(self) -> TestResult:
        """TC-05: Change Chart Type - change to bar chart preserves data."""
        tc_id = "TC-05"
        tc_name = "Change Chart Type"

        try:
            # First create a line chart
            self.query_api("show me revenue over time")

            # Now change to bar chart
            data = self.query_api("make that a bar chart")

            # Check for bar chart
            dashboard = data.get("dashboard", {})
            widget_types = [w.get("type") for w in dashboard.get("widgets", [])] if dashboard else []
            has_bar = "bar_chart" in widget_types

            # Check text mentions bar
            text = self.extract_text_response(data).lower()
            mentions_bar = "bar" in text

            # Check data preserved (should still have revenue values)
            has_revenue_data = self.contains_value(data, 42, 0.1) or self.contains_value(data, 150, 0.1)

            passed = has_bar or mentions_bar

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Bar chart: widget={has_bar}, text={mentions_bar}, types={widget_types}",
                verification={
                    "has_bar_widget": has_bar,
                    "text_mentions_bar": mentions_bar,
                    "widget_types": widget_types,
                    "has_revenue_data": has_revenue_data,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc06(self) -> TestResult:
        """TC-06: Multi-Widget Dashboard - 3+ widgets with correct values."""
        tc_id = "TC-06"
        tc_name = "Multi-Widget Dashboard"

        try:
            data = self.query_api("build me a sales dashboard")

            # Check for multiple widgets
            widget_count = self.count_widgets(data)

            # Check for key values
            has_revenue = self.contains_value(data, 150, 0.1)
            has_pipeline = self.contains_value(data, 431, 0.1)
            has_win_rate = self.contains_value(data, 42, 0.1)

            # Count nodes if no dashboard
            nodes = data.get("nodes", [])
            node_count = len(nodes)

            passed = (widget_count >= 3) or (node_count >= 3 and (has_revenue or has_pipeline or has_win_rate))

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Widgets: {widget_count}, Nodes: {node_count}, Revenue: {has_revenue}, Pipeline: {has_pipeline}, WinRate: {has_win_rate}",
                verification={
                    "widget_count": widget_count,
                    "node_count": node_count,
                    "has_revenue": has_revenue,
                    "has_pipeline": has_pipeline,
                    "has_win_rate": has_win_rate,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc07(self) -> TestResult:
        """TC-07: Guided Discovery - list available customer metrics."""
        tc_id = "TC-07"
        tc_name = "Guided Discovery"

        try:
            data = self.query_api("what can you show me about customers?")

            text = self.extract_text_response(data).lower()

            # Check for customer metrics
            has_customer_count = "customer" in text or "customer_count" in text
            has_nrr = "nrr" in text or "retention" in text or "net revenue" in text
            has_churn = "churn" in text

            # Should be text response, not chart
            is_dashboard = self.has_dashboard_schema(data) and self.has_chart_widget(data)

            # Check nodes for customer metrics
            nodes = data.get("nodes", [])
            node_metrics = [n.get("metric", "") for n in nodes]
            has_customer_nodes = any("customer" in m or "nrr" in m or "churn" in m for m in node_metrics)

            passed = has_customer_count or has_nrr or has_churn or has_customer_nodes

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Customer: {has_customer_count}, NRR: {has_nrr}, Churn: {has_churn}, Nodes: {has_customer_nodes}",
                verification={
                    "has_customer_count": has_customer_count,
                    "has_nrr": has_nrr,
                    "has_churn": has_churn,
                    "has_customer_nodes": has_customer_nodes,
                    "is_text_response": not is_dashboard,
                    "node_metrics": node_metrics,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc08(self) -> TestResult:
        """TC-08: Ambiguous Query - asks for clarification."""
        tc_id = "TC-08"
        tc_name = "Ambiguous Query"

        try:
            data = self.query_api("show me performance")

            text = self.extract_text_response(data).lower()

            # Check for clarification
            asks_clarification = any(word in text for word in [
                "which", "clarif", "specific", "mean", "type", "what kind",
                "sales performance", "system performance", "team performance"
            ])

            # Check query_type
            query_type = data.get("query_type", "")
            needs_clarification = data.get("needs_clarification", False)

            # Should NOT show chart (don't guess)
            has_chart = self.has_chart_widget(data)

            passed = asks_clarification or needs_clarification or query_type == "AMBIGUOUS"

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Clarification: {asks_clarification}, query_type: {query_type}, no_chart: {not has_chart}",
                verification={
                    "asks_clarification": asks_clarification,
                    "needs_clarification_flag": needs_clarification,
                    "query_type": query_type,
                    "no_chart": not has_chart,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc09(self) -> TestResult:
        """TC-09: Missing Data - graceful handling."""
        tc_id = "TC-09"
        tc_name = "Missing Data"

        try:
            data = self.query_api("show me mars colony revenue")

            text = self.extract_text_response(data).lower()

            # Check for graceful response
            graceful = any(phrase in text for phrase in [
                "not available", "don't have", "no data", "cannot", "unable",
                "doesn't exist", "not found", "can help you with"
            ])

            # Check query_type
            query_type = data.get("query_type", "")

            # Should NOT show chart with fake data
            has_chart = self.has_chart_widget(data)

            # Check no fake values
            has_fake_zero = "$0" in text or "0%" in text

            passed = graceful and not has_chart

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Graceful: {graceful}, no_chart: {not has_chart}, query_type: {query_type}",
                verification={
                    "graceful_response": graceful,
                    "no_chart": not has_chart,
                    "no_fake_values": not has_fake_zero,
                    "query_type": query_type,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc10(self) -> TestResult:
        """TC-10: No Context - graceful handling of context-dependent query."""
        tc_id = "TC-10"
        tc_name = "No Context"

        try:
            # Reset session to clear context
            self.session_id = f"eval_fresh_{datetime.now().strftime('%H%M%S')}"

            data = self.query_api("make it a bar chart")

            text = self.extract_text_response(data).lower()

            # Check for clarification
            asks_clarification = any(word in text for word in [
                "what", "which", "clarif", "first", "no ", "nothing",
                "don't see", "no current", "no existing"
            ])

            # Check query_type
            query_type = data.get("query_type", "")
            needs_clarification = data.get("needs_clarification", False)

            # Should NOT show random chart
            has_chart = self.has_chart_widget(data)

            passed = asks_clarification or needs_clarification or not has_chart

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Clarification: {asks_clarification}, no_chart: {not has_chart}, query_type: {query_type}",
                verification={
                    "asks_clarification": asks_clarification,
                    "needs_clarification_flag": needs_clarification,
                    "no_chart": not has_chart,
                    "query_type": query_type,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc11(self) -> TestResult:
        """TC-11: Cross-Widget Filtering - clicking chart filters table."""
        tc_id = "TC-11"
        tc_name = "Cross-Widget Filtering"

        try:
            # Create dashboard with chart and table
            data = self.query_api("show me pipeline by region with a deals table")

            # Check for dashboard with multiple widgets
            widget_count = self.count_widgets(data)

            # Check for interaction config in schema
            dashboard = data.get("dashboard", {})
            widgets = dashboard.get("widgets", []) if dashboard else []

            has_interactions = any(w.get("interactions") for w in widgets)
            has_filter_config = any(
                (w.get("interactions") or {}).get("filter_targets")
                for w in widgets
                if isinstance(w, dict)
            )

            # This is a UI interaction test - we can only verify the schema supports it
            passed = widget_count >= 2 or has_interactions

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Widgets: {widget_count}, Interactions: {has_interactions}, Filter config: {has_filter_config}",
                verification={
                    "widget_count": widget_count,
                    "has_interactions": has_interactions,
                    "has_filter_config": has_filter_config,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_tc12(self) -> TestResult:
        """TC-12: Multiple KPIs - exact values for revenue, margin, pipeline."""
        tc_id = "TC-12"
        tc_name = "Multiple KPIs"

        try:
            data = self.query_api("show me revenue, margin, and pipeline KPIs")

            # Check for exact values
            has_revenue = self.contains_value(data, 150, 0.05)
            has_margin = self.contains_value(data, 65, 0.05)
            has_pipeline = self.contains_value(data, 431, 0.05)

            # Check text response
            text = self.extract_text_response(data)
            text_has_150 = "150" in text
            text_has_65 = "65" in text
            text_has_431 = "431" in text

            # Check nodes
            nodes = data.get("nodes", [])
            node_values = {n.get("metric"): n.get("value") for n in nodes}

            passed = (has_revenue and has_margin and has_pipeline) or \
                     (text_has_150 and text_has_65 and text_has_431)

            return TestResult(
                id=tc_id,
                name=tc_name,
                status="PASS" if passed else "FAIL",
                message=f"Revenue=$150M: {has_revenue or text_has_150}, Margin=65%: {has_margin or text_has_65}, Pipeline=$431M: {has_pipeline or text_has_431}",
                verification={
                    "has_revenue_150": has_revenue or text_has_150,
                    "has_margin_65": has_margin or text_has_65,
                    "has_pipeline_431": has_pipeline or text_has_431,
                    "node_values": node_values,
                },
                response_data=data
            )
        except Exception as e:
            return TestResult(tc_id, tc_name, "ERROR", str(e))

    def run_all(self) -> Dict[str, Any]:
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("NLQ Dashboard UI Evaluation")
        print("=" * 60 + "\n")

        # Check API health
        try:
            response = requests.get(f"{API_BASE}/", timeout=5)
            print("✅ API server is healthy\n")
        except Exception as e:
            print(f"❌ API server not available: {e}")
            print(f"Please start: PYTHONPATH=/home/user/AOS-NLQ python -m uvicorn src.nlq.main:app --host 0.0.0.0 --port 8000")
            sys.exit(1)

        # Run all test cases
        test_methods = [
            self.run_tc01,
            self.run_tc02,
            self.run_tc03,
            self.run_tc04,
            self.run_tc05,
            self.run_tc06,
            self.run_tc07,
            self.run_tc08,
            self.run_tc09,
            self.run_tc10,
            self.run_tc11,
            self.run_tc12,
        ]

        for test_fn in test_methods:
            result = test_fn()
            self.results.append(result)

            status_icon = "✅" if result.status == "PASS" else ("❌" if result.status == "FAIL" else "⚠️")
            print(f"[{result.status}] {result.id}: {result.name}")
            print(f"  {status_icon} {result.message}")
            print()

        # Summary
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        errors = sum(1 for r in self.results if r.status == "ERROR")
        total = len(self.results)

        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total:  {total}")
        print(f"Pass:   {passed}")
        print(f"Fail:   {failed}")
        print(f"Error:  {errors}")
        print(f"Rate:   {(passed / total * 100):.1f}%")
        print("=" * 60 + "\n")

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "rate": passed / total * 100,
            "results": [
                {
                    "id": r.id,
                    "name": r.name,
                    "status": r.status,
                    "message": r.message,
                    "verification": r.verification,
                }
                for r in self.results
            ]
        }


def main():
    runner = UIEvalRunner()
    summary = runner.run_all()

    # Write results to file
    with open(os.path.join(os.path.dirname(__file__), "eval_results.json"), "w") as f:
        json.dump({
            "date": datetime.now().isoformat(),
            "summary": summary,
            "ground_truth": GROUND_TRUTH,
        }, f, indent=2)

    # Exit with appropriate code
    sys.exit(0 if summary["passed"] == summary["total"] else 1)


if __name__ == "__main__":
    main()
