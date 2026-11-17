# 05h-connect-goose

## Purpose

Connect Goose to the door with its own door key, without changing anything else.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key holding, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL and slowest call |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. This stage is a human yes point.

## Where Goose keeps it

| macOS and Linux | Windows |
|---|---|
| `~/.config/goose/config.yaml` | `%APPDATA%\Block\goose\config\config.yaml` |

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Entry**: prefer Goose's own `goose configure` menu (add a remote extension over streamable HTTP; check the vendor docs for your version). `python tools/entry.py --harness goose --url <door url>` prints the YAML shape with a placeholder, under `extensions`.
2. **Key**: the person enters this harness's door key in Goose's own prompt or pastes it in place of the placeholder. Check the vendor docs for whether your version keeps header values in the keyring.
3. **Read timeout**: `timeout` on the extension, in seconds (default 300), above the door's slowest call.
4. **Check**: start a session; the `door` extension is enabled with its tools; ask one read question.
5. **Smoke**: `python tools/smoke_harness.py --harness goose --url <door url> --key-env <variable or --key-file> --server-name door --read-timeout <seconds>`.

## Output

Write to `<run folder>/05h-connect-goose/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
