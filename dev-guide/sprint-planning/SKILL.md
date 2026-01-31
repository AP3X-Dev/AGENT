---
name: sprint-planning
description: Guide to AG3NT's sprint planning methodology, realignment loop, and development workflow for production readiness.
version: "1.0.0"
tags:
  - development
  - planning
  - workflow
  - process
triggers:
  - "how to plan a sprint"
  - "realignment loop"
  - "sprint planning"
  - "development workflow"
  - "next sprint"
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: development
---

# Sprint Planning and Development Workflow

Use this skill when planning sprints, understanding the realignment loop, or following AG3NT's development methodology.

## The Realignment Loop

**CRITICAL**: Before starting ANY sprint, you MUST complete the Realignment Loop:

```
┌──────────────────────────────────────────────────────────────┐
│                    REALIGNMENT LOOP                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. READ ALL DOCUMENTATION                                   │
│     ├── /docs/AG3NT_Product_Requirements_*.md               │
│     ├── /docs/AG3NT_System_Architecture_*.md                │
│     ├── /docs/PRODUCTION_READINESS_PLAN.md                  │
│     ├── /docs/ROADMAP.md                                    │
│     └── /docs/DOCUMENTATION_REVIEW_*.md (latest)            │
│                                                              │
│  2. ASSESS CURRENT STATE                                     │
│     ├── What was completed in previous sprints?             │
│     ├── What gaps remain?                                   │
│     └── What has changed since last review?                 │
│                                                              │
│  3. VALIDATE ALIGNMENT                                       │
│     ├── Does planned work match product vision?             │
│     ├── Are dependencies satisfied?                         │
│     └── Are priorities still correct?                       │
│                                                              │
│  4. THEN PROCEED WITH SPRINT                                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Sprint Structure

AG3NT follows a 2-week sprint cadence with 5 sprints for production readiness:

| Sprint | Focus | Priority | Coverage Target |
|--------|-------|----------|-----------------|
| 1 | Core Tools & Testing Foundation | CRITICAL | 40% |
| 2 | Agent Capabilities & Integration | HIGH | 55% |
| 3 | Channel Expansion | MEDIUM-HIGH | 65% |
| 4 | Production Hardening | MEDIUM | 75% |
| 5 | Polish & Documentation | ESSENTIAL | 80%+ |

## Task Breakdown Template

Every task should include:

```markdown
## P{Sprint}-{Number}: {Task Name}

**Estimate:** X-Y hours
**Owner:** {Role}
**Priority:** {CRITICAL|HIGH|MEDIUM|LOW}
**Dependencies:** {None or list}

### Current State Analysis
- What exists today?
- What's missing?

### Sub-Tasks
- [ ] P{S}-{N}.1: Sub-task 1 (estimate)
- [ ] P{S}-{N}.2: Sub-task 2 (estimate)

### Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

### Risk Assessment
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|

### Unit Tests Required
- test_case_1
- test_case_2
```

## Development Checklist

Before marking a task complete:

1. **Code Quality**
   - [ ] Code follows existing patterns
   - [ ] No duplicate implementations
   - [ ] Dead code removed

2. **Testing**
   - [ ] Unit tests added (90%+ coverage for new code)
   - [ ] Integration tests where needed
   - [ ] Tests pass locally

3. **Documentation**
   - [ ] Code comments where needed
   - [ ] README updates if public API changed
   - [ ] Type hints/JSDoc complete

4. **Security**
   - [ ] No secrets in code
   - [ ] HITL approval for risky operations
   - [ ] Input validation present

## Priority Definitions

- **CRITICAL**: Blocks core functionality, must be done first
- **HIGH**: Important for sprint goals, do early
- **MEDIUM**: Valuable but not blocking, schedule flexibly
- **LOW**: Nice to have, do if time permits

## Further Reading

For detailed plans, refer to:
- Full roadmap: `/docs/ROADMAP.md`
- Sprint 1-2 breakdown: `/docs/SPRINT_1_2_TASK_BREAKDOWN.md`
- Production plan: `/docs/PRODUCTION_READINESS_PLAN.md`

