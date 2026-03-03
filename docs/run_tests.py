#!/usr/bin/env python3
import argparse, json, sys, time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"
DIM="\033[2m"; BOLD="\033[1m"; RESET="\033[0m"

def load_tests(path):
    with open(path) as f: data = json.load(f)
    return [t for t in data["test_cases"] if "id" in t]

def post_json(url, payload, timeout=30):
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read()), None
    except HTTPError as e:
        try: rb = json.loads(e.read())
        except: rb = {}
        return e.code, rb, str(e)
    except URLError as e: return 0, {}, "Connection failed: "+str(e.reason)
    except Exception as e: return 0, {}, str(e)

def deep_search(obj, key):
    r = []
    if isinstance(obj, dict):
        for k,v in obj.items():
            if k == key: r.append(v)
            r.extend(deep_search(v, key))
    elif isinstance(obj, list):
        for i in obj: r.extend(deep_search(i, key))
    return r

def deep_key_exists(obj, key):
    if isinstance(obj, dict):
        if key in obj: return True
        return any(deep_key_exists(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(deep_key_exists(i, key) for i in obj)
    return False

def flatten_text(obj):
    if isinstance(obj, str): return obj.lower()
    if isinstance(obj, dict): return " ".join(flatten_text(v) for v in obj.values())
    if isinstance(obj, list): return " ".join(flatten_text(i) for i in obj)
    return str(obj).lower()

def collect_data_values(obj):
    vals = []
    dk = {"data","values","rows","results","series","items","breakdown_data",
          "chart_data","metrics_data","widget_data","widgets","elements","components","nodes"}
    if isinstance(obj, dict):
        for k,v in obj.items():
            if k in dk:
                if isinstance(v, list): vals.extend(v)
                elif isinstance(v, dict) and v: vals.append(v)
            else: vals.extend(collect_data_values(v))
    elif isinstance(obj, list):
        for i in obj: vals.extend(collect_data_values(i))
    return vals

def collect_numeric_values(obj):
    nums = []
    if isinstance(obj, dict):
        for k,v in obj.items():
            if k in ("value","amount","total","count") and isinstance(v,(int,float)):
                nums.append(v)
            elif isinstance(v,(dict,list)): nums.extend(collect_numeric_values(v))
    elif isinstance(obj, list):
        for i in obj:
            if isinstance(i,(int,float)): nums.append(i)
            else: nums.extend(collect_numeric_values(i))
    return nums

METRIC_FIELDS = ["metric","metric_id","metric_name","resolved_metric"]
UNIT_FIELDS = ["unit","units","format","display_unit","value_format"]

def check_expectations(expect, status, body):
    F = []; flat = flatten_text(body)

    if "status" in expect and status != expect["status"]:
        F.append("Expected status %d, got %d" % (expect["status"], status))

    for p in expect.get("response_must_contain", []):
        if p.lower() not in flat: F.append("Missing text: '%s'" % p)
    for p in expect.get("response_must_not_contain", []):
        if p.lower() in flat: F.append("Forbidden text: '%s'" % p)

    if "metric_must_be" in expect:
        t = expect["metric_must_be"].lower()
        found = []
        for k in METRIC_FIELDS: found.extend(deep_search(body, k))
        fl = [str(m).lower() for m in found]
        if fl and t not in fl: F.append("Expected metric '%s', found: %s" % (t, found))
        elif not fl and t not in flat: F.append("Metric '%s' not found" % t)

    if "metric_must_not_be" in expect:
        b = expect["metric_must_not_be"].lower()
        found = []
        for k in METRIC_FIELDS: found.extend(deep_search(body, k))
        if b in [str(m).lower() for m in found]:
            F.append("Forbidden metric: '%s'" % b)

    for field, allowed in expect.get("field_checks", {}).items():
        if field.endswith("_in"):
            af = field[:-3]
            found = deep_search(body, af)
            fl = [str(v).lower() for v in found]
            al = [str(v).lower() for v in allowed]
            if not any(f in al for f in fl):
                F.append("'%s' expected %s, found: %s" % (af, allowed, found or "(none)"))

    # -- v2 assertions --

    if expect.get("data_must_exist"):
        if not collect_data_values(body):
            F.append("data_must_exist: no data payload found")

    if "data_count_min" in expect:
        mn = expect["data_count_min"]
        dv = collect_data_values(body)
        if len(dv) < mn: F.append("data_count_min: need >= %d, got %d" % (mn, len(dv)))

    if "unit_must_be" in expect:
        tu = expect["unit_must_be"].lower()
        fu = []
        for k in UNIT_FIELDS: fu.extend(deep_search(body, k))
        fl2 = [str(u).lower() for u in fu]
        if fl2 and tu not in fl2: F.append("unit_must_be: expected '%s', found: %s" % (tu, fu))
        elif not fl2 and tu not in flat: F.append("unit_must_be: '%s' not found" % tu)

    if "unit_must_not_be" in expect:
        bu = expect["unit_must_not_be"].lower()
        fu = []
        for k in UNIT_FIELDS: fu.extend(deep_search(body, k))
        if bu in [str(u).lower() for u in fu]: F.append("unit_must_not_be: found '%s'" % bu)

    if "metrics_must_include_any" in expect:
        w = [m.lower() for m in expect["metrics_must_include_any"]]
        found = []
        for k in METRIC_FIELDS: found.extend(deep_search(body, k))
        fl3 = [str(m).lower() for m in found]
        if not any(x in fl3 for x in w): F.append("metrics_must_include_any: none of %s" % w)

    if "metrics_must_include_all" in expect:
        w = [m.lower() for m in expect["metrics_must_include_all"]]
        found = set()
        for k in METRIC_FIELDS:
            for v in deep_search(body, k): found.add(str(v).lower())
        miss = [x for x in w if x not in found]
        if miss: F.append("metrics_must_include_all: missing %s" % miss)

    if "breakdown_must_include" in expect:
        w = [v.lower() for v in expect["breakdown_must_include"]]
        miss = [v for v in w if v not in flat]
        if miss: F.append("breakdown_must_include: missing %s" % miss)

    for fn in expect.get("field_must_exist", []):
        if not deep_key_exists(body, fn): F.append("field_must_exist: '%s' missing" % fn)

    if expect.get("value_must_be_numeric"):
        if not collect_numeric_values(body):
            F.append("value_must_be_numeric: no numeric values")

    return F

def run_tests(base_url, tests, verbose=False):
    passed=failed=errors=skipped=0; results=[]
    print("\n%sNLQ Ground Truth Tests v2%s" % (BOLD, RESET))
    print("Target: %s\nCases:  %d" % (base_url, len(tests)))
    print("-" * 76)

    for tc in tests:
        tid = tc["id"]; desc = tc["description"]
        if tc.get("skip"):
            print("  %sSKIP%s %s: %s %s(%s)%s" % (YELLOW,RESET,tid,desc,DIM,tc.get("skip_reason",""),RESET))
            skipped += 1; results.append({"id":tid,"result":"SKIP"}); continue

        url = base_url.rstrip("/") + tc["endpoint"]
        t0 = time.time()
        st, body, err = post_json(url, tc["payload"])
        el = time.time() - t0

        if err and st == 0:
            print("  %sERR %s %s: %s\n       %s%s%s" % (RED,RESET,tid,desc,DIM,err,RESET))
            errors += 1; results.append({"id":tid,"result":"ERROR","error":err}); continue

        fails = check_expectations(tc["expect"], st, body)
        if not fails:
            print("  %sPASS%s %s: %s %s(%.1fs)%s" % (GREEN,RESET,tid,desc,DIM,el,RESET))
            passed += 1; results.append({"id":tid,"result":"PASS","elapsed":round(el,2)})
        else:
            print("  %sFAIL%s %s: %s %s(%.1fs)%s" % (RED,RESET,tid,desc,DIM,el,RESET))
            for f in fails: print("       %sx%s %s" % (RED,RESET,f))
            failed += 1; results.append({"id":tid,"result":"FAIL","failures":fails})

        if verbose:
            print("       %sPOST %s -> %d%s" % (DIM,tc["endpoint"],st,RESET))
            bs = json.dumps(body, indent=2)
            if len(bs) > 800: bs = bs[:800]+"\n       ..."
            for ln in bs.split("\n"): print("       %s%s%s" % (DIM,ln,RESET))

    print("-" * 76)
    pts = []
    if passed:  pts.append("%s%d passed%s" % (GREEN,passed,RESET))
    if failed:  pts.append("%s%d failed%s" % (RED,failed,RESET))
    if errors:  pts.append("%s%d errors%s" % (YELLOW,errors,RESET))
    if skipped: pts.append("%s%d skipped%s" % (YELLOW,skipped,RESET))
    print("  %s  |  %d total\n" % (", ".join(pts), passed+failed+errors+skipped))
    return passed, failed, errors, results

def main():
    p = argparse.ArgumentParser(description="NLQ Ground Truth Test Harness v2")
    p.add_argument("--base-url", required=True)
    p.add_argument("--tests", default=str(Path(__file__).parent/"tests.json"))
    p.add_argument("--tag"); p.add_argument("--id")
    p.add_argument("-v","--verbose", action="store_true")
    p.add_argument("--json-out")
    a = p.parse_args()

    tests = load_tests(a.tests)
    if a.id:
        tests = [t for t in tests if t["id"]==a.id]
        if not tests: print("No test: "+a.id); sys.exit(1)
    elif a.tag:
        tests = [t for t in tests if a.tag in t.get("tags",[])]
        if not tests: print("No tag: "+a.tag); sys.exit(1)

    pa,fa,er,res = run_tests(a.base_url, tests, verbose=a.verbose)
    if a.json_out:
        with open(a.json_out,"w") as f:
            json.dump({"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
                "base_url":a.base_url,"summary":{"passed":pa,"failed":fa,"errors":er},
                "results":res}, f, indent=2)
    sys.exit(1 if (fa or er) else 0)

if __name__ == "__main__":
    main()
