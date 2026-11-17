# Oddboro: versions, address rules and the smoke test

The person's Oddboro may differ from any example. Find their version first.

## Find the version

In this order:

1. Oddboro's Setup window, Updates section: "the version this is".
2. `python tools/oddboro_version.py`: asks the local office at `http://127.0.0.1:<ODDBORO_PORT or 4500>/api/health` (field `version`, v0.0.11 and later). The desktop app may refuse it without its app key; a source run says `development`.
3. For a source checkout: `python tools/oddboro_version.py --checkout <folder>` runs `git describe --tags`.

A "Takes a key" button in the add-service form means v0.0.6 or later.

## Per version

This table is generated from `tools/kit/oddboro.py`; a test keeps the two equal.

<!-- oddboro:start -->
| Oddboro version | Pasted key | How Odds' calls reach the door | New door tools reach an existing Read grant by | Note |
|---|---|---|---|---|
| v0.0.1 to v0.0.5 | no: sign-in only, a pasted key cannot be used | - | - | Update Oddboro first |
| v0.0.6 to v0.0.7 | yes: + Add service, Takes a key | each Odd's runner (Claude, Codex, Grok, Gemini) calls the door with its own client, so that runner's tool-name and timeout limits apply | remove and re-add the Read grant (the key may need pasting again) | Check each runner's limits |
| v0.0.8 to v0.0.10 | yes | through Oddboro's office gateway | remove and re-add the Read grant (the key may need pasting again) |  |
| v0.0.11 and later | yes | through Oddboro's office gateway | a refresh button | GET /api/health reports the version |
<!-- oddboro:end -->

Fork builds with the Pi runner fail the whole run on any granted tool whose full name is over 64 characters.

## Address rules

- `https://` only, with a publicly trusted certificate. A tailnet route such as `tailscale serve` gives one; never use a public route such as `funnel`.
- The exact path, with no redirect, no query and no fragment.
- A short host: keep the host plus the path slug near 25 characters or less, so `mcp__<service id>__<tool>` stays under 64.
- Header: `Authorization`. Paste the bare key; Oddboro adds `Bearer `.

## Read only grants

A Read only grant reaches a tool only when it has `readOnlyHint: true`, no `destructiveHint`, and no change word in its name. Oddboro reads only the first page of tools. Removing an Odd's grant can delete the stored key.

## Smoke test

Manual part (any version), done by the person with the agent guiding:

1. "+ Add service", choose "Takes a key", header `Authorization`, paste the key, save, press Connect.
2. Check the read-only marks on the door's tools.
3. Grant Read to one Odd.
4. Run a chat in which that Odd calls one tool. Confirm it answers, and that the Ledger shows no "could not start during a run".

Automated part: `python tools/smoke_harness.py --harness oddboro --url <https address> --key-env <variable> --server-name <service id> --oddboro-version <version>`. If your door edition has its own Oddboro smoke command, run that too.
