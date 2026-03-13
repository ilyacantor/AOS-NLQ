#!/usr/bin/env python3
"""Test script to verify NLQ live mode behavior."""

import requests
import json

BASE_URL = "https://aos-nlq.onrender.com"

def test_query(question, expected_value=None):
    """Test a single query in live mode."""
    url = f"{BASE_URL}/api/v1/query"
    payload = {"question": question, "data_mode": "live"}

    print(f"\n{'='*60}")
    print(f"Query: {question}")
    print(f"{'='*60}")

    try:
        response = requests.post(url, json=payload, timeout=60)
        data = response.json()

        print(f"Success: {data.get('success')}")
        print(f"Value: {data.get('value')}")
        print(f"Answer: {data.get('answer')}")
        print(f"Data Source: {data.get('data_source')}")
        print(f"Error: {data.get('error_message')}")

        if expected_value:
            actual = data.get('value')
            match = "✓ PASS" if actual == expected_value else f"✗ FAIL (expected {expected_value})"
            print(f"Result: {match}")

        return data
    except Exception as e:
        print(f"ERROR: {e}")
        return None

if __name__ == "__main__":
    print("Testing NLQ Live Mode\n")

    # Ground truth tests
    test_query("what is our revenue?", expected_value=397.74)
    test_query("what is our arr?", expected_value=397.74)
    test_query("what is our pipeline?", expected_value=397.74)
    test_query("what is our headcount?", expected_value=198)
