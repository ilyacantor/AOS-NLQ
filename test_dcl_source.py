#!/usr/bin/env python3
"""Diagnostic script to trace data_source propagation from DCL."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from nlq.services.dcl_semantic_client import get_semantic_client, set_data_mode

def test_dcl_query_source():
    """Test what data_source DCL returns."""
    print("Testing DCL query with data_mode='live'\n")

    # Set data mode context
    set_data_mode("live")

    client = get_semantic_client()
    print(f"DCL URL: {client.dcl_url}")
    print(f"Catalog source: {client.catalog_source}\n")

    # Query revenue
    try:
        result = client.query(
            metric="revenue",
            time_range={"period": "2026-Q1", "granularity": "quarterly"},
            data_mode="live"  # Explicit pass
        )

        print("Query Result:")
        print(f"  status: {result.get('status')}")
        print(f"  source: {result.get('source')}")
        print(f"  data_source: {result.get('data_source')}")
        print(f"  data_source_reason: {result.get('data_source_reason')}")
        print(f"  data: {result.get('data', [])[:2]}")  # First 2 data points

        # Check metadata
        metadata = result.get('metadata', {})
        print(f"\nMetadata:")
        print(f"  source: {metadata.get('source')}")
        print(f"  mode: {metadata.get('mode')}")
        print(f"  quality_score: {metadata.get('quality_score')}")

    except RuntimeError as e:
        print(f"RuntimeError (expected for live mode with demo data): {e}")
    except Exception as e:
        print(f"Unexpected error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_dcl_query_source()
