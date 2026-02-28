"""
Bridge script: Add derived metrics (DSO, DPO, Working Capital) to fact_base.json.

Reads existing AR, Revenue, AP, COGS, and balance sheet fields from each quarterly
record and computes:
  - DSO = AR / (quarterly_revenue * 4) * 365   (annualised)
  - DPO = AP / (quarterly_COGS * 4) * 365      (annualised)
  - Working Capital = current_assets - current_liabilities

This is a one-time bridge until Farm's financial_model.py generates these natively.

Usage:
    python -m scripts.add_derived_metrics          # dry-run (prints values)
    python -m scripts.add_derived_metrics --write   # writes fact_base.json
"""

import json
import sys
from pathlib import Path

FACT_BASE = Path(__file__).resolve().parent.parent / "data" / "fact_base.json"

CURRENT_ASSET_FIELDS = ["cash", "ar", "unbilled_revenue", "prepaid_expenses"]
CURRENT_LIABILITY_FIELDS = ["ap", "accrued_expenses", "deferred_revenue_current"]


def compute_derived(record: dict) -> dict:
    """Compute DSO, DPO, working_capital from a quarterly record."""
    ar = record.get("ar", 0)
    revenue = record.get("revenue", 0)
    ap = record.get("ap", 0)
    cogs = record.get("cogs", 0)

    # DSO: annualise quarterly revenue
    dso = round(ar / (revenue * 4) * 365, 1) if revenue else None
    # DPO: annualise quarterly COGS
    dpo = round(ap / (cogs * 4) * 365, 1) if cogs else None
    # Working capital: current assets - current liabilities
    ca = sum(record.get(f, 0) for f in CURRENT_ASSET_FIELDS)
    cl = sum(record.get(f, 0) for f in CURRENT_LIABILITY_FIELDS)
    wc = round(ca - cl, 2)

    return {"dso": dso, "dpo": dpo, "working_capital": wc}


def main():
    write = "--write" in sys.argv

    with open(FACT_BASE) as f:
        data = json.load(f)

    print(f"{'Period':<12} {'DSO':>6} {'DPO':>6} {'Working Capital':>16}")
    print("-" * 44)

    for record in data["quarterly"]:
        derived = compute_derived(record)
        period = record["period"]
        print(f"{period:<12} {derived['dso']:>6} {derived['dpo']:>6} {derived['working_capital']:>16.2f}")

        if write:
            record["dso"] = derived["dso"]
            record["dpo"] = derived["dpo"]
            record["working_capital"] = derived["working_capital"]

    if write:
        with open(FACT_BASE, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print(f"\nWrote {len(data['quarterly'])} records to {FACT_BASE}")
    else:
        print("\nDry run. Use --write to update fact_base.json")


if __name__ == "__main__":
    main()
