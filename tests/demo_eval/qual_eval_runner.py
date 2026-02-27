"""Qualitative Demo Eval — 40 queries, HTTP-only, scored on Correct/Complete/Natural (1-3)."""
import json, time, requests, uuid, sys, os

NLQ_URL = "http://localhost:8005/api/v1/query"

# 40 queries organized by persona
QUERIES = {
    "CFO": [
        {"id": "CFO_Q1", "q": "What is our revenue for 2025?", "expect": "point", "gt": 124.18, "unit": "usd_millions", "tol": 10},
        {"id": "CFO_Q2", "q": "Compare 2024 vs 2025 revenue", "expect": "comparison", "gt": None, "unit": "usd_millions", "tol": 15},
        {"id": "CFO_Q3", "q": "What is EBITDA margin?", "expect": "point", "gt": 39.0, "unit": "pct", "tol": 10},
        {"id": "CFO_Q4", "q": "Show me the full P&L", "expect": "composite", "gt": None, "unit": None, "tol": 0},
        {"id": "CFO_Q5", "q": "Show me revenue by region", "expect": "breakdown", "gt": None, "unit": "usd_millions", "tol": 15, "dims": ["AMER", "EMEA", "APAC"]},
        {"id": "CFO_Q6", "q": "What is our burn multiple?", "expect": "point", "gt": -1.3, "unit": "ratio", "tol": 40},
        {"id": "CFO_Q7", "q": "How is ARR trending?", "expect": "comparison", "gt": None, "unit": "usd_millions", "tol": 15},
        {"id": "CFO_Q8", "q": "What is our rule of 40?", "expect": "point", "gt": None, "unit": "pct", "tol": 25},
    ],
    "CRO": [
        {"id": "CRO_Q1", "q": "What is our pipeline?", "expect": "point", "gt": 121.61, "unit": "usd_millions", "tol": 15},
        {"id": "CRO_Q2", "q": "What is our win rate?", "expect": "point", "gt": 40.5, "unit": "pct", "tol": 10},
        {"id": "CRO_Q3", "q": "Show me pipeline by region", "expect": "breakdown", "gt": None, "unit": "usd_millions", "tol": 15, "dims": ["AMER", "EMEA", "APAC"]},
        {"id": "CRO_Q4", "q": "Who are the top 3 sales reps?", "expect": "superlative", "gt": None, "unit": None, "tol": 0},
        {"id": "CRO_Q5", "q": "What is average deal size?", "expect": "point", "gt": None, "unit": "usd", "tol": 25},
        {"id": "CRO_Q6", "q": "What is our sales cycle length?", "expect": "point", "gt": None, "unit": "days", "tol": 25},
        {"id": "CRO_Q7", "q": "Which segment has the best win rate?", "expect": "superlative", "gt": None, "unit": None, "tol": 0},
        {"id": "CRO_Q8", "q": "What is quota attainment?", "expect": "point", "gt": 150, "unit": "pct", "tol": 10},
    ],
    "COO": [
        {"id": "COO_Q1", "q": "What is customer satisfaction?", "expect": "point", "gt": 4.22, "unit": "score", "tol": 10},
        {"id": "COO_Q2", "q": "How is CSAT trending?", "expect": "comparison", "gt": None, "unit": "score", "tol": 15},
        {"id": "COO_Q3", "q": "What is our NPS?", "expect": "point", "gt": 47, "unit": "score", "tol": 15},
        {"id": "COO_Q4", "q": "How many support tickets last quarter?", "expect": "point", "gt": 4121, "unit": "count", "tol": 15},
        {"id": "COO_Q5", "q": "What is first response time?", "expect": "point", "gt": None, "unit": "hours", "tol": 25},
        {"id": "COO_Q6", "q": "Show me CSAT by segment", "expect": "breakdown", "gt": None, "unit": "score", "tol": 15, "dims": ["Enterprise", "Mid-Market", "SMB"]},
        {"id": "COO_Q7", "q": "What is our headcount?", "expect": "point", "gt": 321, "unit": "count", "tol": 10},
        {"id": "COO_Q8", "q": "How many open roles?", "expect": "point", "gt": 51, "unit": "count", "tol": 20},
    ],
    "CTO": [
        {"id": "CTO_Q1", "q": "How many P1 incidents this quarter?", "expect": "point", "gt": 3, "unit": "count", "tol": 50},
        {"id": "CTO_Q2", "q": "What is our MTTR?", "expect": "point", "gt": None, "unit": "hours", "tol": 25},
        {"id": "CTO_Q3", "q": "What is our uptime?", "expect": "point", "gt": 99.59, "unit": "pct", "tol": 2},
        {"id": "CTO_Q4", "q": "Show me uptime by service", "expect": "breakdown", "gt": None, "unit": "pct", "tol": 10},
        {"id": "CTO_Q5", "q": "What is sprint velocity?", "expect": "point", "gt": 101.2, "unit": "story_points", "tol": 15},
        {"id": "CTO_Q6", "q": "How is cloud spend trending?", "expect": "comparison", "gt": None, "unit": "usd_millions", "tol": 15},
        {"id": "CTO_Q7", "q": "Show me cloud spend by category", "expect": "breakdown", "gt": None, "unit": "usd_millions", "tol": 15},
        {"id": "CTO_Q8", "q": "What is our tech debt?", "expect": "point", "gt": 0.133, "unit": "pct", "tol": 25},
    ],
    "CHRO": [
        {"id": "CHRO_Q1", "q": "What is our attrition rate?", "expect": "point", "gt": 11.5, "unit": "pct", "tol": 15},
        {"id": "CHRO_Q2", "q": "Which department has the highest attrition?", "expect": "superlative", "gt": None, "unit": None, "tol": 0},
        {"id": "CHRO_Q3", "q": "What is employee engagement?", "expect": "point", "gt": 4.25, "unit": "score", "tol": 10},
        {"id": "CHRO_Q4", "q": "How many open roles do we have?", "expect": "point", "gt": 51, "unit": "count", "tol": 20},
        {"id": "CHRO_Q5", "q": "What is time to fill?", "expect": "point", "gt": 45, "unit": "days", "tol": 25},
        {"id": "CHRO_Q6", "q": "What is our eNPS?", "expect": "point", "gt": None, "unit": "score", "tol": 15},
        {"id": "CHRO_Q7", "q": "Show me headcount by department", "expect": "breakdown", "gt": None, "unit": "count", "tol": 15, "dims": ["Engineering", "Sales", "G&A"]},
        {"id": "CHRO_Q8", "q": "What is our offer acceptance rate?", "expect": "point", "gt": 84.5, "unit": "pct", "tol": 10},
    ],
}


