# Zendesk

Customer support tickets, users and help center articles. Agents usually read tickets and articles.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use an OAuth client for one agent user. This is the safer path. | An admin creates the client. The person signs in once through the door's login flow or Zendesk's. The agent never handles codes or tokens. |
| API key | You use an API token with an agent's email address. | An admin turns on token access and creates the token. The person stores it with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: a reasonable choice for ticket and article reads.

## Tiers

| Tool type | Tier |
|---|---|
| Read or search tickets, users, articles | green |
| Add an internal note | red |
| Reply to a customer, change status, assign | red |
| Delete, merge, change triggers or macros | red |

## Scope hints

- With OAuth, ask for the `read` scope only.
- API tokens are account-wide and act as the user named with them. Prefer OAuth.

## Smoke test

Read the current user, then one ticket.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection zendesk --tool <read ticket tool> --args '{}' --auth-kind oauth --whoami-tool <current user tool>
```

## Gotchas

- Tickets hold customer personal data. Keep reads narrow.
- List results page with cursors or next links. The door must drop them from results.
- Rate limits depend on the plan.
