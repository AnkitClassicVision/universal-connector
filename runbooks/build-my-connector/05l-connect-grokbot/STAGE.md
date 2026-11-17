# 05l-connect-grokbot

## Purpose

Connect GrokBot to the door, with its own door key where its CLI allows, and list its desktop logins as hosted.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key holding |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. If the plan did not choose GrokBot, write `output/skipped.md` and stop; otherwise the person's yes comes before any change, as in the common steps.

## Where GrokBot keeps it

| Part | Place |
|---|---|
| CLI | Reads Claude Code's MCP list. Its own `~/.grok/config.toml` (or `$GROK_HOME/config.toml`) may hold `mcp_servers` |
| Desktop app | Its connector logins are kept on the vendor's servers |

## Process

1. **Prefer its own entry.** If the person's GrokBot CLI has its own command to add an MCP server (check the vendor docs), follow `skills/connect-harness` with that command and a GrokBot door key of its own, so revoking Claude Code's key never cuts GrokBot. The agent never opens `~/.grok/config.toml`; `add_entry.py` does not support this file, so with no command of its own, the person adds the entry in GrokBot's own settings.
2. **Otherwise** it shares Claude Code's entry from `05a`. Write that in `connect.md` and in the owner sheet notes: revoking Claude Code's door key also cuts GrokBot's CLI. Nothing changes here.
3. **Desktop app**: list its connectors as "hosted, not portable yet". The door is not reachable from the vendor's servers.
4. **Check**: the CLI lists the door's tools; ask one read question.
5. **Smoke** (own entry only): `python tools/smoke_harness.py --harness grokbot --url <door url> --key-file <GrokBot's key file> --server-name door --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05l-connect-grokbot/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