def send_query(question):
    """Send query via HTTP POST, return (response_json, elapsed_ms)."""
    payload = {
        "question": question,
        "data_mode": "live",
        "session_id": "qual-eval-" + uuid.uuid4().hex[:8],
    }
    t0 = time.time()
    try:
        r = requests.post(NLQ_URL, json=payload, timeout=30)
        elapsed = (time.time() - t0) * 1000
        return r.json(), elapsed
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return {"error": str(e)}, elapsed


def extract_value(resp):
    """Extract the primary numeric value from response."""
    if not resp:
        return None
    for key in ["value", "metric_value"]:
        v = resp.get(key)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    data = resp.get("data", {})
    if isinstance(data, dict):
        for key in ["value", "metric_value", "result"]:
            v = data.get(key)
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
    return None


def extract_answer(resp):
    """Extract the natural language answer."""
    if not resp:
        return ""
    for key in ["answer", "natural_answer", "response", "text"]:
        v = resp.get(key)
        if v and isinstance(v, str):
            return v
    data = resp.get("data", {})
    if isinstance(data, dict):
        for key in ["answer", "natural_answer"]:
            v = data.get(key)
            if v and isinstance(v, str):
                return v
    return ""


def has_field(resp, field):
    """Check if response has a non-null field."""
    if resp.get(field) is not None:
        return True
    data = resp.get("data", {})
    if isinstance(data, dict) and data.get(field) is not None:
        return True
    return False


