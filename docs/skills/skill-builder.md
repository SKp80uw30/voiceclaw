# Skill Builder Skill

## Purpose

The Skill Builder is a meta-skill — a skill that creates other skills. It introspects an MCP server's tool schema and generates a Voice Bridge Skill SKILL.md file tailored to that server's capabilities.

## How It Works

```
User: "Build a voice skill for my Google Calendar MCP"
  ↓
Skill Builder runs
  ↓
Calls MCP server: list_tools()
  ↓
Receives: [create_event, delete_event, list_events, update_event, get_freebusy, ...]
  ↓
Analyses each tool:
  - name + description → intent patterns
  - required fields → what to confirm before calling
  - destructive operations → confirmation policy
  - response shape → natural language templates
  ↓
Generates: ~/.openclaw/workspace/skills/google-calendar-voice-bridge/SKILL.md
  ↓
Skill immediately available to voice agent
```

## Usage

Once installed, trigger via voice or text:

```
"Build a voice skill for [MCP server name]"
"Create a voice bridge for my Notion tools"
"What MCP tools do I have and which need voice skills?"
```

## SKILL.md Template

See [voice-bridge-skills.md](voice-bridge-skills.md) for the full anatomy of a generated skill.

## Limitations of Generated Skills

The Skill Builder produces a **first draft**. Always review:

- **Confirmation policies** — the builder errs conservative (confirms more than needed). Tune to your preference.
- **Response templates** — generated templates are functional but generic. Personalise the voice/tone.
- **Intent patterns** — the builder may miss regional speech patterns or personal shorthand. Add your own.
- **Disambiguation** — complex multi-step disambiguation may need manual refinement.

## Publishing to ClawHub

Well-refined Voice Bridge Skills should be published to ClawHub so the whole OpenClaw community can use them with VoiceClaw (or any OpenClaw installation). The Skill Builder will eventually include a one-command publish flow.
