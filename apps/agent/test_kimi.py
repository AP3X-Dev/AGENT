#!/usr/bin/env python3
"""Test script for Kimi (Moonshot AI) integration.

This script tests the Kimi model provider configuration.
Set KIMI_API_KEY environment variable before running.

Usage:
    export KIMI_API_KEY=your_key_here
    export AG3NT_MODEL_PROVIDER=kimi
    export AG3NT_MODEL_NAME=moonshot-v1-128k
    python test_kimi.py
"""

import os
import sys


def test_kimi_config():
    """Test Kimi configuration."""
    print("Testing Kimi configuration...")
    print(f"Provider: {os.environ.get('AG3NT_MODEL_PROVIDER', 'not set')}")
    print(f"Model: {os.environ.get('AG3NT_MODEL_NAME', 'not set')}")
    print(f"API Key: {'set' if os.environ.get('KIMI_API_KEY') else 'NOT SET'}")
    print()

    if not os.environ.get("KIMI_API_KEY"):
        print("❌ KIMI_API_KEY not set!")
        print("Get your key from: https://platform.moonshot.cn/")
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
            session_id="test-kimi-session",
            text="Say hello in both English and Chinese, then tell me what you can do in one sentence.",
        )

        print(f"✅ Agent responded successfully!")
        print(f"   Session ID: {result['session_id']}")
        print(f"   Response: {result['text'][:200]}...")
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
    print("AG3NT Kimi (Moonshot AI) Integration Test")
    print("=" * 60)
    print()

    tests = [
        test_kimi_config,
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

