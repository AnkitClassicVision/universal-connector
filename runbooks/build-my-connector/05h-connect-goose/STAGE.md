# 05h-connect-goose

## Purpose

Connect Goose to the door with its own door key, without changing anything else and without opening its config.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key file, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL and slowest call |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. Never open `config.yaml`. The person's yes comes in step 2 of the common steps.

## Where Goose keeps it

| macOS and Linux | Windows |
|---|---|
| `~/.config/goose/config.yaml` | `%APPDATA%\Block\goose\config\config.yaml` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Prefer Goose's own menu**: `goose configure`, add a remote extension over streamable HTTP (check the vendor docs for your version). The person types the door key into Goose's own prompt.
2. **Otherwise**: `python tools/add_entry.py --harness goose --config ~/.config/goose/config.yaml --url <door url> --key-file <Goose's key file> --read-timeout <seconds> --backup-dir <run folder>/05h-connect-goose/backup`. It inserts one entry under `extensions`, keeping comments.
3. **Plain text**: Goose keeps a header value in its config: a plain-text door key, expected by design. The file is made owner-only and the next rescan marks it as a door entry.
4. **Read timeout**: `timeout` on the extension, in seconds (default 300), above the door's slowest call.
5. **Check**: start a session; the `door` extension is enabled with its tools; ask one read question.
6. **Smoke**: `python tools/smoke_harness.py --harness goose --url <door url> --key-file <Goose's key file> --server-name door --read-timeout <seconds> --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05h-connect-goose/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/add_entry.py`, `tools/smoke_harness.py`
