# Voice Bridge Skills

## What They Are

Voice Bridge Skills are `SKILL.md` files that teach the OpenClaw agent how to handle voice-originated requests for specific MCP tool categories. They are the core innovation of VoiceClaw — the missing glue layer between real-time speech and MCP tool execution.

## Why They're Needed

When someone types "move my 3pm to tomorrow" in a chat interface, the ambiguity is low — they can re-read, clarify, wait. When they say it out loud, mid-task, with possible background noise:

- "3pm" might match two calendar events
- "tomorrow" needs to resolve to a UTC datetime right now
- A destructive operation (delete, send, move) needs verbal confirmation
- The response needs to be speakable, not a JSON blob
- If the tool fails, the recovery needs to sound natural

A Voice Bridge Skill encodes all of this context for a specific tool category.

## Anatomy of a Voice Bridge Skill

```markdown
# [Tool Category] Voice Bridge Skill

## When to use this skill
Use when the user's voice request relates to [calendar / email / tasks / etc].

## Intent patterns
- "move my [time] meeting" → update_event
- "what's on my calendar [time]" → list_events  
- "cancel my [description] meeting" → delete_event (CONFIRM FIRST)
- "am I free [time]" → get_freebusy

## Required context before tool call
- For any time reference: resolve to ISO 8601 UTC using current datetime
- For ambiguous event references: list matching events and ask "which one?"
- For attendee references: resolve name to email via contacts if available

## Confirmation policy
- list_events, get_freebusy: execute silently
- create_event: confirm title + time before creating
- update_event: confirm what is changing
- delete_event: ALWAYS confirm before executing

## Response templates
- list_events (0 results): "You have nothing on your calendar [timeframe]."
- list_events (1-3): "You have [N] things: [natural list]."
- list_events (4+): "You have [N] things. The first few are [list]. Want me to read them all?"
- create_event success: "Done, [title] is on your calendar for [natural time]."
- delete_event success: "Cancelled. [title] has been removed."
- tool error: "I couldn't [action] because [plain English reason]. Want me to try again?"

## Disambiguation patterns
- Multiple events match: "I found [N] meetings at that time. Do you mean [A] or [B]?"
- Time is ambiguous: "Did you mean this [day] or next [day]?"
- No events found: "I don't see a [description] meeting. Do you want to search differently?"
```

## The Skill Builder Skill

The `skill-builder` meta-skill can generate a Voice Bridge Skill automatically by:

1. Querying an MCP server's `list_tools()` endpoint
2. Analysing each tool's name, description, and input schema
3. Grouping tools by category (CRUD operations, query operations, etc.)
4. Generating intent patterns, confirmation policies, and response templates
5. Saving the result as a new `SKILL.md` in `~/.openclaw/workspace/skills/`

The generated skill is a starting point — review and refine before relying on it in production.

## Available Voice Bridge Skills

| Skill | MCP Category | Status |
|---|---|---|
| `skill-builder` | Meta — generates other skills | In progress |
| `calendar-voice-bridge` | Google Calendar, Outlook Calendar | Planned |
| `email-voice-bridge` | Gmail, Outlook | Planned |
| `tasks-voice-bridge` | Notion, Linear, Asana | Planned |
| `messaging-voice-bridge` | Slack, Teams | Planned |
| `files-voice-bridge` | Google Drive, Dropbox | Planned |
