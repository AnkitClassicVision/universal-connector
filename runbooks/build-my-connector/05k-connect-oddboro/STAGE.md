# 05k-connect-oddboro

## Purpose

Connect the person's own Oddboro office to the door as one hosted MCP service, granted Read only to one Odd. Their Oddboro may differ from any example: work from their address, kind and version.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Chosen or not; their Oddboro address, kind and version; the https route |
| Door | `<run folder>/04-door/output/door.md` | The https route URL and the door's host list |
| Common steps | `skills/connect-harness/SKILL.md` | Yes, key file, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | Oddboro's limits |
| Oddboro versions | `skills/connector-options/references/oddboro.md` | What their version supports, the address rules, the keyring preflight, the smoke test |

Read only what is listed here. Oddboro has no config file to change: the person adds the service in its Services tab. The person's yes comes in step 4.

## What Oddboro needs

- **v0.0.6 or later.** Earlier versions are sign-in only and cannot use a pasted key: the person updates Oddboro first. In v0.0.6 and v0.0.7 each Odd's runner (Claude, Codex, Grok, Gemini) calls the door with its own client, so each runner's own tool-name and timeout limits apply; from v0.0.8 calls go through Oddboro's office gateway. See the table in `oddboro.md`.
- **A system keyring.** Oddboro keeps a pasted key in the system's secret store. On Linux that is a Secret Service keyring (GNOME Keyring or KWallet) reached through `secret-tool`; a Mac and Windows have one built in.
- **https only.** Oddboro accepts only `https://` service addresses with a publicly trusted certificate, the exact path, and no redirect. A door on loopback needs an https route (`references/door-placement.md` lists the options), with the route's exact Host in the door's host list. `04-door` set this up.
- **A short address.** The service id comes from the address: the lower-case host plus path, with every run of other characters turned into one `-` (port and query dropped). Keep it near 25 characters.
- **64 characters.** Oddboro's Pi worker refuses any granted tool whose full name `mcp__<service id>__<tool>` is over 64 characters, and fork builds with the Pi runner fail the whole run on one such tool. Expose only the door's short fixed tools to Oddboro: the door's `--format oddboro` sets `pinned_tools: false` for this.
- **Read only reaches few tools.** Oddboro's own rule: a Read only grant reaches a tool only when it has `readOnlyHint: true`, its `destructiveHint` is not `true` (false or absent is fine), and none of its name's words is a change word. Names are split on `_`, `-`, `.` and other separators and on camelCase, and the change words are Oddboro's 42 (add, append, approve, archive, assign, cancel, capture, clear, close, comment, create, delete, destroy, drop, edit, exec, execute, forward, insert, invite, merge, modify, move, patch, post, publish, put, remove, rename, reply, reset, run, save, send, set, share, store, submit, update, upload, upsert, write).
- **First page only.** Oddboro reads only the first page of `tools/list`.
- **New door tools.** From v0.0.6 to v0.0.10, tools the door adds later do not reach an existing Read grant: the person removes and re-adds the grant. v0.0.11 and later have a refresh button.
- **Grants hold the key.** Removing an Odd's grant can delete the stored key, so the person may need to paste it again.

## Process

1. **Confirm their Oddboro.** From the plan: its address, kind (desktop app, browser-source office, or remote over a tailnet) and version. If the plan lacks them, ask now.
2. **Find the version** as `oddboro.md` says: the Setup window first, then `python tools/oddboro_version.py` (add `--checkout <folder>` for a source run). Below v0.0.6, stop: the person updates Oddboro first. For v0.0.6 or v0.0.7, note each runner's own limits.
3. **Keyring preflight**: `python tools/oddboro_version.py --version <version> --preflight` on the machine that runs the office. On Linux it checks that `secret-tool` is installed and a Secret Service keyring is running (names only; nothing is read from the store). If not, the person starts and unlocks GNOME Keyring or KWallet first.
4. **Ask for the yes**: one new service in their Services tab, granted Read only to one Odd they name.
5. **Key**: the person issues one door key for Oddboro with the door's own command, into a 0600 file.
6. **Add the service** (the person clicks, you guide): Services tab, "+ Add service", a hosted MCP service. Address: the https route to the door, exact path. Choose "Takes a key". Header name: `Authorization`. The person pastes the bare key; Oddboro adds `Bearer `.
7. **Save the key** on the Oddboro desk task, pasted by the person, then press **Connect**.
8. **Check the read-only marks** on the door's tools, then **grant** the service to one Odd, Read only.
9. **Rollback** is not a file here: record the service id, the grant, and how to remove both.
10. **Check in Oddboro**: the service shows Connected with a tool count. Run a chat in which that Odd calls one tool; confirm it answers and that the Ledger shows no "could not start during a run". Then look at the door's audit log for those calls (names only).
11. **Smoke**: `python tools/smoke_harness.py --harness oddboro --url <https route> --key-file <Oddboro's key file> --oddboro-version <version> --plan <run folder>/02-plan/output/manifest-draft.yaml --json`. It judges tool names by the service id it derives from the address, and checks the version, https, the exact address and redirects, the first page, Oddboro's Read only rule, refusals and the route Host. If the door edition has its own Oddboro smoke command, run it too.

## Output

Write to `<run folder>/05k-connect-oddboro/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/oddboro_version.py`, `tools/smoke_harness.py`, `tools/gotchas.py`
