# Cloudflare

DNS, CDN, Workers and security settings. Agents usually read zones, DNS records, analytics and logs.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use Cloudflare's own remote MCP servers. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |
| API key | You use a scoped API token with a direct adapter. | The person creates a custom token with read permissions in the Cloudflare dashboard and stores it with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: yes. Cloudflare runs several remote MCP servers, each for one product area, that sign in with OAuth. Find the server addresses in the vendor's MCP docs.
- Community MCP servers: exist.
- Direct API adapter: for a few fixed reads with a scoped token.

## Tiers

| Tool type | Tier |
|---|---|
| Read zones, DNS records, analytics, logs | green |
| Read Worker code and settings | green |
| Change DNS, purge the cache | red |
| Deploy a Worker, change firewall or access rules | red |
| Delete anything, change account members or tokens | red |

## Scope hints

- Use a custom token with read permissions only, for example zone read and DNS read.
- Limit the token to the zones it needs, and add an expiry date.
- Never use the global API key.

## Smoke test

Run the token verify read, then list one zone.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection cloudflare --tool <list zones tool> --args '{}' --auth-kind api-key --whoami-tool <token verify tool>
```

## Gotchas

- Each remote server covers one area. Connect only the ones you need, so the tool list stays short.
- List results page with cursors or page numbers. The door must drop cursors from results.
