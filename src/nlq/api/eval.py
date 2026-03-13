"""
Evaluation endpoint — runs the pytest eval suite on demand.

Extracted from routes.py (C1).
"""

import logging
import re
import subprocess
import time
from pathlib import Path
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class EvalResult(BaseModel):
    """Result of running evaluation tests."""
    status: str  # "passed", "failed", "error"
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_seconds: float
    summary: str
    failures: List[str] = []


@router.post("/eval/run", response_model=EvalResult)
async def run_evaluation():
    """
    Run the NLQ-DCL evaluation test suite.

    Executes pytest on tests/eval/ and returns results.
    Tests require DCL to be available - no mocking.
    """
    start_time = time.time()

    try:
        # Run pytest on the eval suite
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/eval/", "-v", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
            cwd=str(Path(__file__).parent.parent.parent.parent)
        )

        duration = time.time() - start_time
        output = result.stdout + result.stderr

        # Parse pytest output
        lines = output.strip().split('\n')

        # Extract counts from pytest summary line
        total = passed = failed = errors = skipped = 0
        summary_line = ""
        failures = []

        for line in lines:
            if " passed" in line or " failed" in line or " error" in line:
                summary_line = line
                if match := re.search(r'(\d+) passed', line):
                    passed = int(match.group(1))
                if match := re.search(r'(\d+) failed', line):
                    failed = int(match.group(1))
                if match := re.search(r'(\d+) error', line):
                    errors = int(match.group(1))
                if match := re.search(r'(\d+) skipped', line):
                    skipped = int(match.group(1))
            if "FAILED" in line or "ERROR" in line:
                failures.append(line.strip())

        total = passed + failed + errors + skipped
        status = "passed" if failed == 0 and errors == 0 else "failed"

        return EvalResult(
            status=status,
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_seconds=round(duration, 2),
            summary=summary_line or f"{passed} passed, {failed} failed",
            failures=failures[:20],
        )

    except subprocess.TimeoutExpired:
        return EvalResult(
            status="error",
            total=0,
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            duration_seconds=120.0,
            summary="Test suite timed out after 120 seconds",
            failures=["Timeout: tests took too long to complete"],
        )
    except (OSError, RuntimeError, ValueError) as e:
        return EvalResult(
            status="error",
            total=0,
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            duration_seconds=time.time() - start_time,
            summary=f"Error running tests: {str(e)}",
            failures=[str(e)],
        )
