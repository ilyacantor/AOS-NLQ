"""
Evaluation suite for NLQ-DCL integration.

These tests validate the REAL integration between NLQ and DCL.
No mocking allowed - tests must hit real endpoints or fail loudly.

Run with:
    python -m pytest tests/eval/ -v --tb=short

Or with explicit DCL URL:
    DCL_API_URL=https://your-dcl.repl.co python -m pytest tests/eval/ -v
"""
