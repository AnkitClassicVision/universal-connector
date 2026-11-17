# 05d-connect-cursor

## Purpose

Connect Cursor to the door with its own door key, without changing anything else.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key variable, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. This stage is a human yes point.

## Where Cursor keeps it

| Scope | macOS and Linux | Windows |
|---|---|---|
| Global | `~/.cursor/mcp.json` | `%USERPROFILE%\.cursor\mcp.json` |
| Project | `<project>/.cursor/mcp.json` | `<project>\.cursor\mcp.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Quit Cursor** before editing.
2. **Entry**: `python tools/entry.py --harness cursor --url <door url> --key-env CURSOR_DOOR_KEY`. It uses `${env:CURSOR_DOOR_KEY}`; check the vendor docs that your version expands it. If it does not, the person pastes this harness's door key into the file themselves and makes the file readable only by them.
3. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
4. **Limits**: Cursor has warned on long server plus tool names and capped active tools (check the vendor docs). Keep the server name short.
5. **Check**: Cursor's MCP settings show `door` enabled with its tools; ask one read question in chat.
6. **Smoke**: `python tools/smoke_harness.py --harness cursor --url <door url> --key-env CURSOR_DOOR_KEY --server-name door`.

## Output

Write to `<run folder>/05d-connect-cursor/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
