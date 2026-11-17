# Where the door runs

| Option | Good when | Watch out |
|---|---|---|
| This machine, loopback only (`http://127.0.0.1:<port>/mcp`) | Every harness runs on this machine. The default | Harnesses that need `https://` (Oddboro) or run elsewhere cannot reach it without a route |
| This machine plus a private https route on a tailnet (for example `tailscale serve` on a free port) | A harness needs https, or runs on another of the person's own devices | Tailnet-only. Never a public route such as `tailscale funnel`. The route keeps the tailnet Host header, so the door's host list must name that host exactly. The person runs the route command; check the vendor docs for your version's syntax |
| This machine plus a local https proxy on a `<label>.localhost` name | A harness on this machine needs https and there is no tailnet | Only this machine can reach it. The certificate comes from a local authority the system must trust; a harness that wants a publicly trusted certificate (Oddboro does) may refuse it. Check with that harness's smoke test |
| A server the person controls | Harnesses run in several places; the door must stay up | The server holds the vault access, so it needs its own hardening, updates and backups. Out of scope for a first run |

## Private https routes

A harness that accepts only `https://` needs a route in front of the loopback door. Pick one; the person runs every command. Commands marked **unverified** were not run by this kit's authors; check the vendor docs for your version.

1. **Tailscale serve (tailnet only).** Forwards a tailnet https address to the door's loopback port, with a publicly trusted certificate for the tailnet name. Example, unverified for your version: `tailscale serve --bg --https=8443 http://127.0.0.1:8765`. Never use `tailscale funnel`, which publishes it to the internet. Add the exact host the route sends (for example `<machine>.tailnet-name.ts.net:8443`, or without the port when it is 443) to the door's host list.
2. **A local https proxy on a `.localhost` name.** Names under `.localhost` always resolve to this machine. Example with Caddy, unverified: `caddy reverse-proxy --from https://door.localhost:8443 --to 127.0.0.1:8765`, after `caddy trust` installs Caddy's local authority into the system store (it asks for the person's yes). Then add `door.localhost:8443` to the door's `door_hosts`, exactly. Any proxy works the same way (nginx, a mkcert certificate, Windows' IIS): it must terminate https on the `.localhost` name and forward to the loopback port without changing the path. Some clients do not trust a local authority, so run the harness's own smoke test and stop if it fails.
3. **A server** with a real domain and certificate: out of scope for a first run.

Whichever route: keep the host plus path short (Oddboro builds tool names from it), use the exact path with no redirect, and run `python tools/gotchas.py host --route-host <host> --door-hosts <list>`.

Rules for every placement:

- The door listens on loopback. A route forwards to loopback; the door itself never binds to all interfaces.
- The door refuses any request with an `Origin` header, so a web page in a browser cannot call it.
- The door accepts only the Host values in its own list (`door_hosts` or the door's equivalent). Add the route's host exactly; no wildcards.
- The live manifest and the door's state live in their own folder, never in a code checkout.
- Run a tagged release, not a working copy.
- Set each harness's read timeout above the door's slowest call. Many HTTP clients default to a few seconds, which is too short for some upstream calls.
- One key per harness. Revoking one harness never affects another.

What the door must do (check these against the door you install; the smoke tests check most of them):

1. Refuse a request with no key, a wrong key or a revoked key with 401.
2. Refuse an `Origin` header and an unlisted Host.
3. Keep an audit line per call: time, harness, connection, tool, tier, outcome. No arguments and no results.
4. Enforce tiers: green tools run; yellow tools only where the plan allows drafts; red tools are refused.
5. Drop paging cursors from list results, or return them only in a field that the harness passes back unchanged.
6. Return all of its tools in one `tools/list` page, with short fixed names, and mark read tools with `readOnlyHint: true`.
7. Read secrets from the vault in memory only, per call.
