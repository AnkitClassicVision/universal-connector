# 04-door

## Purpose

Run the door: a tagged release on this machine, listening on loopback, reading its secrets from the vault, with an https route only if a chosen harness needs one, and a green doctor.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/` | The manifest draft, harnesses and door placement |
| Vault receipt | `<run folder>/03-vault/output/vault-receipt.md` | Which entries exist and which connections still need a sign-in |
| Door placement | `skills/connector-options/references/door-placement.md` | What the door must do, and route rules |
| The door's own release notes | The release you install | Install, service, login, doctor and key commands |

Read only what is listed here. This stage is a human yes point: installing a user service needs the person's yes.

## Process

1. **The release.** The door ships in this repository, in `door/`, released with the tag `v0.1.0`. Install that tag, not a working copy: `uv tool install git+https://github.com/AnkitClassicVision/universal-connector@v0.1.0#subdirectory=door` (the person runs it; it fetches from the network). Check the installed door against the "What the door must do" list in `door-placement.md`. If it lacks an item, tell the person and stop for their decision. Another door works too if it meets that list; record which.
2. Put the live manifest and the door's state in their own folder, never inside a code checkout. Verify the release the way its notes say (tag signature or checksum).
3. Turn `manifest-draft.yaml` into the door's manifest with the door's own command or format. Keep names and pointers only. For each harness, issue its entry in the harness's own format; for Oddboro use the door's `--format oddboro`, which sets `pinned_tools: false` so Oddboro sees only the door's short fixed tools and every full name stays under 64 characters.
4. With the person's yes, install the door as a user service that listens on loopback only (a systemd user unit, a launchd agent or a scheduled task, as the door's notes say).
5. For each OAuth connection, the person runs the door's login command and signs in, fresh, in their browser. You never see the code or the token.
6. If a chosen harness needs https (for example Oddboro), the person adds a private route to the door's loopback port, never a public one: a tailnet route, or a local https proxy on a `<label>.localhost` name (both in `door-placement.md`, Private https routes). Add the route's exact host to the door's host list (`door_hosts`). Check it: `python tools/gotchas.py host --route-host <host> --door-hosts <list>`.
7. Run the door's doctor. Every connection must show its secret present (without showing it) and its upstream reachable. Fix or mark each red row with the person.
8. Record the door's slowest expected call, for the read timeouts in `05x`.
9. Write `door.md` with the fields in `deliverable.md`.

## Output

Write to `<run folder>/04-door/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connector-options`, `skills/handle-secrets`
- `tools/gotchas.py`
