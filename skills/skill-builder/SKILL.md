# Skill Builder

## When to use this skill

Use this skill when the user asks to:
- Build or generate a voice skill for an MCP server
- Create a voice bridge for a tool or app
- List what MCP tools are available and whether voice skills exist for them
- Audit which connected tools have voice skills and which are missing them

Trigger phrases:
- "build a voice skill for [app]"
- "create a voice bridge for [tool]"
- "what tools do I have voice skills for?"
- "generate a skill for my [MCP server]"

## Steps

1. Identify the target MCP server from the user's request
2. Call `list_tools()` on the MCP server to get all available tools
3. Group tools by operation type:
   - Query operations (list, get, search, fetch) — low confirmation needed
   - Create operations (create, add, new) — confirm key fields
   - Update operations (update, edit, move, reschedule) — confirm what's changing
   - Delete operations (delete, cancel, remove, archive) — always confirm
4. For each tool, extract:
   - Tool name → intent pattern(s) in natural speech
   - Required fields → what to ask before calling
   - Response shape → how to speak the result
5. Generate a SKILL.md using the Voice Bridge Skill template
6. Save to `~/.openclaw/workspace/skills/[app-name]-voice-bridge/SKILL.md`
7. Confirm to the user: "Voice skill for [app] is ready. Say '[example trigger]' to try it."

## Voice Bridge Skill Template

Generate a file with this structure, filled in for the specific MCP server:

```markdown
# [App Name] Voice Bridge Skill

## When to use this skill
[When to trigger — list voice phrases]

## Intent patterns
[Map spoken phrases to tool names]

## Required context before tool call
[What to resolve before calling each tool type]

## Confirmation policy
[Which operations confirm and how]

## Response templates
[How to speak each result type naturally]

## Disambiguation patterns
[How to handle ambiguous references]
```

## Output

Always tell the user:
- Where the skill was saved
- One example voice phrase to test it
- Which tools have confirmation policies (so they know what to expect)
- Any tools the builder was uncertain about (flag for manual review)
