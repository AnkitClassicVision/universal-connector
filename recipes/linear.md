# Linear

An issue tracker for product and engineering teams. Agents usually read issues, projects and cycles.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use Linear's own MCP server. This is the usual path. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |
| API key | The door uses a direct API adapter. | The person creates a personal API key in Linear's settings and stores it with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: yes, remote, signs in with OAuth. Find the server address in the vendor's MCP docs.
- Community MCP servers: exist. Prefer the official one.
- Direct API adapter: only when you need a key instead of a sign-in, for example on a machine with no browser.

## Tiers

| Tool type | Tier |
|---|---|
| List or read issues, projects, cycles, teams | green |
| Search issues | green |
| Create or update an issue | red |
| Comment, assign, change state | red |
| Delete or archive | red |

## Scope hints

- With OAuth, ask for read access only. Scope names: check the vendor docs.
- An API key acts as the full user. Rely on the door's tiers.
- Use separate connections for separate workspaces.

## Smoke test

Read the signed-in user, then one issue.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection linear --tool <read issue tool> --args '{}' --auth-kind oauth --whoami-tool <current user tool>
```

## Gotchas

- Linear's API pages results with cursors. The door must drop cursors from list results.
- Rate limits apply per user. A busy agent can hit them.
- Removing the app from Linear's settings ends the sign-in. Sign in again through the vendor flow.