def has_dimensions(resp, expected_dims):
    """Check if breakdown response contains expected dimensions."""
    answer = extract_answer(resp).lower()
    found = set()
    for d in expected_dims:
        if d.lower() in answer:
            found.add(d)
    # Also check data fields
    data = resp.get("data", {})
    if isinstance(data, dict):
        dims = data.get("dimensions", data.get("breakdown", data.get("rows", [])))
        if isinstance(dims, (list, dict)):
            dim_str = json.dumps(dims).lower()
            for d in expected_dims:
                if d.lower() in dim_str:
                    found.add(d)
    return len(found)


def score_correct(scenario, resp):
    """Score correctness 1-3."""
    expect = scenario["expect"]
    gt = scenario.get("gt")
    tol = scenario.get("tol", 10)

    if resp.get("error") or resp.get("status") == "error":
        return 1, "Error response"

    resp_type = resp.get("response_type", resp.get("type", ""))
    if resp_type in ("clarification", "NEEDS_CLARIFICATION"):
        if expect == "clarification":
            return 3, "Correctly asked for clarification"
        return 1, "Unexpected clarification"

    if expect == "composite":
        answer = extract_answer(resp)
        if len(answer) > 50:
            return 3, "Composite response with content"
        elif len(answer) > 20:
            return 2, "Partial composite"
        return 1, "Thin composite"

    if expect == "superlative":
        answer = extract_answer(resp)
        if answer and len(answer) > 20:
            return 3, "Named entity with value"
        elif answer:
            return 2, "Partial superlative"
        return 1, "No superlative result"

    if expect == "comparison":
        answer = extract_answer(resp)
        compare_words = ["compared", "vs", "versus", "from", "to", "increased",
                         "decreased", "grew", "declined", "change", "growth", "trend"]
        has_compare = any(w in answer.lower() for w in compare_words)
        val = extract_value(resp)
        if has_compare or (val is not None):
            return 3, "Comparison with values"
        elif answer and len(answer) > 30:
            return 2, "Some comparison content"
        return 1, "No comparison"

    if expect == "breakdown":
        dims = scenario.get("dims", [])
        if dims:
            found = has_dimensions(resp, dims)
            if found >= len(dims):
                return 3, "All %d dimensions found" % len(dims)
            elif found > 0:
                return 2, "%d/%d dimensions" % (found, len(dims))
            else:
                return 1, "No dimensions found"
        answer = extract_answer(resp)
        if answer and len(answer) > 50:
            return 2, "Breakdown response but no dim check"
        return 1, "No breakdown"

    # Point value
    if gt is not None:
        val = extract_value(resp)
        if val is None:
            answer = extract_answer(resp)
            return 1, "No numeric value extracted. Answer: %s" % answer[:80]

        if gt == 0:
            if abs(val) < 1:
                return 3, "Value %s close to 0" % val
            return 1, "Value %s far from 0" % val

        pct_off = abs(val - gt) / abs(gt) * 100
        if pct_off <= tol:
            return 3, "Value %s within %d%% of %s (off by %.1f%%)" % (val, tol, gt, pct_off)
        elif pct_off <= tol * 2:
            return 2, "Value %s within %d%% of %s (off by %.1f%%)" % (val, tol * 2, gt, pct_off)
        else:
            return 1, "Value %s off by %.1f%% from %s" % (val, pct_off, gt)

    # No ground truth -- check we got a value at all
    val = extract_value(resp)
    answer = extract_answer(resp)
    if val is not None:
        return 3, "Got value %s" % val
    elif answer and len(answer) > 30:
        return 2, "Got answer text but no numeric value"
    return 1, "No meaningful response"


