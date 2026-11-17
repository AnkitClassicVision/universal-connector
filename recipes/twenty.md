# Twenty CRM

An open-source CRM, used in the cloud or self-hosted. Agents usually read people, companies and opportunities.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | You use an API key from the workspace settings. This is the usual path. | The person creates the key in Twenty's settings and stores it with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: exist. Check who maintains one before you trust it with a key.
- Direct API adapter: a reasonable choice. Twenty has REST and GraphQL APIs.
- A self-hosted workspace has its own address. Use the one your deployment gives you.

## Tiers

| Tool type | Tier |
|---|---|
| List or read people, companies, opportunities, notes | green |
| Search records | green |
| Create or update a record, add a note or task | red |
| Delete, merge, change workspace members or settings | red |

CRM writes are red because other people act on these records.

## Scope hints

- An API key may reach the whole workspace. Rely on the door's tiers (check the vendor docs for key roles).
- Set an expiry date on the key when you create it.

## Smoke test

List one person record.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection twenty --tool <list people tool> --args '{}' --auth-kind api-key
```

## Gotchas

- List results page with cursors. The door must drop cursors from results.
- Self-hosted versions differ. Check the API version your workspace runs.
