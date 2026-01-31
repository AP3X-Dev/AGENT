---
name: daily-briefing
description: Generate a daily briefing summary for the user
version: 1.0.0
tags:
  - system
  - scheduled
  - proactive
  - briefing
triggers:
  - DAILY_BRIEFING
  - morning briefing
  - daily summary
---

# Daily Briefing

Generate a concise daily briefing for the user. This skill is typically triggered by a scheduled cron job at the start of the day.

## Briefing Structure

1. **Good morning greeting** (keep it brief)
2. **Today's date and day of week**
3. **Reminders due today** (if any scheduled)
4. **Tasks in progress** (from your todo list)
5. **Key items to be aware of** (based on recent context)

## Response Format

```
☀️ Good morning!

📅 Today is [Day], [Date]

📋 Today's Focus:
- [Key tasks or reminders]
- [Any pending items]

🎯 Tip: [Optional - a brief productivity tip or encouragement]
```

## Guidelines

- **Be concise**: Keep the briefing under 10 lines
- **Only actionable items**: Don't pad with fluff
- **Positive tone**: Start the day on a good note
- **Skip sections**: If there's nothing for a section, omit it entirely
- **Context-aware**: Reference recent conversations if relevant

## Example Output

```
☀️ Good morning!

📅 Today is Monday, January 27th

📋 Today's Focus:
- Reminder: Team standup at 10am
- In progress: Code review for auth feature
- Pending: Reply to Alice's email

🎯 Have a productive day!
```

## Integration Notes

This skill is designed to be triggered by a cron job configured like:

```yaml
scheduler:
  cron:
    - schedule: "0 9 * * *"  # 9 AM daily
      message: "DAILY_BRIEFING"
      sessionMode: "main"
      name: "Morning Briefing"
```

The response will be sent to the user's primary channel.

