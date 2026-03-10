"""
Ground Truth Reconciliation Engine.

Compares NLQ query results against Farm's ground truth manifest to verify
data integrity across the full pipeline: Farm -> DCL -> NLQ.

Reconciliation types:
  - Full: Compare all ~131 scalar metrics for a given quarter
  - Line-item: Compare a single metric across all quarters
  - Dimensional: Compare dimensional breakdowns (revenue_by_region, etc.)

The engine fetches ground truth from Farm's API and compares against
NLQ's query results. Mismatches are reported with full context -- never
silently swallowed.

Ground truth manifest structure (from Farm v2.0):
  {
    "manifest_version": "2.0",
    "run_id": "...",
    "ground_truth": {
      "2024-Q1": {
        "revenue": {"value": 25.5, "unit": "millions_usd", "primary_source": "netsuite"},
        "arr": {"value": 100.0, "unit": "millions_usd", "primary_source": "chargebee"},
        ...
        "is_forecast": false,
        "period_type": "actual"
      },
      ...
      "dimensional_truth": { ... },
      "expected_conflicts": [ ... ]
    }
  }
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Keys in each quarter dict that are metadata, not metrics
_QUARTER_META_KEYS = frozenset({"is_forecast", "period_type"})

# Keys in the ground_truth dict that are not quarter data
_GT_NON_QUARTER_KEYS = frozenset({"dimensional_truth", "expected_conflicts"})


@dataclass
class ReconciliationResult:
    """Result of a reconciliation run."""

    status: str  # "pass", "fail", "error"
    total_checks: int
    passed: int
    failed: int
    errors: int
    mismatches: List[Dict[str, Any]]
    timestamp: str
    ground_truth_version: str
    details: Optional[str] = None

    def summary(self) -> str:
        """Human-readable one-line summary."""
        return (
            f"Reconciliation {self.status.upper()}: "
            f"{self.passed}/{self.total_checks} passed, "
            f"{self.failed} failed, {self.errors} errors "
            f"(gt version: {self.ground_truth_version})"
        )


def _error_result(message: str, gt_version: str = "unknown") -> ReconciliationResult:
    """Build an error ReconciliationResult with a descriptive message."""
    return ReconciliationResult(
        status="error",
        total_checks=0,
        passed=0,
        failed=0,
        errors=1,
        mismatches=[],
        timestamp=datetime.utcnow().isoformat() + "Z",
        ground_truth_version=gt_version,
        details=message,
    )


def _extract_expected_value(metric_entry: Any) -> Optional[Any]:
    """
    Extract the numeric expected value from a ground truth metric entry.

    Ground truth entries are dicts like {"value": 25.5, "unit": "millions_usd", ...}.
    Some entries are plain scalars (e.g., is_forecast: false). Returns None for
    non-numeric entries.
    """
    if isinstance(metric_entry, dict) and "value" in metric_entry:
        val = metric_entry["value"]
        if isinstance(val, (int, float)):
            return val
        return None
    # Plain scalar (shouldn't be reached for metrics, but handle gracefully)
    if isinstance(metric_entry, (int, float)):
        return metric_entry
    return None


class ReconciliationEngine:
    """
    Compares NLQ query results against Farm's ground truth manifest.

    The engine is designed to be testable without running any servers:
    pass a ground_truth dict directly, and a query_fn that returns
    objects with a .value attribute (like SimpleMetricResult).

    Args:
        query_fn: Callable(metric_id: str, period: str) -> Optional[object].
                  The returned object must have a numeric .value attribute.
                  Return None if the metric is not available.
        ground_truth: Pre-loaded ground truth manifest dict (for testing).
        farm_url: Farm API URL to fetch ground truth at runtime.
        tolerance_pct: Percentage tolerance for numeric comparison. Default 1.0%.
    """

    def __init__(
        self,
        query_fn: Callable,
        ground_truth: Optional[Dict] = None,
        farm_url: Optional[str] = None,
        tolerance_pct: float = 1.0,
    ):
        self.query_fn = query_fn
        self._ground_truth = ground_truth
        self._farm_url = farm_url or os.environ.get("FARM_URL", "")
        if not self._farm_url:
            logger.warning(
                "FARM_URL environment variable is not set. "
                "Ground truth loading from Farm API will fail. "
                "Set FARM_URL to the Farm service URL (e.g. https://farmv2.onrender.com)."
            )
        self.tolerance_pct = tolerance_pct

    # ── Internal helpers ────────────────────────────────────────────────────

    def _resolve_gt_data(self, gt: Dict, entity_id: Optional[str] = None) -> Dict:
        """
        Extract the quarter-level ground truth dict from a manifest.

        Handles three manifest formats:
        - v2.0: top-level "ground_truth" key → return it directly
        - v3.0 (multi-entity): "ground_truth_by_entity" → select by entity_id
        - Legacy: no wrapper → return gt as-is

        Args:
            entity_id: For v3.0 manifests, select this entity's ground truth.
                       If None, falls back to first entity (backward compat).
        """
        # v2.0 single-entity path
        if "ground_truth" in gt:
            return gt["ground_truth"]

        # v3.0 multi-entity path
        if "ground_truth_by_entity" in gt:
            by_entity = gt["ground_truth_by_entity"]
            if not by_entity:
                logger.error("ground_truth_by_entity is empty in v3.0 manifest")
                return gt

            if entity_id and entity_id in by_entity:
                logger.info(
                    f"Using ground truth for entity '{entity_id}' from v3.0 manifest"
                )
                return by_entity[entity_id]
            elif entity_id:
                available = list(by_entity.keys())
                logger.error(
                    f"Entity '{entity_id}' not found in v3.0 manifest. "
                    f"Available entities: {available}"
                )
                return gt

            # No entity_id specified — fall back to first entity
            first_entity = next(iter(by_entity))
            logger.info(
                f"No entity_id specified; using first entity '{first_entity}' "
                f"from v3.0 manifest"
            )
            return by_entity[first_entity]

        # Legacy fallback — gt is the ground truth dict itself
        return gt

    # ── Public API ────────────────────────────────────────────────────────────

    def reconcile_quarter(self, period: str, entity_id: Optional[str] = None) -> ReconciliationResult:
        """
        Compare all scalar metrics for a single quarter against ground truth.

        Iterates every numeric metric in the ground truth for the given period
        and compares against the NLQ query result. Non-numeric entries (dicts,
        lists, booleans, strings) are skipped -- dimensional breakdowns are
        handled by reconcile_dimensional().
        """
        gt = self._get_ground_truth()
        if gt is None:
            return _error_result(
                "Ground truth unavailable: could not load from pre-loaded data, "
                f"Farm API at {self._farm_url}, or local file fallback."
            )

        gt_data = self._resolve_gt_data(gt, entity_id=entity_id)
        quarter_data = gt_data.get(period)
        if quarter_data is None:
            available = [
                k for k in gt_data
                if k not in _GT_NON_QUARTER_KEYS
            ]
            return _error_result(
                f"Period '{period}' not found in ground truth. "
                f"Available periods: {available}"
            )

        mismatches: List[Dict[str, Any]] = []
        passed = 0
        failed = 0
        errors = 0

        for key, entry in quarter_data.items():
            if key in _QUARTER_META_KEYS:
                continue

            expected = _extract_expected_value(entry)
            if expected is None:
                # Not a numeric scalar -- skip (dimensional or non-numeric)
                continue

            try:
                result = self.query_fn(key, period)
            except Exception as exc:
                errors += 1
                mismatches.append({
                    "metric": key,
                    "period": period,
                    "expected": expected,
                    "actual": None,
                    "delta": None,
                    "pct_delta": None,
                    "status": "error",
                    "error": (
                        f"query_fn raised {type(exc).__name__} for "
                        f"metric='{key}', period='{period}': {exc}"
                    ),
                })
                logger.error(
                    "Reconciliation query error for metric='%s', period='%s': %s",
                    key, period, exc,
                )
                continue

            if result is None:
                errors += 1
                mismatches.append({
                    "metric": key,
                    "period": period,
                    "expected": expected,
                    "actual": None,
                    "delta": None,
                    "pct_delta": None,
                    "status": "missing",
                })
                continue

            actual = result.value
            if not isinstance(actual, (int, float)):
                errors += 1
                mismatches.append({
                    "metric": key,
                    "period": period,
                    "expected": expected,
                    "actual": actual,
                    "delta": None,
                    "pct_delta": None,
                    "status": "error",
                    "error": (
                        f"query_fn returned non-numeric value "
                        f"(type={type(actual).__name__}) for metric='{key}'"
                    ),
                })
                continue

            delta = abs(actual - expected)
            if expected != 0:
                pct_delta = delta / abs(expected) * 100
            else:
                pct_delta = 0.0 if delta == 0 else 100.0

            if pct_delta <= self.tolerance_pct:
                passed += 1
            else:
                failed += 1
                mismatches.append({
                    "metric": key,
                    "period": period,
                    "expected": expected,
                    "actual": actual,
                    "delta": round(delta, 4),
                    "pct_delta": round(pct_delta, 2),
                    "status": "mismatch",
                })

        total = passed + failed + errors
        gt_version = gt.get("manifest_version", "unknown")

        return ReconciliationResult(
            status="pass" if (failed == 0 and errors == 0) else "fail",
            total_checks=total,
            passed=passed,
            failed=failed,
            errors=errors,
            mismatches=mismatches,
            timestamp=datetime.utcnow().isoformat() + "Z",
            ground_truth_version=gt_version,
        )

    def reconcile_line_item(self, metric: str, entity_id: Optional[str] = None) -> ReconciliationResult:
        """
        Compare a single metric across all available quarters.

        Useful for validating that a specific metric (e.g., "revenue") is
        correctly reported in every quarter.
        """
        gt = self._get_ground_truth()
        if gt is None:
            return _error_result(
                "Ground truth unavailable: could not load from pre-loaded data, "
                f"Farm API at {self._farm_url}, or local file fallback."
            )

        gt_data = self._resolve_gt_data(gt, entity_id=entity_id)
        quarters = [
            k for k in gt_data
            if k not in _GT_NON_QUARTER_KEYS
        ]

        if not quarters:
            return _error_result("No quarters found in ground truth data.")

        mismatches: List[Dict[str, Any]] = []
        passed = 0
        failed = 0
        errors = 0

        for period in sorted(quarters):
            quarter_data = gt_data[period]
            entry = quarter_data.get(metric)
            if entry is None:
                errors += 1
                mismatches.append({
                    "metric": metric,
                    "period": period,
                    "expected": None,
                    "actual": None,
                    "delta": None,
                    "pct_delta": None,
                    "status": "error",
                    "error": f"Metric '{metric}' not found in ground truth for period '{period}'",
                })
                continue

            expected = _extract_expected_value(entry)
            if expected is None:
                # Not numeric -- skip this period for this metric
                continue

            try:
                result = self.query_fn(metric, period)
            except Exception as exc:
                errors += 1
                mismatches.append({
                    "metric": metric,
                    "period": period,
                    "expected": expected,
                    "actual": None,
                    "delta": None,
                    "pct_delta": None,
                    "status": "error",
                    "error": (
                        f"query_fn raised {type(exc).__name__} for "
                        f"metric='{metric}', period='{period}': {exc}"
                    ),
                })
                logger.error(
                    "Reconciliation query error for metric='%s', period='%s': %s",
                    metric, period, exc,
                )
                continue

            if result is None:
                errors += 1
                mismatches.append({
                    "metric": metric,
                    "period": period,
                    "expected": expected,
                    "actual": None,
                    "delta": None,
                    "pct_delta": None,
                    "status": "missing",
                })
                continue

            actual = result.value
            if not isinstance(actual, (int, float)):
                errors += 1
                mismatches.append({
                    "metric": metric,
                    "period": period,
                    "expected": expected,
                    "actual": actual,
                    "delta": None,
                    "pct_delta": None,
                    "status": "error",
                    "error": (
                        f"query_fn returned non-numeric value "
                        f"(type={type(actual).__name__}) for metric='{metric}'"
                    ),
                })
                continue

            delta = abs(actual - expected)
            if expected != 0:
                pct_delta = delta / abs(expected) * 100
            else:
                pct_delta = 0.0 if delta == 0 else 100.0

            if pct_delta <= self.tolerance_pct:
                passed += 1
            else:
                failed += 1
                mismatches.append({
                    "metric": metric,
                    "period": period,
                    "expected": expected,
                    "actual": actual,
                    "delta": round(delta, 4),
                    "pct_delta": round(pct_delta, 2),
                    "status": "mismatch",
                })

        total = passed + failed + errors
        gt_version = gt.get("manifest_version", "unknown")

        return ReconciliationResult(
            status="pass" if (failed == 0 and errors == 0) else "fail",
            total_checks=total,
            passed=passed,
            failed=failed,
            errors=errors,
            mismatches=mismatches,
            timestamp=datetime.utcnow().isoformat() + "Z",
            ground_truth_version=gt_version,
        )

    def reconcile_dimensional(
        self,
        period: str,
        breakdown: str,
        entity_id: Optional[str] = None,
    ) -> ReconciliationResult:
        """
        Compare a dimensional breakdown (e.g., revenue_by_region) against ground truth.

        The query_fn is called with metric_id="{breakdown}.{dimension_key}" and the
        given period. For example, for breakdown="revenue_by_region" and key="AMER",
        calls query_fn("revenue_by_region.AMER", period).
        """
        gt = self._get_ground_truth()
        if gt is None:
            return _error_result(
                "Ground truth unavailable: could not load from pre-loaded data, "
                f"Farm API at {self._farm_url}, or local file fallback."
            )

        gt_data = self._resolve_gt_data(gt, entity_id=entity_id)
        dim_truth = gt_data.get("dimensional_truth")
        if dim_truth is None:
            return _error_result(
                "No 'dimensional_truth' block found in ground truth manifest."
            )

        breakdown_data = dim_truth.get(breakdown)
        if breakdown_data is None:
            available = [
                k for k in dim_truth
                if not k.startswith("_") and k != "source"
            ]
            return _error_result(
                f"Breakdown '{breakdown}' not found in dimensional_truth. "
                f"Available breakdowns: {available}"
            )

        period_data = breakdown_data.get(period)
        if period_data is None:
            available_periods = [
                k for k in breakdown_data
                if k != "source" and not k.startswith("_")
            ]
            return _error_result(
                f"Period '{period}' not found in dimensional breakdown '{breakdown}'. "
                f"Available periods: {available_periods}"
            )

        if not isinstance(period_data, dict):
            return _error_result(
                f"Dimensional data for '{breakdown}' / '{period}' is not a dict "
                f"(got {type(period_data).__name__}). Cannot reconcile."
            )

        mismatches: List[Dict[str, Any]] = []
        passed = 0
        failed = 0
        errors = 0

        # Collect all (metric_id, expected_value) pairs to compare.
        # Dimensional entries can be flat scalars (revenue_by_region: {"AMER": 12.5})
        # or nested dicts (attrition_by_department: {"Engineering": {"attrition_count": 2}}).
        checks: List[tuple] = []  # (metric_id, expected_value)
        for dim_key, expected in period_data.items():
            if isinstance(expected, dict):
                for sub_key, sub_expected in expected.items():
                    if isinstance(sub_expected, (int, float)):
                        checks.append((f"{breakdown}.{dim_key}.{sub_key}", sub_expected))
            elif isinstance(expected, (int, float)):
                checks.append((f"{breakdown}.{dim_key}", expected))

        for metric_id, expected_val in checks:
            try:
                result = self.query_fn(metric_id, period)
            except Exception as exc:
                errors += 1
                mismatches.append({
                    "metric": metric_id,
                    "period": period,
                    "expected": expected_val,
                    "actual": None,
                    "delta": None,
                    "pct_delta": None,
                    "status": "error",
                    "error": (
                        f"query_fn raised {type(exc).__name__} for "
                        f"metric='{metric_id}', period='{period}': {exc}"
                    ),
                })
                logger.error(
                    "Reconciliation query error for metric='%s', period='%s': %s",
                    metric_id, period, exc,
                )
                continue

            if result is None:
                errors += 1
                mismatches.append({
                    "metric": metric_id,
                    "period": period,
                    "expected": expected_val,
                    "actual": None,
                    "delta": None,
                    "pct_delta": None,
                    "status": "missing",
                })
                continue

            actual = result.value
            if not isinstance(actual, (int, float)):
                errors += 1
                mismatches.append({
                    "metric": metric_id,
                    "period": period,
                    "expected": expected_val,
                    "actual": actual,
                    "delta": None,
                    "pct_delta": None,
                    "status": "error",
                    "error": (
                        f"query_fn returned non-numeric value "
                        f"(type={type(actual).__name__}) for metric='{metric_id}'"
                    ),
                })
                continue

            delta = abs(actual - expected_val)
            if expected_val != 0:
                pct_delta = delta / abs(expected_val) * 100
            else:
                pct_delta = 0.0 if delta == 0 else 100.0

            if pct_delta <= self.tolerance_pct:
                passed += 1
            else:
                failed += 1
                mismatches.append({
                    "metric": metric_id,
                    "period": period,
                    "expected": expected_val,
                    "actual": actual,
                    "delta": round(delta, 4),
                    "pct_delta": round(pct_delta, 2),
                    "status": "mismatch",
                })

        total = passed + failed + errors
        gt_version = gt.get("manifest_version", "unknown")

        return ReconciliationResult(
            status="pass" if (failed == 0 and errors == 0) else "fail",
            total_checks=total,
            passed=passed,
            failed=failed,
            errors=errors,
            mismatches=mismatches,
            timestamp=datetime.utcnow().isoformat() + "Z",
            ground_truth_version=gt_version,
        )

    def reconcile_full(self, entity_id: Optional[str] = None) -> ReconciliationResult:
        """
        Full reconciliation across all quarters.

        Runs reconcile_quarter() for every quarter found in the ground truth
        and aggregates results into a single ReconciliationResult.
        """
        gt = self._get_ground_truth()
        if gt is None:
            return _error_result(
                "Ground truth unavailable: could not load from pre-loaded data, "
                f"Farm API at {self._farm_url}, or local file fallback."
            )

        gt_data = self._resolve_gt_data(gt, entity_id=entity_id)
        quarters = sorted([
            k for k in gt_data
            if k not in _GT_NON_QUARTER_KEYS
        ])

        if not quarters:
            return _error_result("No quarters found in ground truth data.")

        all_mismatches: List[Dict[str, Any]] = []
        total_passed = 0
        total_failed = 0
        total_errors = 0

        for period in quarters:
            qr = self.reconcile_quarter(period, entity_id=entity_id)
            total_passed += qr.passed
            total_failed += qr.failed
            total_errors += qr.errors
            all_mismatches.extend(qr.mismatches)

        total = total_passed + total_failed + total_errors
        gt_version = gt.get("manifest_version", "unknown")

        return ReconciliationResult(
            status="pass" if (total_failed == 0 and total_errors == 0) else "fail",
            total_checks=total,
            passed=total_passed,
            failed=total_failed,
            errors=total_errors,
            mismatches=all_mismatches,
            timestamp=datetime.utcnow().isoformat() + "Z",
            ground_truth_version=gt_version,
        )

    # ── Ground truth loading ──────────────────────────────────────────────────

    def _get_ground_truth(self) -> Optional[Dict]:
        """
        Get ground truth manifest.

        Resolution order:
        1. Pre-loaded dict (passed to constructor -- primary for testing)
        2. Farm API at self._farm_url
        3. Local file at data/ground_truth.json

        Every failure is logged with full context. No silent fallbacks.
        """
        if self._ground_truth is not None:
            return self._ground_truth

        # Try Farm API
        gt = self._fetch_from_farm_api()
        if gt is not None:
            self._ground_truth = gt
            return gt

        # Try local file
        gt = self._load_from_local_file()
        if gt is not None:
            logger.info(
                "Loaded ground truth from local file (Farm API was unavailable)."
            )
            self._ground_truth = gt
            return gt

        logger.error(
            "Failed to load ground truth from all sources: "
            "no pre-loaded data, Farm API at %s failed, and no local file found.",
            self._farm_url,
        )
        return None

    def _fetch_from_farm_api(self) -> Optional[Dict]:
        """Fetch ground truth from Farm's API. Returns None on failure with logging.

        Farm's ground truth requires a run_id. Resolution:
        1. Fetch the runs list from /api/business-data/runs
        2. Use the latest run_id
        3. Fetch ground truth from /api/business-data/ground-truth/{run_id}
        """
        try:
            import httpx
        except ImportError:
            logger.error(
                "httpx not installed -- cannot fetch ground truth from Farm API at %s. "
                "Install httpx or provide ground_truth dict directly.",
                self._farm_url,
            )
            return None

        # Step 1: Get the latest run_id
        runs_url = f"{self._farm_url}/api/business-data/runs"
        try:
            runs_response = httpx.get(runs_url, timeout=15)
            if runs_response.status_code != 200:
                logger.error(
                    "Farm runs API returned HTTP %d at %s: %s",
                    runs_response.status_code, runs_url, runs_response.text[:500],
                )
                return None

            runs_data = runs_response.json()
            runs = runs_data.get("runs", [])
            if not runs:
                logger.error(
                    "Farm runs API at %s returned no runs. Cannot fetch ground truth.",
                    runs_url,
                )
                return None

            # Use the first (most recent) run
            run_id = runs[0].get("run_id")
            if not run_id:
                logger.error(
                    "Farm runs API at %s returned a run with no run_id: %s",
                    runs_url, runs[0],
                )
                return None

        except Exception as exc:
            logger.error(
                "Failed to fetch Farm runs from %s: %s: %s",
                runs_url, type(exc).__name__, exc,
            )
            return None

        # Step 2: Fetch ground truth for this run
        gt_url = f"{self._farm_url}/api/business-data/ground-truth/{run_id}"
        try:
            response = httpx.get(gt_url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "Loaded ground truth from Farm API at %s (version: %s, run: %s)",
                    gt_url, data.get("manifest_version", "unknown"), run_id,
                )
                return data
            logger.error(
                "Farm ground truth API returned HTTP %d at %s: %s",
                response.status_code, gt_url, response.text[:500],
            )
        except Exception as exc:
            logger.error(
                "Failed to fetch ground truth from Farm API at %s: %s: %s",
                gt_url, type(exc).__name__, exc,
            )
        return None

    def _load_from_local_file(self) -> Optional[Dict]:
        """Load ground truth from local data/ground_truth.json file."""
        # Try path relative to this file: src/nlq/services/ -> data/
        gt_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "ground_truth.json"
        try:
            if gt_path.exists():
                with open(gt_path) as f:
                    data = json.load(f)
                logger.info(
                    "Loaded ground truth from local file %s (version: %s)",
                    gt_path,
                    data.get("manifest_version", "unknown"),
                )
                return data
            logger.warning(
                "Local ground truth file not found at %s",
                gt_path,
            )
        except json.JSONDecodeError as exc:
            logger.error(
                "Local ground truth file at %s contains invalid JSON: %s",
                gt_path,
                exc,
            )
        except Exception as exc:
            logger.error(
                "Failed to read local ground truth file at %s: %s: %s",
                gt_path,
                type(exc).__name__,
                exc,
            )
        return None

