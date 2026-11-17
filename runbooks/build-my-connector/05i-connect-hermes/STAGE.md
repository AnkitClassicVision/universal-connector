# 05i-connect-hermes

## Purpose

Connect Hermes to the door. Each Hermes profile the plan chose is its own agent, with its own entry and its own door key.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; which profiles; server name, keys, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL and slowest call |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. This stage is a human yes point.

## Where Hermes keeps it

| What | Place |
|---|---|
| Main config | `~/.hermes/config.yaml`, or under `$HERMES_HOME` when that variable is set |
| One profile | `~/.hermes/profiles/<profile>/config.yaml` |
| Variables | `~/.hermes/.env`, and `profiles/<profile>/.env` |

## Process

Follow `skills/connect-harness` once per chosen profile. The harness-specific parts:

1. **Entry**: `python tools/entry.py --harness hermes --url <door url> --key-env HERMES_DOOR_KEY --read-timeout <seconds>` prints an `mcp_servers` entry with `Authorization: "Bearer ${HERMES_DOOR_KEY}"`.
2. **Key**: the person puts this profile's door key into that profile's `.env` as `HERMES_DOOR_KEY`, themselves. Check the vendor docs that your version expands `${...}` in `config.yaml`; if it does not, the person pastes the key into the entry and makes the file readable only by them.
3. **Read timeout**: `timeout` on the entry (and `connect_timeout` if your version has it; check the vendor docs), above the door's slowest call.
4. **Check**: restart Hermes for that profile; it lists the door's tools; ask one read question.
5. **Smoke**, once per profile: `python tools/smoke_harness.py --harness hermes --url <door url> --key-env <that profile's key variable> --server-name door --read-timeout <seconds>`.

## Output

Write to `<run folder>/05i-connect-hermes/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
