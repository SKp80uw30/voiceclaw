# Calendar Voice Bridge Skill

## When to use this skill

Use when the user's voice request relates to calendar, meetings, events, scheduling, or availability.

Trigger phrases:
- "what's on my calendar"
- "am I free [time]"
- "move my [time] meeting"
- "cancel my [description] meeting"
- "schedule a meeting with [person]"
- "when is my next [description]"
- "what do I have [day]"

## Intent patterns

| Spoken phrase | Tool | Notes |
|---|---|---|
| "what's on my calendar [time]" | `list_events` | |
| "what do I have [day]" | `list_events` | |
| "am I free [time]" | `get_freebusy` | |
| "do I have anything [time]" | `get_freebusy` | |
| "schedule / book / create a meeting" | `create_event` | Confirm before creating |
| "move / reschedule my [event]" | `update_event` | Confirm what's changing |
| "cancel / delete my [event]" | `delete_event` | Always confirm |
| "when is my next [description]" | `list_events` | Filter upcoming only |

## Required context before tool call

- **All time references**: Resolve to ISO 8601 UTC using the current datetime before calling any tool. Never pass relative times ("tomorrow", "3pm") directly to the tool.
- **Ambiguous event references**: If more than one event matches, list them and ask "which one?"
- **Person references**: Attempt to resolve name to email via contacts MCP if available.
- **Duration**: If not specified for create_event, default to 1 hour and confirm.

## Confirmation policy

| Tool | Policy |
|---|---|
| `list_events` | Execute silently |
| `get_freebusy` | Execute silently |
| `create_event` | Confirm title + time before creating |
| `update_event` | Confirm what is changing (old → new) |
| `delete_event` | **Always confirm** — say "Just to confirm, delete [title] on [date]?" |

## Response templates

- **list_events (0 results)**: "You have nothing on your calendar [timeframe]."
- **list_events (1 result)**: "You have [title] at [natural time]."
- **list_events (2-3 results)**: "You have [N] things: [natural list]."
- **list_events (4+ results)**: "You have [N] things on [day]. The first few are [list]. Want me to read them all?"
- **get_freebusy (free)**: "You're free [timeframe]."
- **get_freebusy (busy)**: "You have [N] thing(s) during that time."
- **create_event success**: "Done, [title] is on your calendar for [natural time]."
- **update_event success**: "Updated. [title] is now [what changed]."
- **delete_event success**: "Cancelled. [title] has been removed from your calendar."
- **tool error**: "I couldn't [action] — [plain English reason]. Want me to try a different way?"

## Disambiguation patterns

- **Multiple events match**: "I found [N] meetings around that time. Do you mean [A] at [time A] or [B] at [time B]?"
- **Time is ambiguous**: "Did you mean this [weekday] or next [weekday]?"
- **No events found**: "I don't see a [description] on your calendar. Do you want to search differently?"
- **Attendee not found in contacts**: "I don't have an email for [name]. Do you know it?"
