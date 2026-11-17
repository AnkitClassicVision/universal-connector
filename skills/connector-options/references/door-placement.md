# Where the door runs

| Option | Good when | Watch out |
|---|---|---|
| This machine, loopback only (`http://127.0.0.1:<port>/mcp`) | Every harness runs on this machine. The default | Harnesses that need `https://` (Oddboro) or run elsewhere cannot reach it without a route |
| This machine plus a private https route on a tailnet (for example `tailscale serve` on a free port) | A harness needs https, or runs on another of the person's own devices | Tailnet-only. Never a public route such as `tailscale funnel`. The route keeps the tailnet Host header, so the door's host list must name that host exactly. The person runs the route command; check the vendor docs for your version's syntax |
| A server the person controls | Harnesses run in several places; the door must stay up | The server holds the vault access, so it needs its own hardening, updates and backups. Out of scope for a first run |

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
