# 05c-connect-codex

## Purpose

Connect Codex to the door with its own door key, held by reference, without changing anything else and without opening its config.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key file, key variable, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL and slowest call |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. Never open `config.toml`. The person's yes comes in step 2 of the common steps.

## Where Codex keeps it

| macOS and Linux | Windows |
|---|---|
| `~/.codex/config.toml`, or `$CODEX_HOME/config.toml` when that variable is set | `%USERPROFILE%\.codex\config.toml` |

Newer versions also read `<project>/.codex/config.toml` in trusted projects. Use the user file unless the person wants the door in one project only.

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Add**: if your version has `codex mcp add` with a URL option (check the vendor docs), use it. Otherwise: `python tools/add_entry.py --harness codex --config ~/.codex/config.toml --url <door url> --key-env CODEX_DOOR_KEY --read-timeout <seconds> --backup-dir <run folder>/05c-connect-codex/backup`. It appends one `[mcp_servers.door]` table.
2. **Key**: `bearer_token_env_var = "CODEX_DOOR_KEY"` makes Codex read the key from that variable. The person makes it available to Codex from Codex's 0600 key file; the agent never reads or sets it.
3. **Read timeout**: `tool_timeout_sec` (default 60) above the door's slowest call; `add_entry.py` writes it from `--read-timeout`.
4. **Older versions** need `experimental_use_rmcp_client = true` at the top of the file for remote servers. Check the vendor docs; the person adds that line in Codex's own settings if needed.
5. **Check**: in Codex, list MCP servers (`/mcp` in the terminal UI) and see `door` with its tools; ask one read question.
6. **Smoke**: `python tools/smoke_harness.py --harness codex --url <door url> --key-file <Codex's key file> --server-name door --read-timeout <seconds> --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05c-connect-codex/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/add_entry.py`, `tools/smoke_harness.py`
