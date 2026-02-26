"""
AOS-NLQ Demo Eval Runner — Qualitative Scoring

Runs 40 scenarios (5 personas x 8 queries) against the live NLQ system
and scores each response on three dimensions:

  Correct (1-3):  Value matches Farm ground truth
  Complete (1-3): Includes period, unit, trend/context
  Natural (1-3):  Sounds like a good answer, not a database printout

Max per persona: 24. Passing bar: 18 (75%).

Usage:
  python -m tests.demo_eval.demo_eval [--url URL] [--verbose] [--persona CFO]
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_URL = "https://aos-nlq.onrender.com"
ENDPOINT = "/api/v1/query"
HEALTH_ENDPOINT = "/api/v1/health"
TIMEOUT = 45.0
SCENARIOS_FILE = Path(__file__).parent / "scenarios.yaml"
RESULTS_DIR = Path(__file__).parent / "results"

BANNED_SOURCES = {"demo", "local", "local_fallback", "fact_base"}

# Unit aliases — NLQ may return different unit strings for the same concept
UNIT_ALIASES = {
    "usd_millions": {"usd_millions", "USD millions", "$M", "millions"},
    "pct": {"pct", "percent", "%"},
    "count": {"count", "people", "customers", "tickets", "incidents", "roles", "hires"},
    "score": {"score", "score_5", "points"},
    "ratio": {"ratio", "x", "multiple"},
    "days": {"days", "day"},
    "hours": {"hours", "hour"},
    "story_points": {"story_points", "points", "sp"},
}


def _unit_matches(expected: str, actual: str) -> bool:
    """Check if actual unit matches expected, considering aliases."""
    if expected is None:
        return True
    if actual is None:
        return False
    expected_lower = expected.lower().strip()
    actual_lower = actual.lower().strip()
    if expected_lower == actual_lower:
        return True
    # Check alias groups
    for _canonical, aliases in UNIT_ALIASES.items():
        aliases_lower = {a.lower() for a in aliases}
        if expected_lower in aliases_lower and actual_lower in aliases_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Response extraction helpers
# ---------------------------------------------------------------------------

def extract_value(resp: Dict) -> Optional[float]:
    """Extract numeric value from NLQ response."""
    return resp.get("value")


def extract_unit(resp: Dict) -> Optional[str]:
    """Extract unit from NLQ response."""
    return resp.get("unit")


def extract_answer(resp: Dict) -> Optional[str]:
    """Extract answer text from NLQ response."""
    return resp.get("answer")


def extract_dimensions(resp: Dict) -> List[str]:
    """Extract dimension labels from breakdown responses."""
    labels = []

    # Check dashboard_data for dimensional series
    dd = resp.get("dashboard_data") or {}
    for _wid, wdata in dd.items():
        if isinstance(wdata, dict):
            for series in wdata.get("series", []):
                for pt in series.get("data", []):
                    if isinstance(pt, dict) and "label" in pt:
                        labels.append(str(pt["label"]))

    # Check related_metrics
    for rm in resp.get("related_metrics") or []:
        if isinstance(rm, dict):
            name = rm.get("display_name") or rm.get("metric", "")
            if name:
                labels.append(name)

    return labels


def extract_comparison_values(resp: Dict) -> Dict[str, Optional[float]]:
    """Extract comparison period values from response."""
    vals = {}
    for rm in resp.get("related_metrics") or []:
        if isinstance(rm, dict):
            period = str(rm.get("period", ""))
            value = rm.get("value")
            if "2024" in period:
                vals["value_2024"] = value
            elif "2025" in period:
                vals["value_2025"] = value

    # Also check answer text for inline values
    answer = resp.get("answer") or ""
    if not vals.get("value_2024") and "2024" in answer:
        nums = re.findall(r'2024[^0-9]*?\$?([\d,.]+)', answer)
        if nums:
            try:
                vals["value_2024"] = float(nums[0].replace(",", ""))
            except ValueError:
                pass
    if not vals.get("value_2025") and "2025" in answer:
        nums = re.findall(r'2025[^0-9]*?\$?([\d,.]+)', answer)
        if nums:
            try:
                vals["value_2025"] = float(nums[0].replace(",", ""))
            except ValueError:
                pass

    return vals


def extract_superlative_label(resp: Dict) -> Optional[str]:
    """Extract the top/bottom ranked dimension label."""
    answer = resp.get("answer") or ""
    # Check dashboard_data for ranked results
    dd = resp.get("dashboard_data") or {}
    for _wid, wdata in dd.items():
        if isinstance(wdata, dict):
            for series in wdata.get("series", []):
                data = series.get("data", [])
                if data and isinstance(data[0], dict):
                    return data[0].get("label")

    # Check related_metrics
    rms = resp.get("related_metrics") or []
    if rms:
        first = rms[0] if isinstance(rms[0], dict) else {}
        return first.get("display_name") or first.get("metric")

    # Fallback: try to find a capitalized name in the answer
    if answer:
        # Look for quoted names or capitalized multi-word sequences
        quoted = re.findall(r'"([^"]+)"', answer)
        if quoted:
            return quoted[0]

    return None


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def score_correct(scenario: Dict, resp: Dict) -> Tuple[int, str]:
    """Score correctness (1-3) based on value matching ground truth."""
    expect_type = scenario.get("expect_type", "point")
    expected = scenario.get("expected_value")

    # Clarification: correct if system asked for clarification
    if expect_type == "clarification":
        if resp.get("needs_clarification"):
            return 3, "asked for clarification"
        answer = (resp.get("answer") or "").lower()
        clarification_signals = ["which", "did you mean", "could you specify",
                                 "clarify", "do you mean", "please specify"]
        if any(s in answer for s in clarification_signals):
            return 2, "implied clarification in answer"
        if resp.get("success") and resp.get("value") is not None:
            return 1, "gave a value instead of clarifying"
        return 1, "no clarification behavior"

    # Superlative: correct if we got a dimension label
    if expect_type == "superlative":
        label = extract_superlative_label(resp)
        if label and len(label) > 1:
            return 3, f"ranked result: {label}"
        if resp.get("success") and resp.get("answer"):
            return 2, "answered but unclear ranking"
        return 1, "no ranking result"

    # Breakdown: correct if expected dimensions are present
    if expect_type == "breakdown":
        check_dims = scenario.get("check_dimensions", [])
        found_dims = extract_dimensions(resp)
        found_lower = {d.lower() for d in found_dims}
        matched = sum(1 for d in check_dims if d.lower() in found_lower)
        if not check_dims:
            # No specific dimensions to check — just verify we got some
            if found_dims:
                return 3, f"breakdown with {len(found_dims)} dimensions"
            if resp.get("success") and resp.get("answer"):
                return 2, "answered but no dimensional data"
            return 1, "no breakdown data"
        if matched == len(check_dims):
            return 3, f"all {matched} dimensions present"
        if matched > 0:
            return 2, f"{matched}/{len(check_dims)} dimensions present"
        return 1, f"0/{len(check_dims)} expected dimensions found"

    # Comparison: correct if we got values for both periods
    if expect_type == "comparison":
        comp_vals = extract_comparison_values(resp)
        check_fields = scenario.get("check_fields", [])
        if check_fields:
            found = sum(1 for f in check_fields if comp_vals.get(f) is not None)
            if found == len(check_fields):
                return 3, f"both comparison values present"
            if found > 0:
                return 2, f"{found}/{len(check_fields)} comparison values"
        # Fallback: check if answer mentions both years
        answer = (resp.get("answer") or "")
        if "2024" in answer and "2025" in answer:
            return 2, "both years mentioned in answer"
        if resp.get("success"):
            return 1, "comparison attempted but incomplete"
        return 1, "no comparison data"

    # Composite: correct if multiple metrics present
    if expect_type == "composite":
        rms = resp.get("related_metrics") or []
        if len(rms) >= 3:
            return 3, f"{len(rms)} related metrics"
        if len(rms) >= 1:
            return 2, f"only {len(rms)} related metrics"
        return 1, "no composite data"

    # Point query: check value against expected
    if expected is None:
        if resp.get("success") and resp.get("value") is not None:
            return 2, "got a value but no ground truth to check"
        return 1, "no value and no ground truth"

    actual = extract_value(resp)
    if actual is None:
        return 1, f"value is None (expected ~{expected})"

    tolerance = scenario.get("tolerance_pct", 10)
    # Handle negative expected values
    if expected == 0:
        pct_off = abs(actual) * 100
    else:
        pct_off = abs(actual - expected) / abs(expected) * 100

    if pct_off <= tolerance:
        return 3, f"value={actual} within {tolerance}% of {expected} (off by {pct_off:.1f}%)"
    if pct_off <= tolerance * 2:
        return 2, f"value={actual} within {tolerance*2}% of {expected} (off by {pct_off:.1f}%)"
    return 1, f"value={actual} off by {pct_off:.1f}% from {expected}"


def score_complete(scenario: Dict, resp: Dict) -> Tuple[int, str]:
    """Score completeness (1-3) based on metadata presence."""
    expect_type = scenario.get("expect_type", "point")

    # Clarification type — complete if it gives options
    if expect_type == "clarification":
        answer = resp.get("answer") or ""
        prompt = resp.get("clarification_prompt") or ""
        if resp.get("needs_clarification") and (prompt or answer):
            return 3, "clarification with prompt"
        if "?" in answer or "which" in answer.lower():
            return 2, "question in answer but no structured prompt"
        return 1, "no clarification detail"

    has_value = resp.get("value") is not None
    has_unit = resp.get("unit") is not None and resp.get("unit") != "unknown"
    has_period = resp.get("resolved_period") is not None
    has_answer = resp.get("answer") is not None and len(resp.get("answer", "")) > 5
    has_trend = resp.get("related_metrics") is not None and len(resp.get("related_metrics", [])) > 0
    has_provenance = resp.get("provenance") is not None
    has_confidence = resp.get("confidence", 0) > 0.5

    # Check unit correctness
    expected_unit = scenario.get("expected_unit")
    unit_correct = _unit_matches(expected_unit, resp.get("unit"))

    # For breakdown/superlative, value may be null but answer should exist
    if expect_type in ("breakdown", "superlative", "comparison", "composite"):
        pieces = sum([has_answer, has_confidence, has_provenance,
                      bool(extract_dimensions(resp) or extract_comparison_values(resp))])
        if pieces >= 3:
            return 3, "rich response with metadata"
        if pieces >= 2:
            return 2, "adequate metadata"
        return 1, "sparse response"

    # Point query completeness
    pieces = sum([has_value, has_unit and unit_correct, has_period, has_answer, has_confidence])
    if pieces >= 4:
        return 3, "value + unit + period + answer"
    if pieces >= 3:
        return 2, f"missing some metadata ({pieces}/5 fields)"
    return 1, f"sparse response ({pieces}/5 fields)"


def score_natural(scenario: Dict, resp: Dict) -> Tuple[int, str]:
    """Score naturalness (1-3) — does this sound like a good answer?"""
    answer = resp.get("answer") or ""

    if not answer:
        return 1, "no answer text"

    # Length checks
    length = len(answer)

    # Bad signals
    bad_signals = 0
    reasons_bad = []

    if length < 10:
        bad_signals += 1
        reasons_bad.append("too short")

    if length > 800:
        bad_signals += 1
        reasons_bad.append("too verbose")

    # Raw data dump detection
    if answer.strip().startswith("{") or answer.strip().startswith("["):
        return 1, "raw JSON dump"

    if "error" in answer.lower() and ("traceback" in answer.lower() or "exception" in answer.lower()):
        return 1, "error/traceback in answer"

    # Robotic patterns
    robotic = ["the value of", "the current value is", "result:", "data:", "query returned"]
    if any(r in answer.lower() for r in robotic):
        bad_signals += 1
        reasons_bad.append("robotic phrasing")

    # Good signals
    good_signals = 0
    reasons_good = []

    # Formatted numbers ($, %, M)
    if re.search(r'\$[\d,.]+', answer) or re.search(r'[\d,.]+%', answer) or re.search(r'[\d,.]+M', answer):
        good_signals += 1
        reasons_good.append("formatted numbers")

    # Natural sentence structure (starts with capital, has verb-like words)
    if answer[0].isupper() and len(answer.split()) > 3:
        good_signals += 1
        reasons_good.append("sentence structure")

    # Context/comparison language
    context_words = ["compared to", "up from", "down from", "increase", "decrease",
                     "growth", "trend", "year-over-year", "vs", "compared",
                     "quarter", "year", "period", "for 2025", "in Q"]
    if any(w in answer.lower() for w in context_words):
        good_signals += 1
        reasons_good.append("contextual language")

    # Scoring
    if bad_signals == 0 and good_signals >= 2:
        return 3, " + ".join(reasons_good)
    if bad_signals <= 1 and good_signals >= 1:
        return 2, (" + ".join(reasons_good) + "; " + ", ".join(reasons_bad)).strip("; ")
    return 1, ", ".join(reasons_bad) if reasons_bad else "flat delivery"


# ---------------------------------------------------------------------------
# Query runner
# ---------------------------------------------------------------------------

def run_query(client: httpx.Client, base_url: str, question: str,
              persona: str, data_mode: str = "live") -> Tuple[Dict, float]:
    """Send query to NLQ and return (response_dict, elapsed_seconds)."""
    session_id = f"eval_{uuid.uuid4().hex[:12]}"
    payload = {
        "question": question,
        "data_mode": data_mode,
        "mode": "ai",
        "session_id": session_id,
    }
    start = time.monotonic()
    try:
        response = client.post(
            f"{base_url}{ENDPOINT}",
            json=payload,
            timeout=TIMEOUT,
        )
        elapsed = time.monotonic() - start

        if response.status_code >= 400:
            return {
                "success": False,
                "error_code": f"HTTP_{response.status_code}",
                "error_message": response.text[:500],
                "answer": None,
                "value": None,
                "unit": None,
            }, elapsed

        return response.json(), elapsed

    except httpx.TimeoutException:
        elapsed = time.monotonic() - start
        return {
            "success": False,
            "error_code": "TIMEOUT",
            "error_message": f"Request timed out after {TIMEOUT}s",
            "answer": None,
            "value": None,
            "unit": None,
        }, elapsed
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "success": False,
            "error_code": "CONNECTION_ERROR",
            "error_message": str(e),
            "answer": None,
            "value": None,
            "unit": None,
        }, elapsed


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def load_scenarios(persona_filter: Optional[str] = None) -> Dict[str, List[Dict]]:
    """Load scenarios from YAML, optionally filtering by persona."""
    with open(SCENARIOS_FILE) as f:
        data = yaml.safe_load(f)

    scenarios = data.get("scenarios", {})
    if persona_filter:
        key = persona_filter.lower()
        if key in scenarios:
            return {key: scenarios[key]}
        print(f"  ERROR: Unknown persona '{persona_filter}'. "
              f"Available: {', '.join(scenarios.keys())}")
        sys.exit(1)
    return scenarios


def check_health(client: httpx.Client, base_url: str) -> bool:
    """Verify NLQ is reachable and live data is available."""
    try:
        resp = client.get(f"{base_url}{HEALTH_ENDPOINT}", timeout=10.0)
        if resp.status_code != 200:
            return False
        body = resp.json()
        live = body.get("live_data_available", False)
        status = body.get("status", "unknown")
        print(f"  Server {status} | live_data_available={live}")
        return True
    except Exception as e:
        print(f"  ERROR: Cannot reach {base_url}: {e}")
        return False


def run_eval(base_url: str, verbose: bool = False,
             persona_filter: Optional[str] = None) -> Dict:
    """Run the full demo eval and return results."""
    scenarios = load_scenarios(persona_filter)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

    print()
    print("=" * 76)
    print("  AOS-NLQ Demo Eval — Qualitative Scoring")
    total = sum(len(v) for v in scenarios.values())
    print(f"  {total} scenarios | {len(scenarios)} personas | data_mode=live")
    print(f"  Endpoint: POST {base_url}{ENDPOINT}")
    print("=" * 76)
    print()

    client = httpx.Client()
    if not check_health(client, base_url):
        print("\n  FATAL: NLQ is unreachable. Eval cannot proceed.")
        sys.exit(1)

    print()

    all_results = {}
    persona_summaries = {}

    for persona, persona_scenarios in scenarios.items():
        persona_upper = persona.upper()
        print(f"  {'='*72}")
        print(f"  {persona_upper} ({len(persona_scenarios)} scenarios)")
        print(f"  {'='*72}")

        persona_results = []
        persona_total = {"correct": 0, "complete": 0, "natural": 0}

        for scenario in persona_scenarios:
            sid = scenario["id"]
            question = scenario["question"]

            resp, elapsed = run_query(client, base_url, question, persona)

            # Check for banned data sources
            ds = (resp.get("data_source") or "").lower()
            if ds in BANNED_SOURCES:
                resp["_banned_source"] = True

            # Score
            c_score, c_reason = score_correct(scenario, resp)
            cm_score, cm_reason = score_complete(scenario, resp)
            n_score, n_reason = score_natural(scenario, resp)
            total_score = c_score + cm_score + n_score

            persona_total["correct"] += c_score
            persona_total["complete"] += cm_score
            persona_total["natural"] += n_score

            # Status icon
            if total_score >= 7:
                icon = "PASS"
            elif total_score >= 5:
                icon = "FAIR"
            else:
                icon = "FAIL"

            # Print result
            print(f"\n  {sid:12s} {icon} [{elapsed:4.1f}s] {question}")
            print(f"               C={c_score} Cm={cm_score} N={n_score} "
                  f"(total={total_score}/9)")

            if verbose or icon == "FAIL":
                answer_preview = (resp.get("answer") or "(no answer)")[:120]
                print(f"               Answer: {answer_preview}")
                if c_score < 3:
                    print(f"               Correct: {c_reason}")
                if cm_score < 3:
                    print(f"               Complete: {cm_reason}")
                if n_score < 3:
                    print(f"               Natural: {n_reason}")
                if resp.get("_banned_source"):
                    print(f"               WARNING: banned data_source={ds}")

            result = {
                "id": sid,
                "question": question,
                "expect_type": scenario.get("expect_type"),
                "elapsed_s": round(elapsed, 2),
                "scores": {
                    "correct": c_score,
                    "complete": cm_score,
                    "natural": n_score,
                    "total": total_score,
                },
                "reasons": {
                    "correct": c_reason,
                    "complete": cm_reason,
                    "natural": n_reason,
                },
                "response": {
                    "success": resp.get("success"),
                    "answer": resp.get("answer"),
                    "value": resp.get("value"),
                    "unit": resp.get("unit"),
                    "confidence": resp.get("confidence"),
                    "resolved_metric": resp.get("resolved_metric"),
                    "resolved_period": resp.get("resolved_period"),
                    "data_source": resp.get("data_source"),
                    "needs_clarification": resp.get("needs_clarification"),
                    "response_type": resp.get("response_type"),
                },
            }
            persona_results.append(result)

        # Persona summary
        persona_score = sum(persona_total.values())
        max_score = len(persona_scenarios) * 9
        passing = persona_score >= len(persona_scenarios) * 9 * 0.75
        pct = persona_score / max_score * 100 if max_score else 0

        persona_summaries[persona] = {
            "total_score": persona_score,
            "max_score": max_score,
            "pct": round(pct, 1),
            "passing": passing,
            "correct": persona_total["correct"],
            "complete": persona_total["complete"],
            "natural": persona_total["natural"],
        }

        status = "PASS" if passing else "FAIL"
        print(f"\n  {persona_upper} TOTAL: {persona_score}/{max_score} "
              f"({pct:.0f}%) [{status}]")
        print(f"    Correct={persona_total['correct']}  "
              f"Complete={persona_total['complete']}  "
              f"Natural={persona_total['natural']}")

        all_results[persona] = persona_results

    client.close()

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print()
    print("=" * 76)
    print("  DEMO EVAL SUMMARY")
    print("-" * 76)
    print(f"  {'Persona':<8} {'Score':>6} {'Max':>5} {'Pct':>5}  "
          f"{'C':>3} {'Cm':>3} {'N':>3}  {'Status'}")
    print(f"  {'-'*8} {'-'*6} {'-'*5} {'-'*5}  {'-'*3} {'-'*3} {'-'*3}  {'-'*6}")

    grand_total = 0
    grand_max = 0
    all_passing = True
    for persona, summary in persona_summaries.items():
        status = "PASS" if summary["passing"] else "FAIL"
        if not summary["passing"]:
            all_passing = False
        grand_total += summary["total_score"]
        grand_max += summary["max_score"]
        print(f"  {persona.upper():<8} {summary['total_score']:>6} "
              f"{summary['max_score']:>5} {summary['pct']:>4.0f}%  "
              f"{summary['correct']:>3} {summary['complete']:>3} "
              f"{summary['natural']:>3}  {status}")

    grand_pct = grand_total / grand_max * 100 if grand_max else 0
    grand_status = "PASS" if all_passing else "FAIL"
    print(f"  {'TOTAL':<8} {grand_total:>6} {grand_max:>5} "
          f"{grand_pct:>4.0f}%  "
          f"{sum(s['correct'] for s in persona_summaries.values()):>3} "
          f"{sum(s['complete'] for s in persona_summaries.values()):>3} "
          f"{sum(s['natural'] for s in persona_summaries.values()):>3}  "
          f"{grand_status}")
    print("-" * 76)

    # Show failures
    failures = []
    for persona, results in all_results.items():
        for r in results:
            if r["scores"]["total"] < 5:
                failures.append(r)

    if failures:
        print(f"\n  FAILURES ({len(failures)}):")
        for f in failures:
            print(f"    {f['id']} -- {f['question']}")
            print(f"      Scores: C={f['scores']['correct']} "
                  f"Cm={f['scores']['complete']} N={f['scores']['natural']}")
            answer = (f["response"].get("answer") or "(no answer)")[:200]
            print(f"      Answer: {answer}")
            print(f"      Correct: {f['reasons']['correct']}")
            print()

    print("=" * 76)

    # -----------------------------------------------------------------------
    # Save JSON report
    # -----------------------------------------------------------------------
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / f"eval_{timestamp}.json"
    report = {
        "timestamp": timestamp,
        "base_url": base_url,
        "total_scenarios": total,
        "grand_total": grand_total,
        "grand_max": grand_max,
        "grand_pct": round(grand_pct, 1),
        "all_passing": all_passing,
        "persona_summaries": persona_summaries,
        "results": all_results,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  JSON report: {report_path}")
    print()

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AOS-NLQ Demo Eval — Qualitative Scoring"
    )
    parser.add_argument("--url", default=DEFAULT_URL,
                        help=f"NLQ base URL (default: {DEFAULT_URL})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show answer text and scoring reasons for all scenarios")
    parser.add_argument("--persona", "-p", default=None,
                        help="Run only one persona (e.g., cfo, cro, cto)")
    args = parser.parse_args()

    report = run_eval(args.url, verbose=args.verbose, persona_filter=args.persona)

    sys.exit(0 if report["all_passing"] else 1)


if __name__ == "__main__":
    main()
