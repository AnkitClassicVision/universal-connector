# 05a-connect-claude-code

## Purpose

Connect Claude Code to the door with its own door key, without changing anything else.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key variable, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL and slowest call |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. This stage is a human yes point.

## Where Claude Code keeps it

| Scope | macOS and Linux | Windows |
|---|---|---|
| User (all projects) | `~/.claude.json`, or `$CLAUDE_CONFIG_DIR/.claude.json` when that variable is set | `%USERPROFILE%\.claude.json` |
| Project (shared with the repo) | `<project>/.mcp.json` | `<project>\.mcp.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Entry**: `python tools/entry.py --harness claude-code --url <door url> --key-env CLAUDE_DOOR_KEY`. Add it with `claude mcp add-json --scope user door '<json>'`. Keep the single quotes so the shell does not expand `${CLAUDE_DOOR_KEY}`.
2. **Key**: the person makes `CLAUDE_DOOR_KEY` available in the environment Claude Code starts with, from wherever the door put this harness's key. The agent never sets it.
3. **Read timeout**: set `MCP_TOOL_TIMEOUT` (milliseconds) above the door's slowest call, in that environment or in the `env` block of `~/.claude/settings.json`.
4. **Check**: `claude mcp list` shows `door` connected. In a session, ask it to list the door's tools, then one read question.
5. **If the door answers 401** while the key is set, this scope did not expand `${...}` in your version. Use project scope `.mcp.json`, or check the vendor docs for a header helper.
6. **Smoke**: `python tools/smoke_harness.py --harness claude-code --url <door url> --key-env CLAUDE_DOOR_KEY --server-name door`.
7. GrokBot's CLI reads this same list. Note that in `connect.md`.

## Output

Write to `<run folder>/05a-connect-claude-code/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
