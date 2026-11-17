# 05d-connect-cursor

## Purpose

Connect Cursor to the door with its own door key, without changing anything else and without opening its config.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key file, key variable, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. Never open `mcp.json`. The person's yes comes in step 2 of the common steps.

## Where Cursor keeps it

| Scope | macOS and Linux | Windows |
|---|---|---|
| Global | `~/.cursor/mcp.json` | `%USERPROFILE%\.cursor\mcp.json` |
| Project | `<project>/.cursor/mcp.json` | `<project>\.cursor\mcp.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Quit Cursor** before the change.
2. **Add**: `python tools/add_entry.py --harness cursor --config ~/.cursor/mcp.json --url <door url> --key-env CURSOR_DOOR_KEY --backup-dir <run folder>/05d-connect-cursor/backup`. It writes `${env:CURSOR_DOOR_KEY}`; check the vendor docs that your version expands it. If it does not, run it with `--key-file <Cursor's key file> --replace` instead: the key is then written into the file in-process, and the file is made owner-only. That is a plain-text door key, expected by design; the next rescan marks it as a door entry.
3. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
4. **Limits**: Cursor has warned on long server plus tool names and capped active tools (check the vendor docs). Keep the server name short.
5. **Check**: Cursor's MCP settings show `door` enabled with its tools; ask one read question in chat.
6. **Smoke**: `python tools/smoke_harness.py --harness cursor --url <door url> --key-file <Cursor's key file> --server-name door --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05d-connect-cursor/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/add_entry.py`, `tools/smoke_harness.py`
