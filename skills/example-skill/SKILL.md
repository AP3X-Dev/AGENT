---
name: example-skill
description: A minimal example skill that demonstrates the AG3NT SKILL.md format and contract.
version: "1.0.0"
tags:
  - documentation
  - example
  - meta
triggers:
  - "how do skills work"
  - "show me an example skill"
  - "explain the skill format"
entrypoints:
  run:
    script: scripts/run.sh
    description: Print a confirmation message to verify skill execution works.
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: documentation
---

# Example Skill

This skill demonstrates the AG3NT skill contract. Use it when the user asks about how skills work or wants to see an example.

## When to Use
- User asks "how do skills work?"
- User wants to understand the SKILL.md format
- User asks for an example skill

## Skill Contract

Every AG3NT skill follows this structure:

```
skill-name/              # Folder name = canonical skill ID
├── SKILL.md             # Required: YAML frontmatter + markdown instructions
├── scripts/             # Optional: executable scripts
│   └── run.sh           # Entrypoint scripts referenced in frontmatter
└── references/          # Optional: supporting docs, configs, examples
    └── notes.md
```

## YAML Frontmatter Fields

**Required:**
- `name`: Must match folder name (max 64 chars, lowercase alphanumeric + hyphens)
- `description`: What the skill does (max 1024 chars)

**Optional (Agent Skills spec):**
- `license`: License name (e.g., "MIT", "Apache-2.0")
- `compatibility`: Environment requirements
- `metadata`: Arbitrary key-value map
- `allowed-tools`: Space-delimited list of pre-approved tools

**AG3NT Extensions:**
- `version`: Semantic version (e.g., "1.0.0")
- `tags`: Array of categorization tags
- `triggers`: Keywords/phrases that activate this skill
- `entrypoints`: Named scripts with descriptions
- `required_permissions`: Permissions needed for approval flow

## Running the Example Script

This skill includes an example entrypoint. To run it:

```bash
./scripts/run.sh
```

The script will print a confirmation message.
