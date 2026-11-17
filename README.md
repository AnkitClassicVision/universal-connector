# Universal Connector

Gather the connections you already have (MCP servers, API keys, OAuth sign-ins, skills) into one portable connector, the **door**, and plug every agent harness you use into it: Claude Code, Codex, Oddboro, Cursor, VS Code, Hermes and more. One door, one revocable key per harness, and secrets that stay in your own vault.

This repo is a **runbook registry**. An agent in Claude Code or Codex reads it and walks you through the work, one stage at a time, asking for your yes before every change. It holds:

- `runbooks/build-my-connector`: scan, interview, plan, vault, door, connect each harness side by side, smoke-test, hand over.
- `runbooks/update-my-connector`: rescan, diff against last time, add, remove or rotate, re-test.
- `skills/`: the secret rules, the options guide (vaults, door placement, harness formats and known limits, auth kinds, tiers and scopes, Oddboro versions) and the connect-one-harness steps.
- `recipes/`: one short file per common service: auth kinds, MCP server status, tiers, scopes and a one-read smoke test.
- `tools/`: the scanner, the smoke tests and helpers, in Python with the standard library plus PyYAML.

The door itself is a separate program. Stage `04-door` lists what any door must do, and the smoke tests check it.

## Run it

You need Python 3.11 or newer and PyYAML (`pip install pyyaml`).

**Claude Code**: open this folder and ask "Run build-my-connector". `CLAUDE.md` loads `AGENTS.md`, which routes the request through `ROUTE.md`.

**Codex**: open this folder and ask the same. Codex reads `AGENTS.md`.

You can also run the tools yourself:

```bash
python tools/scan.py --list-sources                  # every plug-in and where it looks
python tools/scan.py --out ./my-scan                 # inventory.json and inventory.md, names only
python tools/scan.py --include-vaults --out ./my-scan  # also password-manager entry names, only if unlocked
python tools/entry.py --harness codex --url http://127.0.0.1:8765/mcp --key-env CODEX_DOOR_KEY
python tools/smoke_connection.py --help
python tools/smoke_harness.py --help
```

## Safety model

- **Names, never values.** The scanner reads config files in its own process to classify where each key lives (inline, environment reference, file, keyring, vault, OAuth, browser session). It never prints, logs, stores or returns a value. Every output passes a key-shape guard and the tool stops rather than print a match.
- **You do every secret step.** You create keys in each vendor's console, store them with your vault's own command in your own terminal, and sign in through your browser. The agent prepares names and commands and waits.
- **No passwords, ever.** The kit never asks for, collects, stores, prints or moves a password, one-time code or recovery code. They stay in your password manager.
- **One key per harness.** Revoking one harness never affects another. The door refuses requests with no key, a wrong key, a browser `Origin` header, or a Host it does not list.
- **Your yes before every change.** Each vault write, the door's service install and each harness config edit wait for you. Every config edit makes a backup first.
- **Nothing leaves your machine** except the smoke tests' calls to your own door, and your own sign-ins.
- **Blind QA.** Quality criteria live in a separate repo, `universal-connector-qa`, so the agent doing the work cannot aim at the test.

The door does not sandbox a harness. A program running as you can already read your files; the door's promise is that no harness needs an upstream key in its config and no agent ever sees one.

## What the scanner looks at

Run `python tools/scan.py --list-sources` for the exact places on your machine. Every plug-in tolerates missing and malformed files.

| Group | Plug-ins |
|---|---|
| Agent harnesses | `claude-code` (user and project `.mcp.json`, `~/.claude.json`, settings, plugins, managed config, OAuth sign-in names), `claude-desktop` (config and extensions), `codex`, `cursor`, `windsurf`, `vscode`, `cline`, `continue`, `zed`, `goose`, `hermes` (and profiles), `openmausbot`, `oddboro` (office home and tool accounts; services are read from its Services tab), `grokbot`, `extra` (any file you name) |
| Skills | `skills`: Claude Code, plugin skills, Codex, Hermes and profiles, `~/.agents/skills`, project skill folders. Names and one-line descriptions only, each classed as external-api, portable-instructions or harness-specific |
| Environment | `env` (credential-looking variable names), `env-files` (`.env` files), `shell-profiles` |
| CLI sign-ins | `gh`, `gcloud`, `aws`, `azure`, `docker`, `kube`, `npm`, `pypi`, `netrc`, `git-credentials`: presence and names only |
| Vaults, opt-in | `1password`, `bitwarden`, `pass`, `gopass`, `keychain`, `windows-credentials`, `secret-service`: entry names only, only with `--include-vaults`, only if already unlocked |
| Running | `ports` (listening local ports and program names; nothing is probed), `browsers` (profile counts) |

## Tests

```bash
python -m pytest -q        # offline, fixtures only; no network, no real configs
ruff check tools tests
python tools/keyshape.py . # no key-shaped string in the repo
python tools/lint.py . --qa ../universal-connector-qa --summary
```

The tests plant distinct fake values in every source and assert that no 8-character slice of any of them reaches the scanner's output, its files, or the smoke tests' output.

## Status

Version 0.1.0, draft. The runbooks have not yet passed their gates on a real run, so their status is `draft`. Rows in the harness limits table are marked by source; anything marked "check the vendor docs" is not verified here.

## License

Apache-2.0. See `LICENSE`.
