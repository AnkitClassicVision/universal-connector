# 06b-smoke-harnesses

## Purpose

Prove each connected harness works with the door on its own key, that the door refuses what it must, that a revoked key stops working, and that the known gotchas are covered.

## Inputs

| Source | Location | Why |
|---|---|---|
| Connect results | `<run folder>/05a-connect-claude-code/output/` to `<run folder>/05m-connect-other/output/` | Which harnesses are connected, their URLs, server names, key variables and read timeouts |
| Formats and limits | `skills/connector-options/references/harnesses.md` | Each harness's limits |

Read only what is listed here. Skip every connect stage whose output is `skipped.md`.

## Process

For each connected harness (and each VS Code agent, Hermes profile or other client), on its own:

1. **Re-run the harness smoke test** with its live key: `python tools/smoke_harness.py --harness <id> --url <its url> --key-env <its key variable> --server-name <its server name> --read-timeout <its read timeout> --json`. Save it as `harnesses/<id>.json`.
2. **Revoke check, without breaking the live key**: the person issues a second, temporary door key for this harness (`<id>-canary`), you run `smoke_harness.py` with it once (it must pass), the person revokes it with the door's own command, and you run `smoke_harness.py ... --expect-revoked` with it. Save both as `harnesses/<id>-canary.json` and `harnesses/<id>-revoked.json`.
3. **Read limit**: `python tools/gotchas.py timeout --door-worst-case <seconds from 04-door> --read-timeout <its read timeout>`.
4. **Route Host** (harnesses on the https route): `python tools/gotchas.py host --route-host <host> --door-hosts <list>`.
5. **In-harness check** again: the harness lists the door's tools and answers one read question; for Oddboro, the service shows Connected and the door's audit shows the Odd's calls.
6. A failing harness does not stop the others. Record the failing check, then go on.
7. Write `smoke-harnesses.md`.

## Output

Write to `<run folder>/06b-smoke-harnesses/output/`. `deliverable.md` says what must be in it.

## Uses

- `tools/smoke_harness.py`, `tools/gotchas.py`
- `skills/connector-options`, `skills/handle-secrets`
