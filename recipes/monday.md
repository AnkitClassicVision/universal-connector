# Monday.com

A work board for items, boards and updates. Agents usually read boards and items.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | You use a personal API token with a local server or direct adapter. | The person copies the token from monday.com's developer area and stores it with the vault's own command. The value never passes through the agent. |
| OAuth | You use a hosted server or an app that signs in (check the vendor docs). | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |

## Connect it

- Official MCP server: yes, monday.com publishes one. It comes as a local server that uses an API token and as a hosted version. Which fits you: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: not usually needed.

## Tiers

| Tool type | Tier |
|---|---|
| Read boards, items, columns, users | green |
| Search items | green |
| Create or update an item | red |
| Post an update, assign, change status | red |
| Delete, change board permissions | red |

## Scope hints

- A personal token acts as the full user. Rely on the door's tiers.
- Some servers offer a read-only mode. Turn it on if offered (check the vendor docs).
- Use separate connections for separate accounts.

## Smoke test

Read the current user, then one board.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection monday --tool <read board tool> --args '{}' --auth-kind api-key --whoami-tool <current user tool>
```

## Gotchas

- The API uses a query budget. Large board reads can use it up.
- Item pages use cursors. The door must drop cursors from results.
