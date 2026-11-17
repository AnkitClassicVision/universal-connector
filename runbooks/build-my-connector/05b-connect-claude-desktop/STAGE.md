# 05b-connect-claude-desktop

## Purpose

Connect Claude Desktop to the door with its own door key, through a local bridge, without changing anything else and without opening its config.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key file path, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. Never open the config file. The person's yes comes in step 2 of the common steps.

## Where Claude Desktop keeps it

| macOS | Windows | Linux (community builds) |
|---|---|---|
| `~/Library/Application Support/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Quit the app fully first.** It rewrites this file when it quits and would undo the change.
2. **A local bridge.** The JSON file takes local programs only. Use a local stdio bridge that forwards to the door URL and adds the `Authorization` header, reading this harness's key from its 0600 file at start, so the key is not in the JSON. Community bridges exist; check the vendor docs and decide with the person whether to trust one before use.
3. **Add**: `python tools/add_entry.py --harness claude-desktop --config <the file above> --url <door url> --bridge-command <the bridge's path> --key-file <this harness's key file> --backup-dir <run folder>/05b-connect-claude-desktop/backup`. Only the key file's path goes in the entry.
4. **Custom connectors** added in Settings may be reached from the vendor's servers, so a loopback or tailnet door may not be reachable that way. Use the bridge unless the vendor docs say otherwise.
5. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
6. **Check**: start the app; its tools menu lists the door's tools; ask one read question.
7. **Smoke**: `python tools/smoke_harness.py --harness claude-desktop --url <door url> --key-file <this harness's key file> --server-name door --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05b-connect-claude-desktop/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/add_entry.py`, `tools/smoke_harness.py`
