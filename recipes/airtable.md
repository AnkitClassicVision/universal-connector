# Airtable

Bases, tables and records. Agents usually read records and base schemas.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | You use a personal access token. This is the usual path. | The person creates the token in Airtable's developer hub, picks its scopes and bases, and stores it with the vault's own command. The value never passes through the agent. |
| OAuth | An integration signs in on the person's behalf. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: a reasonable choice for record reads.

## Tiers

| Tool type | Tier |
|---|---|
| List and read records, read base schema | green |
| Search records | green |
| Create or update records | red |
| Delete records, change fields or sharing | red |

## Scope hints

- Token scopes: `data.records:read` and `schema.bases:read`.
- Give the token access to only the bases it needs.

## Smoke test

Run the who-am-I read, then list one record.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection airtable --tool <list records tool> --args '{}' --auth-kind api-key --whoami-tool <who am I tool>
```

## Gotchas

- List results page with an `offset` value. The door must drop it from results.
- Rate limits are per base and low. Keep agent queries small.
