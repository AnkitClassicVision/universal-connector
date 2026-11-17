# 05k-connect-oddboro

## Purpose

Connect the person's own Oddboro office to the door as one hosted MCP service, granted Read only to one Odd. Their Oddboro may differ from any example: work from their address and kind.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; their Oddboro address and kind; the https route |
| Door | `<run folder>/04-door/output/door.md` | The https route URL and the door's host list |
| Common steps | `skills/connect-harness/SKILL.md` | Ask, key, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | Oddboro's limits |
| Oddboro versions | `skills/connector-options/references/oddboro.md` | What their version supports, the address rules, the smoke test |

Read only what is listed here. This stage is a human yes point.

## What Oddboro needs

- **v0.0.6 or later.** Earlier versions are sign-in only and cannot use a pasted key: the person updates Oddboro first. In v0.0.6 and v0.0.7 each Odd's runner (Claude, Codex, Grok, Gemini) calls the door with its own client, so each runner's own tool-name and timeout limits apply; from v0.0.8 calls go through Oddboro's office gateway. See the table in `oddboro.md`.
- **https only.** Oddboro accepts only `https://` service addresses with a publicly trusted certificate, the exact path, and no redirect. A door on loopback needs an https route, for example a tailnet-only `tailscale serve` on a free port (never `funnel`), and the route's exact Host in the door's host list. `04-door` set this up. Keep the host plus path slug near 25 characters or less.
- **Read only reaches few tools.** A Read only grant reaches a tool only when it has `readOnlyHint: true`, no `destructiveHint`, and no change word (create, update, delete, send and so on) in its name.
- **64 characters.** Oddboro's Pi worker refuses any granted tool whose full name `mcp__<service id>__<tool>` is over 64 characters, and fork builds with the Pi runner fail the whole run on one such tool. The service id comes from the address, so a long host name makes long ids. Expose only the door's short fixed tools to Oddboro.
- **First page only.** Oddboro reads only the first page of `tools/list`.
- **New door tools.** From v0.0.6 to v0.0.10, tools the door adds later do not reach an existing Read grant: the person removes and re-adds the grant. v0.0.11 and later have a refresh button.
- **Grants hold the key.** Removing an Odd's grant can delete the stored key, so the person may need to paste it again.

## Process

1. **Confirm their Oddboro.** From the plan: its address and kind (desktop app, browser-source office, or remote over a tailnet). If the plan lacks them, ask now.
2. **Find the version** as `oddboro.md` says: the Setup window first, then `python tools/oddboro_version.py` (add `--checkout <folder>` for a source run). Below v0.0.6, stop: the person updates Oddboro first. For v0.0.6 or v0.0.7, note each runner's own limits.
3. **Ask for the yes**: one new service in their Services tab, granted Read only to one Odd they name.
4. **Key**: the person issues one door key for Oddboro with the door's own command.
5. **Add the service** (the person clicks, you guide): Services tab, "+ Add service", a hosted MCP service. Address: the https route to the door, exact path. Choose "Takes a key". Header name: `Authorization`. Paste the bare key; Oddboro adds `Bearer `.
6. **Save the key** on the Oddboro desk task, pasted by the person, then press **Connect**.
7. **Check the read-only marks** on the door's tools, then **grant** the service to one Odd, Read only.
8. **Back up** is not a file here: record the service id, the grant, and how to remove both (the rollback).
9. **Check in Oddboro**: the service shows Connected with a tool count. Run a chat in which that Odd calls one tool; confirm it answers and that the Ledger shows no "could not start during a run". Then look at the door's audit log for those calls (names only).
10. **Smoke**: `python tools/smoke_harness.py --harness oddboro --url <https route> --key-env <variable or --key-file> --server-name <service id as Oddboro shows it> --oddboro-version <version>`. It checks the version, https, the exact address and redirects, the address length, the 64-character names, the first page, Read only reachability, refusals and the route Host. If the door edition has its own Oddboro smoke command, run it too.

## Output

Write to `<run folder>/05k-connect-oddboro/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/smoke_harness.py`, `tools/gotchas.py`
