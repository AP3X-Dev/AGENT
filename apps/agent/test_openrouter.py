#!/usr/bin/env python3
"""Test script for OpenRouter integration.

This script tests the OpenRouter model provider configuration.
Set OPENROUTER_API_KEY environment variable before running.

Usage:
    export OPENROUTER_API_KEY=your_key_here
    export AG3NT_MODEL_PROVIDER=openrouter
    export AG3NT_MODEL_NAME=moonshotai/kimi-k2-thinking
    python test_openrouter.py
"""

import os
import sys


def test_openrouter_config():
    """Test OpenRouter configuration."""
    print("Testing OpenRouter configuration...")
    print(f"Provider: {os.environ.get('AG3NT_MODEL_PROVIDER', 'not set')}")
    print(f"Model: {os.environ.get('AG3NT_MODEL_NAME', 'not set')}")
    print(f"API Key: {'set' if os.environ.get('OPENROUTER_API_KEY') else 'NOT SET'}")
    print()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("❌ OPENROUTER_API_KEY not set!")
        print("Get your key from: https://openrouter.ai/keys")
        return False

    return True


def test_model_creation():
    """Test creating the model instance."""
    print("Testing model creation...")

    try:
        from ag3nt_agent.deepagents_runtime import _create_model

        model = _create_model()
        print(f"✅ Model created successfully: {type(model).__name__}")
        print(f"   Model details: {model}")
        return True
    except Exception as e:
        print(f"❌ Failed to create model: {e}")
        return False


def test_simple_invocation():
    """Test a simple agent invocation."""
    print("\nTesting simple invocation...")

    try:
        from ag3nt_agent.deepagents_runtime import run_turn

        result = run_turn(
            session_id="test-session",
            text="Say hello and tell me what you can do in one sentence.",
        )

        print(f"✅ Agent responded successfully!")
        print(f"   Session ID: {result['session_id']}")
        print(f"   Response: {result['text'][:100]}...")
        print(f"   Events: {len(result.get('events', []))} tool calls")
        return True
    except Exception as e:
        print(f"❌ Failed to invoke agent: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("AG3NT OpenRouter Integration Test")
    print("=" * 60)
    print()

    tests = [
        test_openrouter_config,
        test_model_creation,
        test_simple_invocation,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
            print()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
            print()

    print("=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)

    return all(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

