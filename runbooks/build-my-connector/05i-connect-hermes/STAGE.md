# 05i-connect-hermes

## Purpose

Connect Hermes to the door. Each Hermes profile the plan chose is its own agent, with its own entry and its own door key. No config or `.env` file is opened by the agent.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; which profiles; server name, key files, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL and slowest call |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. The person's yes comes in step 2 of the common steps, once per profile.

## Where Hermes keeps it

| What | Place |
|---|---|
| Main config | `~/.hermes/config.yaml`, or under `$HERMES_HOME` when that variable is set |
| One profile | `~/.hermes/profiles/<profile>/config.yaml` |
| Variables | `~/.hermes/.env`, and `profiles/<profile>/.env` |

## Process

Follow `skills/connect-harness` once per chosen profile. The harness-specific parts:

1. **Add**: `python tools/add_entry.py --harness hermes --config <that profile's config.yaml> --url <door url> --key-env HERMES_DOOR_KEY --read-timeout <seconds> --backup-dir <run folder>/05i-connect-hermes/backup`. It inserts one entry under `mcp_servers`, keeping comments, with `Authorization: "Bearer ${HERMES_DOOR_KEY}"`.
2. **Key**: the person puts this profile's door key into that profile's `.env` as `HERMES_DOOR_KEY`, themselves, in their own editor, from the profile's 0600 key file. The agent never opens `.env`. Check the vendor docs that your version expands `${...}`; if it does not, run `add_entry.py` with `--key-file` and `--replace` instead.
3. **Read timeout**: `timeout` on the entry (and `connect_timeout` if your version has it; check the vendor docs), above the door's slowest call.
4. **Check**: restart Hermes for that profile; it lists the door's tools; ask one read question.
5. **Smoke**, once per profile: `python tools/smoke_harness.py --harness hermes --url <door url> --key-file <that profile's key file> --server-name door --read-timeout <seconds> --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05i-connect-hermes/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/add_entry.py`, `tools/smoke_harness.py`
