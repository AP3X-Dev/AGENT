---
name: heartbeat
description: Periodic system check for proactive updates and reminders
version: 1.0.0
tags:
  - system
  - scheduled
  - proactive
triggers:
  - HEARTBEAT
---

# Heartbeat Check

You are running a scheduled periodic check. Go through this checklist and only report items that need the user's attention.

## Checklist

1. **Pending reminders**: Check if any scheduled reminders are due or approaching
2. **Task status**: Review any in-progress tasks in your todo list that need attention
3. **Time-sensitive items**: Note upcoming events or deadlines if known
4. **Pending questions**: Check if there are any unresolved questions waiting for user input

## Response Format

- If there is something to report, provide a **brief** summary of what needs attention
- If nothing needs attention, respond ONLY with: `HEARTBEAT_OK`

## Guidelines

- **Be concise**: Only report actionable items
- **Prioritize**: Most urgent items first
- **No noise**: If in doubt, say HEARTBEAT_OK
- **No greetings**: Skip pleasantries, get to the point

## Example Responses

### Nothing to report:
```
HEARTBEAT_OK
```

### Has items to report:
```
📋 Quick update:
- Reminder: Call Alice at 3pm (in 30 minutes)
- Task: Code review for PR #42 is still pending
```

**Important**: This is a background check. Only surface genuinely useful information. The user should not be bothered by empty or low-value notifications.

