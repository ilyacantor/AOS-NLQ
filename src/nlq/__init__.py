"""
AOS-NLQ: Natural Language Query Engine for Enterprise Data

This module provides the core NLQ engine that:
1. Accepts natural language questions about financial/enterprise data
2. Parses intent, entities, and time references using Claude API
3. Resolves relative dates ("last quarter") to absolute dates
4. Generates structured queries against a financial fact base
5. Returns answers with bounded confidence scores [0.0, 1.0]

Part of the AutonomOS platform. Sits on top of DCL (Data Unification Engine).
"""

__version__ = "0.1.0"
__author__ = "AutonomOS"
