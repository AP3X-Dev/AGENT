# Deep Reasoning Patterns

This document provides common reasoning patterns for different problem types.

## Pattern 1: Root Cause Analysis

Use when: Debugging issues, finding the source of problems

```
1. Define the symptom clearly
2. List possible causes (branch for each major theory)
3. Gather evidence for/against each cause
4. Eliminate causes that don't fit evidence
5. Verify the remaining cause
6. Conclude with root cause and fix
```

**Recommended settings:**
- Mode: `analytical`
- Use `hypothesis` thought type for each theory
- Use `evidence` thought type when gathering data
- Use `revision` when eliminating theories

## Pattern 2: Decision Making

Use when: Choosing between options, evaluating trade-offs

```
1. Define the decision criteria
2. List all options
3. Branch to evaluate each option
4. Score each option against criteria
5. Compare scores across branches
6. Conclude with recommendation
```

**Recommended settings:**
- Mode: `critical`
- Create explicit branches for each option
- Track confidence for each evaluation
- Use `conclusion` type for final recommendation

## Pattern 3: Design Exploration

Use when: Architecting solutions, exploring design space

```
1. Define requirements and constraints
2. Propose initial design
3. Identify potential issues
4. Branch to explore alternatives
5. Evaluate trade-offs
6. Synthesize best elements
7. Conclude with final design
```

**Recommended settings:**
- Mode: `creative` for brainstorming, `critical` for evaluation
- Use branching liberally
- Lower confidence (0.5-0.7) during exploration
- Higher confidence (0.8+) for final design

## Pattern 4: Learning/Understanding

Use when: Understanding new concepts, learning from documentation

```
1. State what you're trying to understand
2. Break into sub-concepts
3. Explain each sub-concept
4. Identify connections between concepts
5. Test understanding with examples
6. Summarize the complete picture
```

**Recommended settings:**
- Mode: `exploratory` initially, `deductive` for testing
- Use `question` thought type for unknowns
- Use `evidence` when finding answers
- Revise as understanding improves

## Pattern 5: Hypothesis Testing (Scientific Method)

Use when: Validating assumptions, testing theories

```
1. Observe the phenomenon
2. Form a hypothesis
3. Design a test
4. Predict the outcome if hypothesis is true
5. Run the test / gather evidence
6. Compare results to prediction
7. Accept, reject, or revise hypothesis
8. Conclude
```

**Recommended settings:**
- Mode: `deductive` or `inductive`
- Use `hypothesis` thought type explicitly
- Use `verification` when testing
- Track confidence changes as evidence accumulates

## Pattern 6: Planning

Use when: Creating action plans, project planning

```
1. Define the goal
2. Identify major milestones
3. Break milestones into tasks
4. Identify dependencies
5. Identify risks (branch for mitigation strategies)
6. Sequence tasks
7. Conclude with plan
```

**Recommended settings:**
- Mode: `analytical`
- Branch for risk mitigation alternatives
- Use `question` type for unknowns
- Higher confidence for well-understood tasks

## Pattern 7: Comparative Analysis

Use when: Comparing products, technologies, approaches

```
1. Define comparison criteria
2. Research option A (branch)
3. Research option B (branch)
4. Research option C (branch)
5. Create comparison matrix
6. Weigh criteria by importance
7. Conclude with recommendation
```

**Recommended settings:**
- Mode: `analytical`
- Explicit branches for each option
- Use `evidence` type for findings
- Consistent confidence scoring across options

## Confidence Calibration Guide

| Confidence | Meaning | When to Use |
|------------|---------|-------------|
| 0.95-1.0 | Certain | Verified facts, tested conclusions |
| 0.80-0.94 | High | Strong evidence, reliable sources |
| 0.60-0.79 | Moderate | Good reasoning, some uncertainty |
| 0.40-0.59 | Low | Speculation, limited evidence |
| 0.20-0.39 | Very Low | Guessing, exploring possibilities |
| 0.01-0.19 | Minimal | Wild speculation, brainstorming |

## Anti-Patterns to Avoid

1. **Skipping steps**: Don't jump to conclusions without intermediate reasoning
2. **Ignoring low confidence**: Address uncertain areas before concluding
3. **Forgetting to revise**: Update earlier thoughts when you learn new information
4. **Single-path thinking**: Use branches to explore alternatives
5. **Vague hypotheses**: Make hypotheses specific and testable
6. **Missing conclusions**: Always end with `next_thought_needed=false`

