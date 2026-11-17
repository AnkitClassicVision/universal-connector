# 05b-connect-claude-desktop

## Purpose

Connect Claude Desktop to the door with its own door key, through a local bridge, without changing anything else.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key file path, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. This stage is a human yes point.

## Where Claude Desktop keeps it

| macOS | Windows | Linux (community builds) |
|---|---|---|
| `~/Library/Application Support/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Quit the app fully first.** It rewrites this file when it quits and would undo the edit.
2. **Entry**: the JSON file takes local programs only. Use a local stdio bridge that forwards to the door URL and adds the `Authorization` header. The bridge reads this harness's key from a file with mode 600 at start, so the key is not in the JSON. Community bridges exist; check the vendor docs and decide with the person whether to trust one before use. `python tools/entry.py --harness claude-desktop --url <door url>` prints the shape.
3. **Custom connectors** added in Settings may be reached from the vendor's servers, so a loopback or tailnet door may not be reachable that way. Use the bridge unless the vendor docs say otherwise.
4. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
5. **Check**: start the app; its tools menu lists the door's tools; ask one read question.
6. **Smoke**: `python tools/smoke_harness.py --harness claude-desktop --url <door url> --key-file <this harness's key file> --server-name door`.

## Output

Write to `<run folder>/05b-connect-claude-desktop/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
