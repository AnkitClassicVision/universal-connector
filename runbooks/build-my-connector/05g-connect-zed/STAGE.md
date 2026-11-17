# 05g-connect-zed

## Purpose

Connect Zed to the door with its own door key, without changing anything else and without opening its settings.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key file, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. Never open `settings.json`. The person's yes comes in step 2 of the common steps.

## Where Zed keeps it

| macOS and Linux | Windows | Project |
|---|---|---|
| `~/.config/zed/settings.json` | `%APPDATA%\Zed\settings.json` | `<project>/.zed/settings.json` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Prefer Zed's own screen**: the agent panel's "add a custom server" (check the vendor docs for your version). The person pastes the door key there.
2. **Otherwise**: `python tools/add_entry.py --harness zed --config ~/.config/zed/settings.json --url <door url> --key-file <Zed's key file> --backup-dir <run folder>/05g-connect-zed/backup`. Zed's settings usually hold comments, so the tool refuses unless the person agrees to `--allow-rewrite`, which writes the file back without comments (the backup keeps them). Newer versions take `url` plus `headers` (check the vendor docs); older ones take local programs only, so use a local bridge as in `05b`.
3. **Plain text**: Zed keeps the door key in its settings. That is expected by design; the file is made owner-only and the next rescan marks it as a door entry.
4. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
5. **Check**: the agent panel shows `door` running with its tools; ask one read question.
6. **Smoke**: `python tools/smoke_harness.py --harness zed --url <door url> --key-file <Zed's key file> --server-name door --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05g-connect-zed/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/add_entry.py`, `tools/smoke_harness.py`
