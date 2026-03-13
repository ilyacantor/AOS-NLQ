"""
Period Comparison Engine — Act/CF/PY logic for the Standard Reporting Package.

Determines which periods to compare based on report variant and wall clock date.

Period Types:
  - Actuals (Act): Any quarter whose end date is BEFORE the wall clock date.
  - Current Forecast (CF): Any quarter whose end date is ON OR AFTER the wall clock date.
    CF only exists for the current wall clock year.
  - Prior Year (PY): Always Act data from the preceding year.

The period tagging is dynamic — it checks the wall clock date at query time.
Farm generates both actual and forecast data; this module classifies them.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class PeriodInfo:
    """Metadata for a single period."""
    label: str          # e.g., "2025-Q3"
    year: int
    quarter: int
    period_type: str    # "actual" or "forecast"
    quarter_end: date   # last day of the quarter

    @property
    def is_actual(self) -> bool:
        return self.period_type == "actual"

    @property
    def is_forecast(self) -> bool:
        return self.period_type == "forecast"


@dataclass
class PeriodComparison:
    """Result of period comparison engine — what periods to show and how."""
    variant: str                        # e.g., "full_year_act_vs_py"
    left_label: str                     # column header for left column
    right_label: str                    # column header for right column
    left_periods: List[PeriodInfo]      # periods that make up the left column
    right_periods: List[PeriodInfo]     # periods that make up the right column
    wall_clock_date: date
    selected_quarter: Optional[str] = None  # for quarterly variants


# ═══════════════════════════════════════════════════════════════════════════════
# Quarter utilities
# ═══════════════════════════════════════════════════════════════════════════════

def quarter_end_date(year: int, quarter: int) -> date:
    """Return the last day of a quarter."""
    month_ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    m, d = month_ends[quarter]
    return date(year, m, d)


def quarter_label(year: int, quarter: int) -> str:
    return f"{year}-Q{quarter}"


def parse_quarter_label(label: str) -> Tuple[int, int]:
    """Parse '2025-Q3' into (2025, 3)."""
    parts = label.split("-Q")
    return int(parts[0]), int(parts[1])


def classify_period(year: int, quarter: int, wall_clock: date) -> str:
    """Classify a quarter as 'actual' or 'forecast' based on wall clock date.

    A quarter is actual if its end date is BEFORE the wall clock date.
    Otherwise it's forecast. Prior years are always actual.
    """
    qend = quarter_end_date(year, quarter)
    if qend < wall_clock:
        return "actual"
    return "forecast"


def get_all_periods(wall_clock: date) -> List[PeriodInfo]:
    """Get all 12 quarters (2024-Q1 through 2026-Q4) with period type classification."""
    periods = []
    for year in range(2024, 2027):
        for q in range(1, 5):
            qend = quarter_end_date(year, q)
            ptype = classify_period(year, q, wall_clock)
            periods.append(PeriodInfo(
                label=quarter_label(year, q),
                year=year,
                quarter=q,
                period_type=ptype,
                quarter_end=qend,
            ))
    return periods


# ═══════════════════════════════════════════════════════════════════════════════
# Comparison engine
# ═══════════════════════════════════════════════════════════════════════════════

def compute_comparison(
    variant: str,
    wall_clock: Optional[date] = None,
    selected_quarter: Optional[str] = None,
) -> PeriodComparison:
    """Compute period comparison based on variant and wall clock date.

    Args:
        variant: One of:
            - "full_year_act_vs_py": Last completed full year vs preceding year
            - "quarterly_act_vs_py": Selected quarter vs same quarter prior year
            - "full_year_cf_vs_py_act": Current year (Act+CF blend) vs prior year
            - "quarterly_cf_vs_py": Selected quarter CF vs same quarter prior year
        wall_clock: Current date (defaults to today)
        selected_quarter: Required for quarterly variants, e.g. "2025-Q3"

    Returns:
        PeriodComparison with left/right periods and labels.

    Raises:
        ValueError: Invalid variant or missing required parameters.
    """
    if wall_clock is None:
        wall_clock = date.today()

    all_periods = get_all_periods(wall_clock)
    current_year = wall_clock.year

    if variant == "full_year_act_vs_py":
        return _full_year_act_vs_py(all_periods, current_year, wall_clock)
    elif variant == "quarterly_act_vs_py":
        if not selected_quarter:
            raise ValueError(
                "quarterly_act_vs_py requires selected_quarter parameter "
                "(e.g., '2025-Q3')"
            )
        return _quarterly_act_vs_py(all_periods, selected_quarter, wall_clock)
    elif variant == "full_year_cf_vs_py_act":
        return _full_year_cf_vs_py_act(all_periods, current_year, wall_clock)
    elif variant == "quarterly_cf_vs_py":
        if not selected_quarter:
            raise ValueError(
                "quarterly_cf_vs_py requires selected_quarter parameter "
                "(e.g., '2026-Q2')"
            )
        return _quarterly_cf_vs_py(all_periods, selected_quarter, wall_clock)
    else:
        raise ValueError(
            f"Unknown report variant '{variant}'. Valid variants: "
            "full_year_act_vs_py, quarterly_act_vs_py, "
            "full_year_cf_vs_py_act, quarterly_cf_vs_py"
        )


def _full_year_act_vs_py(
    periods: List[PeriodInfo], current_year: int, wall_clock: date
) -> PeriodComparison:
    """Full Year Act vs PY: last completed full year vs preceding year."""
    # Last completed full year = the most recent year where ALL quarters are actual
    act_year = current_year - 1
    # Check if all quarters of current year are actual
    current_year_periods = [p for p in periods if p.year == current_year]
    if current_year_periods and all(p.is_actual for p in current_year_periods):
        act_year = current_year

    left = [p for p in periods if p.year == act_year]
    right = [p for p in periods if p.year == act_year - 1]

    if not left:
        raise ValueError(f"No data available for year {act_year}")

    return PeriodComparison(
        variant="full_year_act_vs_py",
        left_label=f"FY {act_year} Actual",
        right_label=f"FY {act_year - 1} Actual",
        left_periods=left,
        right_periods=right,
        wall_clock_date=wall_clock,
    )


def _quarterly_act_vs_py(
    periods: List[PeriodInfo], selected_quarter: str, wall_clock: date
) -> PeriodComparison:
    """Quarterly Act vs PY: selected quarter vs same quarter prior year."""
    year, q = parse_quarter_label(selected_quarter)

    left_period = next(
        (p for p in periods if p.year == year and p.quarter == q), None
    )
    if left_period is None:
        raise ValueError(f"Quarter {selected_quarter} not found in available data")
    if not left_period.is_actual:
        raise ValueError(
            f"Quarter {selected_quarter} is forecast, not actual. "
            "Use quarterly_cf_vs_py for forecast quarters."
        )

    right_period = next(
        (p for p in periods if p.year == year - 1 and p.quarter == q), None
    )

    return PeriodComparison(
        variant="quarterly_act_vs_py",
        left_label=f"{selected_quarter} Actual",
        right_label=f"{year - 1}-Q{q} Actual",
        left_periods=[left_period],
        right_periods=[right_period] if right_period else [],
        wall_clock_date=wall_clock,
        selected_quarter=selected_quarter,
    )


def _full_year_cf_vs_py_act(
    periods: List[PeriodInfo], current_year: int, wall_clock: date
) -> PeriodComparison:
    """Full Year CF vs PY Act: current year (Act+CF blend) vs prior year Act.

    Left column is a blend: Act for closed quarters + CF for open/future quarters
    in the current wall clock year. Right column is all Act from prior year.
    """
    left = [p for p in periods if p.year == current_year]
    right = [p for p in periods if p.year == current_year - 1]

    if not left:
        raise ValueError(
            f"No data available for current year {current_year}. "
            "Full Year CF vs PY Act is only available for the current wall clock year."
        )

    # Verify there's at least one forecast quarter (otherwise this is just Act vs PY)
    has_forecast = any(p.is_forecast for p in left)
    if not has_forecast:
        # All quarters of current year are actual — redirect to full_year_act_vs_py
        return _full_year_act_vs_py(periods, current_year, wall_clock)

    # Build label indicating blend
    act_qs = [p.label for p in left if p.is_actual]
    cf_qs = [p.label for p in left if p.is_forecast]
    blend_note = f"Act: {', '.join(act_qs)}" if act_qs else ""
    blend_note += f" | CF: {', '.join(cf_qs)}" if cf_qs else ""

    return PeriodComparison(
        variant="full_year_cf_vs_py_act",
        left_label=f"FY {current_year} (Act+CF)",
        right_label=f"FY {current_year - 1} Actual",
        left_periods=left,
        right_periods=right,
        wall_clock_date=wall_clock,
    )


def _quarterly_cf_vs_py(
    periods: List[PeriodInfo], selected_quarter: str, wall_clock: date
) -> PeriodComparison:
    """Quarterly CF vs PY: selected quarter (CF or Act) vs same quarter prior year."""
    year, q = parse_quarter_label(selected_quarter)
    current_year = wall_clock.year

    if year != current_year:
        raise ValueError(
            f"Quarter {selected_quarter} is not in the current wall clock year "
            f"({current_year}). Quarterly CF vs PY is only available for "
            "current year quarters."
        )

    left_period = next(
        (p for p in periods if p.year == year and p.quarter == q), None
    )
    if left_period is None:
        raise ValueError(f"Quarter {selected_quarter} not found in available data")

    right_period = next(
        (p for p in periods if p.year == year - 1 and p.quarter == q), None
    )

    type_label = "Actual" if left_period.is_actual else "Forecast"

    return PeriodComparison(
        variant="quarterly_cf_vs_py",
        left_label=f"{selected_quarter} {type_label}",
        right_label=f"{year - 1}-Q{q} Actual",
        left_periods=[left_period],
        right_periods=[right_period] if right_period else [],
        wall_clock_date=wall_clock,
        selected_quarter=selected_quarter,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Balance Sheet variant validation
# ═══════════════════════════════════════════════════════════════════════════════

VALID_BS_VARIANTS = {"full_year_act_vs_py", "quarterly_act_vs_py"}

def validate_statement_variant(statement: str, variant: str) -> Optional[str]:
    """Validate that a statement type supports the requested variant.

    Returns None if valid, or an error message if not.
    """
    if statement == "balance_sheet" and variant not in VALID_BS_VARIANTS:
        return (
            f"Balance sheet does not support variant '{variant}'. "
            "Balance sheet is point-in-time actuals only — "
            "no forecast variants are available. "
            f"Valid BS variants: {', '.join(sorted(VALID_BS_VARIANTS))}"
        )
    return None
