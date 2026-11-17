# 05a-connect-claude-code

## Purpose

Connect Claude Code to the door with its own door key, without changing anything else and without opening its config.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key file, key variable, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL and slowest call |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. Never open `~/.claude.json` or any settings file. The person's yes comes in step 2 of the common steps.

## Where Claude Code keeps it

| Scope | macOS and Linux | Windows |
|---|---|---|
| User (all projects) | `~/.claude.json`, or `$CLAUDE_CONFIG_DIR/.claude.json` when that variable is set | `%USERPROFILE%\.claude.json` |
| Project (shared with the repo) | `<project>/.mcp.json` | `<project>\.mcp.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Add with Claude Code's own command.** `python tools/entry.py --harness claude-code --url <door url> --key-env CLAUDE_DOOR_KEY` prints a ready, quoted `claude mcp add-json --scope user door '<json>'` line; run it. The quoting keeps `${CLAUDE_DOOR_KEY}` literal. For a project's `.mcp.json`, use `python tools/add_entry.py --harness claude-code --config <project>/.mcp.json --url <door url> --key-env CLAUDE_DOOR_KEY --backup-dir <run folder>/05a-connect-claude-code/backup`.
2. **Key**: the person makes `CLAUDE_DOOR_KEY` available in the environment Claude Code starts with, from Claude Code's 0600 key file. The agent never reads or sets it.
3. **Read timeout**: the person sets `MCP_TOOL_TIMEOUT` (milliseconds) above the door's slowest call in that same environment.
4. **Check**: `claude mcp list` shows `door` connected. In a session, ask it to list the door's tools, then one read question.
5. **If the door answers 401** while the key is set, this scope did not expand `${...}` in your version. Use project scope `.mcp.json`, or check the vendor docs for a header helper.
6. **Smoke**: `python tools/smoke_harness.py --harness claude-code --url <door url> --key-file <Claude Code's key file> --server-name door --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.
7. GrokBot's CLI reads this same list. Note that in `connect.md`.

## Output

Write to `<run folder>/05a-connect-claude-code/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/add_entry.py`, `tools/smoke_harness.py`