def score_complete(scenario, resp):
    """Score completeness 1-3."""
    if resp.get("error") or resp.get("status") == "error":
        return 1, "Error"

    points = 0
    details = []

    if extract_value(resp) is not None:
        points += 1
        details.append("value")

    for key in ["unit", "display_unit"]:
        if has_field(resp, key):
            points += 1
            details.append("unit")
            break
    else:
        data = resp.get("data", {})
        if isinstance(data, dict) and (data.get("unit") or data.get("display_unit")):
            points += 1
            details.append("unit")

    answer = extract_answer(resp)
    if answer and len(answer) > 20:
        points += 1
        details.append("answer")

    if has_field(resp, "period") or has_field(resp, "time_range"):
        points += 1
        details.append("period")
    else:
        data = resp.get("data", {})
        if isinstance(data, dict) and (data.get("period") or data.get("time_range")):
            points += 1
            details.append("period")

    if has_field(resp, "confidence"):
        points += 1
        details.append("confidence")

    if points >= 4:
        return 3, "Complete (%s)" % ", ".join(details)
    elif points >= 2:
        return 2, "Partial (%s)" % ", ".join(details)
    return 1, "Sparse (%s)" % (", ".join(details) if details else "nothing")


def score_natural(scenario, resp):
    """Score naturalness 1-3."""
    if resp.get("error") or resp.get("status") == "error":
        return 1, "Error"

    answer = extract_answer(resp)
    if not answer:
        return 1, "No answer text"

    robotic = 0
    if answer.startswith("{") or answer.startswith("["):
        robotic += 2
    if "null" in answer.lower() and "None" not in answer:
        robotic += 1
    if len(answer) < 15:
        robotic += 1
    if answer.count("_") > 3:
        robotic += 1

    natural = 0
    if any(c in answer for c in ["$", "%", "M", "K"]):
        natural += 1
    if len(answer) > 40:
        natural += 1
    if any(w in answer.lower() for w in ["for", "in", "the", "is", "at", "our"]):
        natural += 1
    if "." in answer and not answer.startswith("{"):
        natural += 1

    score = 2 + natural - robotic
    score = max(1, min(3, score))
    reason = "len=%d, natural=%d, robotic=%d" % (len(answer), natural, robotic)
    return score, reason


