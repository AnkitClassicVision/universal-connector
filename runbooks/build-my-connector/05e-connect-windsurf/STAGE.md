# 05e-connect-windsurf

## Purpose

Connect Windsurf to the door with its own door key, without changing anything else.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key variable, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. This stage is a human yes point.

## Where Windsurf keeps it

| macOS and Linux | Windows |
|---|---|
| `~/.codeium/windsurf/mcp_config.json` | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Quit Windsurf** before editing.
2. **Entry**: `python tools/entry.py --harness windsurf --url <door url> --key-env WINDSURF_DOOR_KEY`. Remote servers use the key `serverUrl`. Check the vendor docs that your version expands `${env:...}`; if it does not, the person pastes this harness's door key into the file and makes the file readable only by them.
3. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
4. **Limits**: Windsurf caps the total number of tools across servers (check the vendor docs). The door's short tool list helps.
5. **Check**: refresh the MCP panel; `door` shows its tools; ask one read question.
6. **Smoke**: `python tools/smoke_harness.py --harness windsurf --url <door url> --key-env WINDSURF_DOOR_KEY --server-name door`.

## Output

Write to `<run folder>/05e-connect-windsurf/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
