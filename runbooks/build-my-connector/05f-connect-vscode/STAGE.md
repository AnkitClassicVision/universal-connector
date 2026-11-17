# 05f-connect-vscode

## Purpose

Connect VS Code to the door: its native MCP support, and the Continue or Cline extension if the person uses one. Each one that will use the door is its own agent with its own door key. No config is opened by the agent.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; which of native, Continue and Cline; server name, keys, read timeout |
| Door | `<run folder>/04-door/output/door.md` | The door URL |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, add, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The entries and their limits |

Read only what is listed here. Never open these files. The person's yes comes in step 2 of the common steps, once per agent.

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

1. **VS Code native**: prefer VS Code's own command "MCP: Add Server" (the person runs it). Otherwise `python tools/add_entry.py --harness vscode --config <user mcp.json> --url <door url> --backup-dir <run folder>/05f-connect-vscode/backup`. It adds a `servers` entry and an `inputs` entry with `password: true`, so VS Code asks for the key once and stores it itself; the person pastes the key into VS Code's own prompt. If the file has comments, `add_entry.py` refuses; use the command, or pass `--allow-rewrite` with the person's yes (comments are lost; the backup keeps them).
2. **Cline**: `python tools/add_entry.py --harness cline --config <Cline's file> --url <door url> --key-file <Cline's key file> --read-timeout <seconds> --backup-dir <run folder>/05f-connect-vscode/backup`, or Cline's own MCP Servers panel. Cline keeps the key in its settings file: a plain-text door key, expected by design.
3. **Continue**: add the server in Continue's own settings (check the vendor docs for `type: streamable-http`, `url` and headers or secrets templating). `add_entry.py` does not edit Continue's list.
4. **Read timeout**: Cline's `timeout`; others: record "unknown: check the vendor docs".
5. **Check**: each agent lists the door's tools and answers one read question.
6. **Smoke**, once per agent: `python tools/smoke_harness.py --harness vscode --url <door url> --key-file <that agent's key file> --server-name door --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05f-connect-vscode/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/add_entry.py`, `tools/smoke_harness.py`