def main():
    results = {}
    all_scores = []
    total_flags = []

    for persona, queries in QUERIES.items():
        print("\n" + "=" * 60)
        print("  %s (%d queries)" % (persona, len(queries)))
        print("=" * 60)
        persona_scores = []

        for sc in queries:
            qid = sc["id"]
            question = sc["q"]
            print("\n  [%s] %s" % (qid, question))

            resp, elapsed_ms = send_query(question)

            c_score, c_reason = score_correct(sc, resp)
            m_score, m_reason = score_complete(sc, resp)
            n_score, n_reason = score_natural(sc, resp)
            total = c_score + m_score + n_score

            val = extract_value(resp)
            answer = extract_answer(resp)
            unit = resp.get("unit") or resp.get("display_unit") or ""
            if not unit:
                data = resp.get("data", {})
                if isinstance(data, dict):
                    unit = data.get("unit", data.get("display_unit", ""))

            flags = []
            if elapsed_ms > 5000:
                flags.append("SLOW (%.0fms)" % elapsed_ms)
            if resp.get("error"):
                flags.append("ERROR")
            if val is not None and sc.get("gt") is not None and sc["gt"] != 0:
                pct_off = abs(val - sc["gt"]) / abs(sc["gt"]) * 100
                if pct_off > 100:
                    flags.append("IMPOSSIBLE (off by %.0f%%)" % pct_off)

            print("    Value: %s  Unit: %s  Time: %.0fms" % (val, unit, elapsed_ms))
            ans_display = answer[:120] + ("..." if len(answer) > 120 else "")
            print("    Answer: %s" % ans_display)
            print("    Correct=%d (%s)" % (c_score, c_reason))
            print("    Complete=%d (%s)" % (m_score, m_reason))
            print("    Natural=%d (%s)" % (n_score, n_reason))
            line = "    TOTAL: %d/9" % total
            if flags:
                flag_str = " | ".join(flags)
                print("%s  *** FLAGS: %s ***" % (line, flag_str))
                total_flags.append("%s: %s" % (qid, flag_str))
            else:
                print(line)

            result = {
                "id": qid,
                "question": question,
                "value": val,
                "unit": str(unit),
                "answer": answer,
                "elapsed_ms": round(elapsed_ms),
                "correct": c_score,
                "correct_reason": c_reason,
                "complete": m_score,
                "complete_reason": m_reason,
                "natural": n_score,
                "natural_reason": n_reason,
                "total": total,
                "flags": flags,
                "raw_response": resp,
            }
            persona_scores.append(result)
            all_scores.append(result)

        p_total = sum(r["total"] for r in persona_scores)
        p_max = len(persona_scores) * 9
        p_pass = "PASS" if p_total >= (p_max * 0.67) else "FAIL"
        print("\n  %s TOTAL: %d/%d (%.0f%%) -- %s" % (persona, p_total, p_max, p_total / p_max * 100, p_pass))
        results[persona] = {
            "scores": persona_scores,
            "total": p_total,
            "max": p_max,
            "pct": round(p_total / p_max * 100, 1),
            "status": p_pass,
        }

    grand_total = sum(r["total"] for r in all_scores)
    grand_max = len(all_scores) * 9
    grand_pct = grand_total / grand_max * 100

    print("\n" + "=" * 60)
    print("  OVERALL SUMMARY")
    print("=" * 60)
    for persona, data in results.items():
        status_icon = "PASS" if data["status"] == "PASS" else "**FAIL**"
        print("  %-6s: %3d/%d (%5.1f%%) %s" % (persona, data["total"], data["max"], data["pct"], status_icon))
    print("  %-6s  %3s" % ("", "---"))
    print("  %-6s: %3d/%d (%.1f%%)" % ("TOTAL", grand_total, grand_max, grand_pct))

    all_pass = all(d["status"] == "PASS" for d in results.values())
    print("\n  DEMO READY: %s" % ("YES" if all_pass else "NO"))

    if total_flags:
        print("\n  FLAGS (%d):" % len(total_flags))
        for f in total_flags:
            print("    - %s" % f)

    sub5 = [r for r in all_scores if r["total"] < 5]
    if sub5:
        print("\n" + "=" * 60)
        print("  CRITICAL FAILURES (score < 5/9): %d" % len(sub5))
        print("=" * 60)
        for r in sub5:
            print("\n  [%s] %s" % (r["id"], r["question"]))
            print("    Score: %d/%d/%d = %d/9" % (r["correct"], r["complete"], r["natural"], r["total"]))
            print("    Value: %s  Unit: %s" % (r["value"], r["unit"]))
            print("    Answer: %s" % r["answer"][:200])
            print("    Correct: %s" % r["correct_reason"])
            print("    Complete: %s" % r["complete_reason"])
            if r["flags"]:
                print("    Flags: %s" % ", ".join(r["flags"]))

    # Save
    out_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "qual_eval_latest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "summary": {
                    p: {k: v for k, v in d.items() if k != "scores"}
                    for p, d in results.items()
                },
                "grand_total": grand_total,
                "grand_max": grand_max,
                "grand_pct": round(grand_pct, 1),
                "demo_ready": all_pass,
                "flags": total_flags,
                "details": all_scores,
            },
            f,
            indent=2,
            default=str,
        )
    print("\n  Results saved to %s" % out_path)


if __name__ == "__main__":
    main()
