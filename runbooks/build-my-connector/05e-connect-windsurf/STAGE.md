# 05e-connect-windsurf

## Purpose

Connect Windsurf to the door with its own door key, without changing anything else and without opening its config.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key file, key variable, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. Never open `mcp_config.json`. The person's yes comes in step 2 of the common steps.

## Where Windsurf keeps it

| macOS and Linux | Windows |
|---|---|
| `~/.codeium/windsurf/mcp_config.json` | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Quit Windsurf** before the change.
2. **Add**: `python tools/add_entry.py --harness windsurf --config ~/.codeium/windsurf/mcp_config.json --url <door url> --key-env WINDSURF_DOOR_KEY --backup-dir <run folder>/05e-connect-windsurf/backup`. Remote servers use the key `serverUrl`. Check the vendor docs that your version expands `${env:...}`; if not, run it with `--key-file <Windsurf's key file> --replace`: a plain-text door key, expected by design.
3. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
4. **Limits**: Windsurf caps the total number of tools across servers (check the vendor docs). The door's short tool list helps.
5. **Check**: refresh the MCP panel; `door` shows its tools; ask one read question.
6. **Smoke**: `python tools/smoke_harness.py --harness windsurf --url <door url> --key-file <Windsurf's key file> --server-name door --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05e-connect-windsurf/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/add_entry.py`, `tools/smoke_harness.py`
