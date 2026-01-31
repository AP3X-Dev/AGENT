---
name: deep-reasoning
description: Structured multi-step reasoning tool for complex problem solving with branching, hypothesis testing, and evidence tracking.
version: "1.0.0"
tags:
  - reasoning
  - problem-solving
  - analysis
  - thinking
  - planning
triggers:
  - "think through this"
  - "reason about"
  - "analyze step by step"
  - "break down this problem"
  - "help me think"
  - "complex problem"
  - "need to figure out"
  - "let me think"
entrypoints:
  example:
    script: scripts/example.py
    description: Show an example of deep reasoning in action.
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: reasoning
---

# Deep Reasoning Skill

Use this skill when you need to think through complex problems systematically. The `deep_reasoning` tool helps you:

- Break down complex problems into manageable steps
- Explore multiple solution approaches (branching)
- Revise earlier thinking when new information emerges
- Generate and test hypotheses
- Track confidence levels in your conclusions
- Maintain structured reasoning across long analyses

## When to Use Deep Reasoning

**Use this tool when:**
- The problem requires multiple steps to solve
- You need to explore alternative approaches
- Earlier assumptions might need revision
- You want to track confidence in your conclusions
- The problem involves hypothesis testing
- You need to maintain reasoning context across many steps

**Don't use for:**
- Simple factual lookups
- Single-step operations
- Tasks that don't benefit from structured thinking

## The deep_reasoning Tool

### Basic Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `thought` | string | Yes | Your current thinking step |
| `thought_number` | int | Yes | Current step number (1, 2, 3...) |
| `total_thoughts` | int | Yes | Estimated total steps needed |
| `next_thought_needed` | bool | Yes | True if more thinking needed |

### Advanced Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `thought_type` | string | "regular" | Type: regular, hypothesis, verification, revision, branch, conclusion, question, evidence |
| `reasoning_mode` | string | "analytical" | Mode: analytical, creative, critical, exploratory, deductive, inductive, abductive |
| `confidence` | float | 0.7 | Confidence level (0.0 to 1.0) |
| `is_revision` | bool | false | Whether this revises a previous thought |
| `revises_thought` | int | null | Which thought number is being revised |
| `branch_from_thought` | int | null | Create a branch from this thought |
| `branch_id` | string | null | Identifier for the branch |
| `hypothesis_statement` | string | null | Propose a new hypothesis |
| `hypothesis_id` | string | null | Reference an existing hypothesis |

## Reasoning Modes

Choose the mode that fits your analysis:

| Mode | When to Use |
|------|-------------|
| **analytical** | Breaking down problems, examining components |
| **creative** | Brainstorming, generating novel solutions |
| **critical** | Evaluating claims, finding weaknesses |
| **exploratory** | Open-ended investigation, discovery |
| **deductive** | Applying general rules to specific cases |
| **inductive** | Inferring patterns from specific examples |
| **abductive** | Finding the best explanation for observations |

## Thought Types

Mark your thoughts appropriately:

| Type | Purpose |
|------|---------|
| **regular** | Standard reasoning step |
| **hypothesis** | Proposing something to test |
| **verification** | Testing a hypothesis |
| **revision** | Updating earlier thinking |
| **branch** | Exploring an alternative path |
| **conclusion** | Final determination |
| **question** | Identifying what needs answering |
| **evidence** | Recording supporting data |

## Example Workflows

### Basic Sequential Reasoning

```
Thought 1/5: "Let me understand the problem first..."
Thought 2/5: "The key constraints are..."
Thought 3/5: "One approach would be..."
Thought 4/5: "Evaluating this approach..."
Thought 5/5: "My conclusion is..." (next_thought_needed=false)
```

### With Branching

```
Thought 1/5: "Initial analysis..."
Thought 2/5: "Approach A would..."
Thought 3/5: "But what if we try Approach B?" (branch_from_thought=2, branch_id="approach_b")
Thought 4/5: "Comparing both approaches..."
Thought 5/5: "Approach B is better because..."
```

### With Hypothesis Testing

```
Thought 1/5: "Observing the symptoms..."
Thought 2/5: "I hypothesize the cause is X" (hypothesis_statement="The bug is in the auth layer")
Thought 3/5: "Testing this hypothesis..." (thought_type="verification", hypothesis_id="...")
Thought 4/5: "Evidence supports/refutes the hypothesis..."
Thought 5/5: "Conclusion based on verified hypothesis..."
```

