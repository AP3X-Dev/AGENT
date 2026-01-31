#!/usr/bin/env python3
"""Example script demonstrating deep reasoning tool usage.

This script shows how the deep_reasoning tool can be used programmatically
to solve a sample problem with branching and hypothesis testing.
"""

import json


def demonstrate_reasoning():
    """Demonstrate a complete reasoning session."""
    
    print("=" * 60)
    print("Deep Reasoning Tool - Example Session")
    print("=" * 60)
    print()
    print("Problem: Why is the API response time increasing over time?")
    print()
    
    # Simulated reasoning session
    thoughts = [
        {
            "step": 1,
            "thought": "Let me analyze the API performance issue. The response time increases from 50ms to 500ms over 24 hours.",
            "params": {
                "thought_number": 1,
                "total_thoughts": 6,
                "next_thought_needed": True,
                "reasoning_mode": "analytical",
                "confidence": 0.8
            }
        },
        {
            "step": 2,
            "thought": "I hypothesize this is a memory leak causing garbage collection pauses.",
            "params": {
                "thought_number": 2,
                "total_thoughts": 6,
                "next_thought_needed": True,
                "thought_type": "hypothesis",
                "hypothesis_statement": "Memory leak causes increasing GC pauses",
                "confidence": 0.6
            }
        },
        {
            "step": 3,
            "thought": "Alternatively, it could be database connection pool exhaustion.",
            "params": {
                "thought_number": 3,
                "total_thoughts": 6,
                "next_thought_needed": True,
                "branch_from_thought": 2,
                "branch_id": "db_pool_theory",
                "reasoning_mode": "exploratory",
                "confidence": 0.5
            }
        },
        {
            "step": 4,
            "thought": "Checking metrics: Memory usage is stable at 60%. GC pauses are normal. Revising my hypothesis.",
            "params": {
                "thought_number": 4,
                "total_thoughts": 6,
                "next_thought_needed": True,
                "is_revision": True,
                "revises_thought": 2,
                "thought_type": "revision",
                "confidence": 0.9
            }
        },
        {
            "step": 5,
            "thought": "DB connection pool shows 95% utilization after 24h. Connections are not being released properly.",
            "params": {
                "thought_number": 5,
                "total_thoughts": 6,
                "next_thought_needed": True,
                "thought_type": "evidence",
                "confidence": 0.85
            }
        },
        {
            "step": 6,
            "thought": "Root cause identified: Connection leak in the user service. Fix: Add connection.close() in finally block.",
            "params": {
                "thought_number": 6,
                "total_thoughts": 6,
                "next_thought_needed": False,
                "thought_type": "conclusion",
                "confidence": 0.95
            }
        }
    ]
    
    for t in thoughts:
        print(f"--- Thought {t['step']}/6 ---")
        print(f"Content: {t['thought']}")
        print(f"Parameters: {json.dumps(t['params'], indent=2)}")
        print()
    
    print("=" * 60)
    print("Session Summary")
    print("=" * 60)
    print("- Total thoughts: 6")
    print("- Branches explored: 2 (main, db_pool_theory)")
    print("- Hypotheses tested: 1 (memory leak - refuted)")
    print("- Revisions made: 1")
    print("- Final confidence: 0.95")
    print("- Conclusion: Connection leak in user service")
    print()
    print("The deep_reasoning tool helped structure this analysis by:")
    print("1. Tracking the reasoning chain")
    print("2. Allowing hypothesis testing")
    print("3. Supporting branching for alternatives")
    print("4. Enabling revision of earlier assumptions")
    print("5. Maintaining confidence scores throughout")


if __name__ == "__main__":
    demonstrate_reasoning()

