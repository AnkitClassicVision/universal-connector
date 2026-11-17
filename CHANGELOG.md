# Changelog

All notable changes to this registry. Versions follow semantic versioning: a new runbook stage or a changed deliverable is a minor change; a changed stage structure is a major change. Each runbook also keeps its own `version` in `process.yaml`.

## [0.1.0] - 2026-11-17

### Added

- Runbook `build-my-connector` (draft): names-only scan and interview side by side, plan with harness choice and owner confirmation, vault setup by the person, the door, thirteen connect stages side by side (Claude Code, Claude Desktop, Codex, Cursor, Windsurf, VS Code with Continue and Cline, Zed, Goose, Hermes, OpenMausBot, Oddboro, GrokBot, any other MCP client), carrying portable skills, smoke tests per connection and per harness, and the owner sheet.
- Runbook `update-my-connector` (draft): rescan, diff against the last inventory, add, remove or rotate connections and harnesses, re-run every smoke test.
- Shared skills: `handle-secrets`, `connector-options` (vaults, door placement, harness formats and known limits, auth kinds, tiers and scopes, Oddboro versions), `connect-harness`.
- Recipes for 29 common services.
- Tools: `scan.py` with 38 plug-ins, `smoke_connection.py`, `smoke_harness.py`, `gotchas.py`, `entry.py`, `diff_inventory.py`, `keyshape.py`, `oddboro_version.py`.
- Offline tests on fake fixtures, including leak tests over every output.
