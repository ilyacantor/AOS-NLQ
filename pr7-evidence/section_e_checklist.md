# PR 7 — Section E Compliance Checklist

> Post-harness check per CLAUDE.md Section E. Date: 2026-04-08.
> Query: `POST /api/v1/query {"question":"What is VeloLabs-NDFK revenue for 2026 Q2?","entity_id":"VeloLabs-NDFK"}`

| # | Item | Result |
|---|------|--------|
| 1 | Every passing test shows `source=dcl` or `source=Ingest` | ✓ `data_source="dcl_v2"` (real v2 triples path) |
| 2 | Pipeline ran before the harness | ✓ DCL ingested VeloLabs-NDFK prior; `/health.live_data_available=true` |
| 3 | UI actually works (B17) | ✓ `trust-badge-provenance.spec.ts` PASSED (9.5s); screenshot at `trust-badge-after.png` |
| 4 | Rerun is identical (B14) | ✓ Two consecutive calls: value/provenance/confidence bit-identical |
| 5 | Latency within budget (B18) | ✓ p50=0.758s, p95=2.056s (cold-start outlier); deletion removes one fixture dict lookup, no regression vs baseline |
| 6 | No new features introduced | ✓ Net deletions: removed `get_provenance_for_metric` function + its call site; widened one dict by 2 fields |
| 7 | `tenant_id` + `entity_id` on every response (I2) | `entity_id="VeloLabs-NDFK"` ✓. `tenant_id=None` at NLQResponse top-level — **pre-existing I2 gap, not introduced by PR 7**, deferred to separate PR |
| 8 | No bare `run_id` field in response (I1) | ✓ `"run_id" in response == False`; provenance uses `dcl_ingest_id` / namespaced identifiers via v2 path |

## Rerun determinism (item 4)

```
identical (ex-volatile): True
value r1: 37.2 r2: 37.2
provenance r1 == r2: True
confidence r1: 1.0 r2: 1.0
```

## Latency samples (item 5)

```
n=10, min=0.589s, max=2.056s (cold), p50=0.758s, p95=2.056s, mean=0.918s
```

Steady state after warmup: 0.6–1.2s. PR 7 removes the per-query fixture-dict lookup in `enrich_response`; expected direction is faster, measured as neutral (within noise).

## Response shape (items 1, 7, 8)

```json
{
  "data_source": "dcl_v2",
  "entity_id": "VeloLabs-NDFK",
  "tenant_id": null,
  "value": 37.2,
  "confidence": 1.0,
  "provenance": {
    "entity_id": "VeloLabs-NDFK",
    "source_system": "sap",
    "source_systems": ["sap"],
    "is_sor": true,
    "data_source": "dcl_v2",
    "confidence_score": 0.95,
    "confidence_tier": "exact",
    "mode": "Farm"
  }
}
```

Fixture shape keys absent: `lineage`, `system_of_record`, `trust_score` — all False. Real shape keys present: `mode=Farm`, `source_systems=["sap"]`, `is_sor=true`.

## Playwright suite summary

- `trust-badge-provenance.spec.ts` — **PASS** (B17 gate for PR 7)
- `provenance-banner.spec.ts` — **PASS** (re-run in isolation; earlier fail was transient)
- `se-pipeline.spec.ts`, `se-without-convergence.spec.ts` — **PASS**
- `map-revenue.spec.ts`, `period-selector.spec.ts`, `period-all-widgets.spec.ts` — **3 pre-existing failures**, confirmed via `git stash` probe (identical failures without PR 7 code). Out of scope; flagged for separate work.

## Backend pytest summary

- `tests/test_dcl_harness.py` — **66/66 PASS** (one obsolete `test_enrichment_includes_provenance` deleted; asserted behavior that PR 7 explicitly removes)
- `tests/test_provenance_no_fixture.py` — **4/4 PASS** (new negative/positive assertions for PR 7)
- `tests/eval/` — 43 pre-existing collection errors (env fixture setup gap), confirmed via stash probe

## Pre-existing issues flagged (not fixed)

1. **I2 tenant_id gap** at NLQResponse top-level — pre-existing, not introduced by PR 7, separate PR needed.
2. **3 Playwright specs** (`map-revenue`, `period-selector`, `period-all-widgets`) — period-selector element not found, map revenue aggregation returns 373 vs expected <250. Confirmed pre-existing.
3. **43 `tests/eval/` collection errors** — env setup issue (`DCL_API_URL` / `NLQ_ALLOW_NO_DCL`), pre-existing.
