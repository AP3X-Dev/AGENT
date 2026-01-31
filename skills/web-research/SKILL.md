---
name: web-research
description: Structured approach to conducting thorough web research with citations and organized output.
version: "1.0.0"
tags:
  - research
  - web
  - search
  - citations
triggers:
  - "research"
  - "find information about"
  - "what is the latest on"
  - "compare"
  - "look up"
  - "search for"
entrypoints:
  report:
    script: scripts/generate-report.py
    description: Generate a formatted markdown report from research findings.
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: research
---

# Web Research Skill

Use this skill when the user needs:
- Current information on any topic
- Comparison between products, services, or concepts
- Documentation or official sources
- News or recent developments
- Cited summaries with sources

## Research Workflow

### Step 1: Plan Your Research

Before searching, define:
1. **Main question**: What specifically does the user want to know?
2. **Subtopics**: Break complex topics into 2-3 focused areas
3. **Source types**: What kinds of sources are most relevant?
   - Documentation (official docs, specs)
   - News (recent articles, announcements)
   - Academic (papers, research)
   - Community (forums, discussions, reviews)

### Step 2: Search and Gather

For each subtopic:
1. **Run 2-3 targeted searches** using the web_search tool
2. **Evaluate sources** for credibility:
   - Official domains (.gov, .edu, company sites)
   - Publication date (prefer recent for evolving topics)
   - Author expertise
3. **Extract key information** and note the source URL

### Step 3: Organize Findings

Create a structured output:

```markdown
## Research: [Topic Name]

### Key Findings
- Finding 1 [Source](url)
- Finding 2 [Source](url)

### Detailed Summary
[Synthesis of information with inline citations]

### Sources
1. [Title](url) - Brief description of what this source provided
2. [Title](url) - Brief description of what this source provided
```

### Step 4: Synthesize and Respond

When presenting to the user:
1. **Lead with the answer** - Don't bury the key information
2. **Provide context** - Why is this relevant?
3. **Cite sources** - Use inline links or footnotes
4. **Note limitations** - If information is incomplete or conflicting, say so

## Citation Format

Use this format for citations:
- Inline: `According to [Source Name](url), ...`
- Footnote: `Key fact here[^1]` with `[^1]: Source Name - url`
- List: See references/citation-format.md for detailed examples

## Quality Checklist

Before finishing research:
- [ ] Answered the user's core question
- [ ] Used at least 2-3 distinct sources
- [ ] Cited all factual claims
- [ ] Noted if information is dated or incomplete
- [ ] Provided actionable next steps if relevant

## Available Tools

When conducting research, you have access to:
- **web_search**: Search the web for information
- **read_file**: Read local reference files (e.g., this skill's references/)
- **write_file**: Save research notes or reports locally

## Tips for Better Research

1. **Be specific in queries** - "Python asyncio error handling 2024" vs "Python errors"
2. **Verify across sources** - Don't rely on a single source for important facts
3. **Check dates** - Technology and news change quickly
4. **Use quotes for exact phrases** - "error message here" finds exact matches
5. **Exclude noise** - Add -pinterest -reddit if results are cluttered
