# 05f-connect-vscode

## Purpose

Connect VS Code to the door: its native MCP support, and the Continue or Cline extension if the person uses one. Each one that will use the door is its own agent with its own door key.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; which of native, Continue and Cline; server name, keys, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entries and their limits |

Read only what is listed here. This stage is a human yes point.

## Where each keeps it

| Agent | Linux | macOS | Windows |
|---|---|---|---|
| VS Code native (user) | `~/.config/Code/User/mcp.json` | `~/Library/Application Support/Code/User/mcp.json` | `%APPDATA%\Code\User\mcp.json` |
| VS Code native (workspace) | `<project>/.vscode/mcp.json` | same | same |
| Cline | `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json` |
| Continue | `~/.continue/config.yaml` | same | `%USERPROFILE%\.continue\config.yaml` |

VS Code Insiders and VSCodium use the same files under their own folder names.

## Process

Follow `skills/connect-harness` once for each agent the plan chose, each with its own backup, key and smoke test. The harness-specific parts:

1. **VS Code native**: `python tools/entry.py --harness vscode --url <door url>`. It uses the top-level key `servers` (not `mcpServers`) and an `inputs` entry with `password: true`, so VS Code asks for the key once and stores it itself. The person pastes the key into VS Code's prompt. You can also add it with the command "MCP: Add Server".
2. **Cline**: add an `mcpServers` entry with `url`, `headers` and `timeout` (seconds, default 60) through Cline's MCP Servers panel. Check the vendor docs for the transport field your version needs. The key sits in Cline's settings file; use Cline's own door key only.
3. **Continue**: add an `mcpServers` item with `type: streamable-http`, `url` and `requestOptions.headers`, using Continue's secrets templating if available (check the vendor docs).
4. **Read timeout**: Cline's `timeout`; others: record "unknown: check the vendor docs".
5. **Check**: each agent lists the door's tools and answers one read question.
6. **Smoke**, once per agent: `python tools/smoke_harness.py --harness vscode --url <door url> --key-env <that agent's key variable> --server-name door`.

## Output

Write to `<run folder>/05f-connect-vscode/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
