# 05c-connect-codex

## Purpose

Connect Codex to the door with its own door key, held by reference, without changing anything else.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; server name, key variable, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL and slowest call |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entry and its limits |

Read only what is listed here. This stage is a human yes point.

## Where Codex keeps it

| macOS and Linux | Windows |
|---|---|
| `~/.codex/config.toml`, or `$CODEX_HOME/config.toml` when that variable is set | `%USERPROFILE%\.codex\config.toml` |

Newer versions also read `<project>/.codex/config.toml` in trusted projects. Use the user file unless the person wants the door in one project only.

## Process

Follow `skills/connect-harness`. The harness-specific parts:

1. **Entry**: `python tools/entry.py --harness codex --url <door url> --key-env CODEX_DOOR_KEY --read-timeout <seconds>`. Add the `[mcp_servers.door]` table to the file with the editing tool, or with your version's `codex mcp` command if it has one (check the vendor docs).
2. **Key**: `bearer_token_env_var = "CODEX_DOOR_KEY"` makes Codex read the key from that variable. The person makes it available in the environment Codex starts with.
3. **Read timeout**: `tool_timeout_sec` (default 60) above the door's slowest call.
4. **Older versions** need `experimental_use_rmcp_client = true` at the top of the file for remote servers. Check the vendor docs for yours.
5. **Check**: in Codex, list MCP servers (`/mcp` in the terminal UI) and see `door` with its tools; ask one read question.
6. **Smoke**: `python tools/smoke_harness.py --harness codex --url <door url> --key-env CODEX_DOOR_KEY --server-name door --read-timeout <seconds>`.

## Output

Write to `<run folder>/05c-connect-codex/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
