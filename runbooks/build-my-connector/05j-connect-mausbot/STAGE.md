# 05j-connect-mausbot

## Purpose

Connect OpenMausBot to the door with its own door key, without changing anything else.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; where its config is; server name |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. This stage is a human yes point.

## Where OpenMausBot keeps it

`config.json` in the install's data folder. The place differs per machine, so the interview or the plan records it. Common places: `<install folder>/data/config.json`, `$OPENMAUSBOT_HOME/data/config.json`, `~/.openmausbot/config.json`.

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Stop the app** before editing.
2. **Entry**: `python tools/entry.py --harness openmausbot --url <door url>` prints an `mcpServers` entry with `"type": "http"`, the URL, an `Authorization` header placeholder and `"enabled": true`.
3. **Key**: OpenMausBot keeps the key as plain text in `config.json`. That is acceptable only because it is this harness's own revocable door key, never an upstream key. The person pastes it in place of the placeholder and makes the file readable only by them.
4. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
5. **Check**: start the app; it lists the door's tools; ask one read question.
6. **Smoke**: `python tools/smoke_harness.py --harness openmausbot --url <door url> --key-env <variable or --key-file> --server-name door`.
7. Switching off its own older connectors comes later, as a separate yes, after `06b` passes.

## Output

Write to `<run folder>/05j-connect-mausbot/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
