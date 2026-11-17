# Intercom

Customer messaging and support. Agents usually read conversations, contacts and articles.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use Intercom's own MCP server or a public app. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |
| API key | You use the access token of a private app in your workspace. | The person creates the app in Intercom's developer area and stores its token with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: Intercom has released a remote MCP server. Which regions and plans it covers: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: a reasonable choice for read tools.

## Tiers

| Tool type | Tier |
|---|---|
| Read or search conversations, contacts, articles | green |
| Add an internal note | red |
| Reply, close, assign, tag | red |
| Delete contacts, change workspace settings | red |

## Scope hints

- Give the private app read permissions only (check the vendor docs for the permission names).
- Conversations hold customer personal data. Keep reads narrow.

## Smoke test

Read the admin who owns the token, then one conversation.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection intercom --tool <read conversation tool> --args '{}' --auth-kind api-key --whoami-tool <current admin tool>
```

## Gotchas

- Workspaces in different regions use different API addresses. Use the one for your region.
- List results page with cursors. The door must drop cursors from results.
