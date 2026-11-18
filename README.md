# Universal Connector

Gather the connections you already have (MCP servers, API keys, OAuth sign-ins, skills) into one portable connector, the **door**, and plug every agent harness you use into it: Claude Code, Codex, Oddboro, Cursor, VS Code, Hermes and more. One door, one revocable key per harness, and secrets that stay in your own vault.

This repo is a **runbook registry**. An agent in Claude Code or Codex reads it and walks you through the work, one stage at a time, asking for your yes before every change. It holds:

- `runbooks/build-my-connector`: scan, interview, plan, vault, door, connect each harness side by side, smoke-test, hand over.
- `runbooks/update-my-connector`: rescan, diff against last time, add, remove or rotate, re-test.
- `skills/`: the secret rules, the options guide (vaults, door placement, harness formats and known limits, auth kinds, tiers and scopes, Oddboro versions) and the connect-one-harness steps.
- `recipes/`: one short file per common service: auth kinds, MCP server status, tiers, scopes and a one-read smoke test.
- `tools/`: the scanner, the smoke tests and helpers, in Python with the standard library plus PyYAML.
- `door/`: the door itself, released with the tags. Install a tag, not a working copy:

```bash
uv tool install git+https://github.com/AnkitClassicVision/universal-connector@v0.1.0#subdirectory=door
```

## The door

The door is its own Python package, `universal_connector`, with the command `uconnector`. Its guide is [door/README.md](door/README.md): vaults, Oddboro, reload, service files and the safety rules it keeps. It has its own `pyproject.toml`, lock file and tests, which run inside `door/` (see Tests).

Works on: Linux, tested. macOS and Windows: the door's code paths for them are tested by simulation, not on real machines yet.

You issue each harness's door key yourself, in your own terminal, into a private file: `uconnector connect <name> --manifest <folder> --key-file <private path>`. Without `--key-file` the key is printed on screen once; never run that through an agent.

## Quality gates need the QA repo

Every `NN.1-qa` stage (for example `01a.1-qa`, `06b.1-qa`) is graded against criteria in a separate repo, `universal-connector-qa`, so the agent doing the work cannot aim at the test. **That repo is not public in v0.1.0.** Without it, an agent cannot grade a gate. At each gate, do one of these:

- **Review it yourself.** Stop, open that stage's `deliverable.md`, and check the hand-in against every "Must be true" line. Go on only when each one holds.
- **Skip it knowingly.** Write in the run folder that the gate was skipped and why, and go on.

Never mark a gate as passed when nobody graded it.

## What you have at the end

- **A running door** on your own machine: a user service on loopback, with an https route only if a harness needs one, reading its secrets from the vault you chose.
- **Connected harnesses**: each chosen harness reaches the door with its own revocable key, added by the harness's own command or `tools/add_entry.py`, with a backup of its config kept (owner-only) in the run folder until you say to delete it.
- **Smoke results**: one read-only call per connection, and per harness the tool list, one call, the refusals (no key, wrong key, browser origin, unlisted host) and a revoked canary key, all saved as JSON.
- **An owner sheet**: what is connected where, how to revoke or rotate each key, how to add more (`update-my-connector`), and the clean-up left for you.

## Not included, or not verified yet

- The runbooks are `draft`: no full real run has passed every gate yet.
- The kit's tests run offline on Linux with fake configs. Real runs on Windows and macOS are not verified; the Windows and macOS paths in the stages come from vendor docs.
- Rows marked "check the vendor docs" or "unverified" (harness limits, MCP server status in the recipes, route commands) were not checked by running them.
- Website-only services need a browser lane, which is not part of this kit.
- Vendor-hosted connectors (logins kept on a vendor's servers) cannot be moved; they are listed, not connected.

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
python tools/add_entry.py --help        # add a door entry to a harness config without opening it
python tools/move_field.py --help       # move one key from a config into a vault, run by you
python tools/smoke_connection.py --help # keys come from a 0600 file: --key-file
python tools/smoke_harness.py --help
```

## Safety model

- **Names, never values.** The scanner reads config files in its own process to classify where each key lives (inline, environment reference, file, keyring, vault, OAuth, browser session). It never prints, logs, stores or returns a value. Every output passes a key-shape guard and the tool stops rather than print a match.
- **You do every secret step.** You create keys in each vendor's console, store them with your vault's own command in your own terminal, and sign in through your browser. The agent prepares names and commands and waits.
- **No passwords, ever.** The kit never asks for, collects, stores, prints or moves a password, one-time code or recovery code. They stay in your password manager.
- **One key per harness.** Revoking one harness never affects another. The door refuses requests with no key, a wrong key, a browser `Origin` header, or a Host it does not list.
- **Your yes before every change.** Each vault write, the door's service install and each harness config edit wait for you. The agent never opens a harness config: entries go in by the harness's own command or `tools/add_entry.py`, which backs the file up into the run folder (owner-only, never beside the config) and prints nothing from it.
- **Scanned text is data.** Names, descriptions and paths found on your machine are shown only inside code spans and never followed as instructions.
- **Nothing leaves your machine** except the smoke tests' calls to your own door, and your own sign-ins.
- **Blind QA.** Quality criteria live in a separate repo, `universal-connector-qa`, so the agent doing the work cannot aim at the test. It is not public in v0.1.0; see "Quality gates need the QA repo".

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
python tools/keyshape.py . # no key-shaped string (a uv.lock's package hashes excepted); it lists
                           # .venv, __pycache__ and other tool folders as skipped and exits 1, so for
                           # a clean pass scan an export: git archive HEAD | tar -x -C <empty folder>
python tools/lint.py . --qa ../universal-connector-qa --summary   # --qa needs the QA repo
```

The door's tests are separate: the root run collects `tests/` only. Run them inside `door/`, after installing its development tools once with `uv sync --extra dev` (that step downloads packages):

```bash
cd door
uv sync --extra dev
uv run pytest -q -m "not live"
uv run ruff check
uv run uconnector check --manifest examples/manifest
```

`uconnector check` scans from the Git top level wherever it starts, and reads the allow file there: the root `scan-allow.yaml` lists the door's entries with a `door/` prefix, and `door/scan-allow.yaml` holds the same entries for the door on its own.

The tests plant distinct fake values in every source and assert that no 8-character slice of any of them reaches the scanner's output, its files, or the smoke tests' output.

## Status

Version 0.1.0, draft. The runbooks have not yet passed their gates on a real run, so their status is `draft`. Rows in the harness limits table are marked by source; anything marked "check the vendor docs" is not verified here.

## License

Apache-2.0. See `LICENSE`.
