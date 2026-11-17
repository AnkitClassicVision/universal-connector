# Notion

Docs, wikis and databases. Agents usually search and read pages and database rows.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use Notion's hosted MCP server. | The person signs in once through the vendor's login flow and picks the pages to share. The agent never handles codes or tokens. |
| API key | You use an internal integration with a local server or direct adapter. | The person creates the integration in Notion's settings, shares pages with it, and stores its token with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: yes. Notion offers a hosted remote server with OAuth, and a local open-source server that uses an integration token. Find the server address in the vendor's MCP docs.
- Community MCP servers: exist.
- Direct API adapter: not usually needed.

## Tiers

| Tool type | Tier |
|---|---|
| Search, read a page, query a database | green |
| Create a private draft page only the owner sees | yellow, if the owner agrees; else red |
| Edit shared pages or database rows | red |
| Comment | red |
| Delete, move, change sharing | red |

## Scope hints

- For an internal integration, turn on "read content" only and leave insert and update off.
- An integration sees only the pages shared with it. Share the smallest set.
- Keep work and personal workspaces as separate connections.

## Smoke test

Read the integration's own bot user, then search for one page.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection notion --tool <search tool> --args '{}' --auth-kind api-key --whoami-tool <bot user tool>
```

## Gotchas

- List and query results carry a `next_cursor`. The door must drop cursors from results.
- Search returns nothing until pages are shared with the integration.
- Rate limits are low. Keep agent queries small.
