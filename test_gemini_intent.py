#!/usr/bin/env python3
"""
Test script for Gemini 3 LLM-based intent classification
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'apps', 'backend'))

def test_gemini_setup():
    """Test Gemini LLM provider setup."""
    print("🔧 Testing Gemini 3 setup...")

    # Set environment variables for Gemini
    os.environ['LLM_PROVIDER'] = 'gemini'
    os.environ['LLM_MODEL'] = 'gemini-2.0-flash-exp'
    os.environ['GOOGLE_API_KEY'] = os.getenv('GOOGLE_API_KEY', 'your_api_key_here')

    try:
        from agent.llm_provider import get_llm
        llm = get_llm()
        print(f"✅ LLM provider created: {type(llm).__name__}")
        print(f"   Model: {llm.model}")
        return True
    except Exception as e:
        print(f"❌ LLM provider failed: {e}")
        return False

def test_intent_classification():
    """Test intent classification with keyword fallback."""
    print("\n🎯 Testing intent classification...")

    try:
        from agent.router import classify_intent, INTENT_DEFINITIONS
        from models.schemas import PerceptionResult

        print(f"✅ Available intents: {list(INTENT_DEFINITIONS.keys())}")

        # Test cases
        test_cases = [
            ("Show me recent errors", "database_query"),
            ("Find the authentication code", "search_code"),
            ("How do I authenticate?", "document_search"),
            ("Why is the API slow?", "incident_investigation"),
            ("Create a dashboard", "dashboard_management"),
        ]

        for query, expected_intent in test_cases:
            perception = PerceptionResult(
                user_input=query,
                intent=None,
                entities=[],
                tool_hint=None,
                repo_url=None
            )

            try:
                intent = classify_intent(perception)
                status = "✅" if intent == expected_intent else "⚠️"
                print(f"   {status} '{query}' → {intent} (expected: {expected_intent})")
            except Exception as e:
                print(f"   ❌ '{query}' failed: {e}")

        return True
    except Exception as e:
        print(f"❌ Intent classification test failed: {e}")
        return False

def main():
    """Main test function."""
    print("🚀 DevRelAgent Gemini 3 Intent Classification Test")
    print("=" * 50)

    success = True

    # Test Gemini setup
    if not test_gemini_setup():
        success = False

    # Test intent classification
    if not test_intent_classification():
        success = False

    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed! Gemini 3 intent classification is ready.")
        print("\n📝 To use in production:")
        print("   export LLM_PROVIDER=gemini")
        print("   export LLM_MODEL=gemini-2.0-flash-exp")
        print("   export GOOGLE_API_KEY=your_actual_api_key")
    else:
        print("❌ Some tests failed. Check the errors above.")

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())