### With Revision

```
Thought 1/5: "Initial assumption: the database is the bottleneck"
Thought 2/5: "But wait, the metrics show..." (is_revision=true, revises_thought=1)
Thought 3/5: "Actually, the network latency is the issue..."
```

## Complete Tool Call Examples

### Example 1: Starting a Reasoning Session

```json
{
  "thought": "Let me break down this authentication bug. The user reports they can log in but get logged out after 5 minutes.",
  "thought_number": 1,
  "total_thoughts": 6,
  "next_thought_needed": true,
  "reasoning_mode": "analytical",
  "confidence": 0.8
}
```

### Example 2: Proposing a Hypothesis

```json
{
  "thought": "Based on the 5-minute timeout, I suspect the session token expiration is set incorrectly.",
  "thought_number": 2,
  "total_thoughts": 6,
  "next_thought_needed": true,
  "thought_type": "hypothesis",
  "hypothesis_statement": "Session token TTL is set to 5 minutes instead of the expected 30 minutes",
  "confidence": 0.7
}
```

### Example 3: Creating a Branch

```json
{
  "thought": "Alternatively, this could be a cookie domain mismatch issue causing the session to not persist.",
  "thought_number": 3,
  "total_thoughts": 6,
  "next_thought_needed": true,
  "branch_from_thought": 2,
  "branch_id": "cookie_theory",
  "reasoning_mode": "exploratory",
  "confidence": 0.5
}
```

### Example 4: Revising Earlier Thinking

```json
{
  "thought": "After checking the config, the TTL is correct at 30 minutes. My earlier hypothesis was wrong.",
  "thought_number": 4,
  "total_thoughts": 6,
  "next_thought_needed": true,
  "is_revision": true,
  "revises_thought": 2,
  "thought_type": "revision",
  "confidence": 0.9
}
```

### Example 5: Reaching a Conclusion

```json
{
  "thought": "The issue is confirmed: the cookie domain was set to 'example.com' but the app runs on 'app.example.com'. Fixing the domain setting resolves the logout issue.",
  "thought_number": 6,
  "total_thoughts": 6,
  "next_thought_needed": false,
  "thought_type": "conclusion",
  "confidence": 0.95
}
```

## Best Practices

### 1. Start with Clear Problem Definition
Always begin by clearly stating what you're trying to solve. This anchors the entire reasoning chain.

### 2. Adjust Total Thoughts Dynamically
If you realize you need more steps, increase `total_thoughts`. The tool handles this gracefully.

### 3. Use Appropriate Confidence Levels
- **0.9-1.0**: Very confident, based on verified facts
- **0.7-0.8**: Reasonably confident, good evidence
- **0.5-0.6**: Uncertain, exploring possibilities
- **0.3-0.4**: Low confidence, speculative
- **0.1-0.2**: Highly uncertain, just brainstorming

### 4. Branch When Exploring Alternatives
Don't just mention alternatives—create explicit branches. This helps track which path led to the solution.

### 5. Revise Rather Than Ignore
When you realize earlier thinking was wrong, use `is_revision=true` to explicitly update it. This maintains reasoning integrity.

### 6. End with Conclusions
Always set `next_thought_needed=false` and `thought_type="conclusion"` when you've reached your answer.

## Tool Response Format

The tool returns a JSON response with:

```json
{
  "status": "success",
  "thought_id": "abc123",
  "thought_number": 3,
  "total_thoughts": 6,
  "next_thought_needed": true,
  "branches": ["main", "cookie_theory"],
  "hypotheses": ["hyp_001"],
  "thought_history_length": 3,
  "average_confidence": 0.73,
  "current_mode": "analytical",
  "guidance": "Consider testing your hypothesis with evidence.",
  "hypothesis_id": "hyp_001"
}
```

## Integration with Other Tools

Deep reasoning works well with:

- **web_search**: Gather evidence to support or refute hypotheses
- **read_file**: Examine code or configs during analysis
- **run_skill**: Execute other skills as part of your reasoning
- **memory_search**: Recall relevant past context

## Troubleshooting

### "Max branches reached"
You've hit the branch limit (default: 10). Consolidate branches or start a new reasoning session.

### "Max thoughts reached"
You've hit the thought limit (default: 50). Summarize your findings and start fresh if needed.

### Low average confidence
If your average confidence is below 0.5, consider:
- Gathering more evidence
- Revising uncertain assumptions
- Exploring alternative approaches

