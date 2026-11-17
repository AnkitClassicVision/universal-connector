# 05j-connect-mausbot

## Purpose

Connect OpenMausBot to the door with its own door key, without changing anything else and without opening its config.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; where its config is; server name, key file |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. Never open `config.json`. The person's yes comes in step 2 of the common steps.

## Where OpenMausBot keeps it

`config.json` in the install's data folder. The place differs per machine, so the interview or the plan records it. Common places: `<install folder>/data/config.json`, `$OPENMAUSBOT_HOME/data/config.json`, `~/.openmausbot/config.json`.

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Stop the app** before the change.
2. **Add**: `python tools/add_entry.py --harness openmausbot --config <its config.json> --url <door url> --key-file <OpenMausBot's key file> --backup-dir <run folder>/05j-connect-mausbot/backup`. It adds an `mcpServers` entry with `"type": "http"`, the URL, the `Authorization` header and `"enabled": true`.
3. **Plain text**: OpenMausBot keeps the key as plain text in `config.json`. That is acceptable only because it is this harness's own revocable door key, never an upstream key. `add_entry.py` writes it in its own process and makes the file owner-only; the next rescan marks it as a door entry.
4. **Read timeout**: no documented setting. Record "unknown: check the vendor docs".
5. **Check**: start the app; it lists the door's tools; ask one read question.
6. **Smoke**: `python tools/smoke_harness.py --harness openmausbot --url <door url> --key-file <OpenMausBot's key file> --server-name door --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.
7. Switching off its own older connectors comes later, as a separate yes, after `06b` passes.

## Output

Write to `<run folder>/05j-connect-mausbot/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/add_entry.py`, `tools/smoke_harness.py`
