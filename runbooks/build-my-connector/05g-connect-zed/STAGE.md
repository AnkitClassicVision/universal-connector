# 05g-connect-zed

## Purpose

Connect Zed to the door with its own door key, without changing anything else.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key holding, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. This stage is a human yes point.

## Where Zed keeps it

| macOS and Linux | Windows | Project |
|---|---|---|
| `~/.config/zed/settings.json` | `%APPDATA%\Zed\settings.json` | `<project>/.zed/settings.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Edit with care**: the file allows comments and trailing commas. Add one entry under `context_servers` and keep every other line as it was.
2. **Entry**: newer versions take a remote server as `url` plus `headers` (check the vendor docs). `python tools/entry.py --harness zed --url <door url>` prints that shape with a placeholder. The person pastes this harness's door key in place of the placeholder themselves. If your version takes local programs only, use a local bridge as in `05b-connect-claude-desktop`.
3. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
4. **Check**: the agent panel shows `door` running with its tools; ask one read question.
5. **Smoke**: `python tools/smoke_harness.py --harness zed --url <door url> --key-env <variable or --key-file> --server-name door`.

## Output

Write to `<run folder>/05g-connect-zed/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
