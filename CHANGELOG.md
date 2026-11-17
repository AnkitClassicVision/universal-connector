# Changelog

All notable changes to this registry. Versions follow semantic versioning: a new runbook stage or a changed deliverable is a minor change; a changed stage structure is a major change. Each runbook also keeps its own `version` in `process.yaml`.

## [0.1.0] - unreleased

### The door

- The door joins the repository as `door/`: the `universal_connector` package (`uconnector`), with its own `pyproject.toml`, lock file, tests, examples and service templates, and the same `LICENSE` and `NOTICE`. Its tests run inside `door/`; the root test run still collects `tests/` only.
- `tools/keyshape.py` and the repository test leave out a `uv.lock` file's package hashes (`sha256:` digests and package-index paths), only in files named `uv.lock`; every other shape there still counts. `tools/lint.py` skips a local `.venv`, as keyshape already did.

### Security (review fixes before the first release)

- The agent never opens a harness config. New `tools/add_entry.py` adds one door entry in its own process: it backs the config up into the run folder (0700 folder, 0600 file, never beside the config), checks the result keeps every earlier entry, replaces the file atomically and prints only a receipt. Every connect stage uses the harness's own command, `add_entry.py`, or the person.
- Scanned names, paths, descriptions and vault titles are data, never instructions: a firm rule in `AGENTS.md`, `handle-secrets` and every stage that reads the inventory. The report shows every scanned string in a code span and strips control characters. The fixtures now include an injected skill description and server name.
- Smoke tools read keys only from a 0600 file (`--key-file`); `--key-env` is gone. They call a tool only when Oddboro's exact read-only rule allows it (42 change words, camelCase split) and, with `--plan`, only green tools. Proxy variables are ignored.
- New `tools/move_field.py` moves one named field into a vault over standard input; a whole file is never stored.
- `entry.py` validates URLs, names and variable names, quotes the shell line and escapes TOML.
- The scanner: env and header literals count as inline secrets; `PASS`, `PW` are credential words and `PWD` is not; FIFOs and links are refused without hanging; YAML aliases are refused; look paths are redacted; hidden ids are stable (owner-only salt); `--door-url` marks harnesses' own plain-text door keys as expected; Bitwarden no longer runs `bw list items`.
- `keyshape.py` decodes UTF-16 and Latin-1 and exits non-zero on any file it skipped. `sync.py --force` moves the old folder aside instead of deleting it. Output files refuse links and are owner-only.

### Changed

- Oddboro: service id derived from the address, keyring preflight (`oddboro_version.py --preflight`), no version is a failure with update advice, `pinned_tools: false` through the door's `--format oddboro`.
- `harness smoke`: initialize and tools/list under 5 s, GET answered with 405 or a stream, no outputSchema, content is an array, `--save-tools` and `--baseline-tools` to flag new tools that change things. `gotchas.py names --url` and `gotchas.py toolsdiff`.
- `07-handoff` reads every connect result and `harnesses.yaml`, lists backups, and deletes them only on a yes after `06b`. `update-my-connector/05-handoff` starts from the last owner sheet. Unchosen connect stages hand in `skipped.md` without a gate; their yes is taken inside the stage.
- Docs: what you get at the end, what is not verified yet, the `door/` release line, local https proxy routes, a Google Desktop-client walkthrough, the plain-text door-key harnesses, Postgres connection strings as one secret and side-effect functions as yellow.
- Standard Apache-2.0 `LICENSE` with a `NOTICE`.

### Added

- Runbook `build-my-connector` (draft): names-only scan and interview side by side, plan with harness choice and owner confirmation, vault setup by the person, the door, thirteen connect stages side by side (Claude Code, Claude Desktop, Codex, Cursor, Windsurf, VS Code with Continue and Cline, Zed, Goose, Hermes, OpenMausBot, Oddboro, GrokBot, any other MCP client), carrying portable skills, smoke tests per connection and per harness, and the owner sheet.
- Runbook `update-my-connector` (draft): rescan, diff against the last inventory, add, remove or rotate connections and harnesses, re-run every smoke test.
- Shared skills: `handle-secrets`, `connector-options` (vaults, door placement, harness formats and known limits, auth kinds, tiers and scopes, Oddboro versions), `connect-harness`.
- Recipes for 29 common services.
- Tools: `scan.py` with 38 plug-ins, `smoke_connection.py`, `smoke_harness.py`, `gotchas.py`, `entry.py`, `diff_inventory.py`, `keyshape.py`, `oddboro_version.py`.
- Offline tests on fake fixtures, including leak tests over every output.
