#!/usr/bin/env python3
"""
Test script to verify dashboard routing fix
"""

import asyncio
import os
import sys

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.router import classify_intent
from models.schemas import PerceptionResult

# Test queries that should route to dashboard_management
test_queries = [
    "Create a Grafana dashboard for monitoring critical errors",
    "Create a dashboard called 'Critical Errors Monitor' with panels",
    "Build a monitoring dashboard with error rate over time",
    "Create a Grafana dashboard with panels for error metrics",
    "Setup a dashboard for API monitoring",
]

print("=" * 80)
print("DASHBOARD ROUTING TEST")
print("=" * 80)

for query in test_queries:
    print(f"\nQuery: {query}")

    # Create a simple perception result
    perception = PerceptionResult(
        user_input=query,
        intent=None,
        entities=[],
        tool_hint=None,
        confidence=0.0
    )

    # Classify intent
    intent, confidence = classify_intent(perception)

    # Check result
    status = "[OK]" if intent == "dashboard_management" else "[FAIL]"
    print(f"  Intent: {intent} (confidence: {confidence:.2f}) {status}")

print("\n" + "=" * 80)
print("Test complete!")
print("=" * 80)
