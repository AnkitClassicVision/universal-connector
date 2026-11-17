# ClickUp

Work management for tasks, lists and docs. Agents usually read tasks and lists.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | You use a personal API token. This is the usual path. | The person creates the token in ClickUp's settings and stores it with the vault's own command. The value never passes through the agent. |
| OAuth | You build or use an app that signs in (check the vendor docs). | The person signs in once through the door's or the vendor's login flow. The agent never handles codes or tokens. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: exist. Check who maintains one before you trust it with a token.
- Direct API adapter: a reasonable choice. The door calls the API with the token and exposes a few read tools.

## Tiers

| Tool type | Tier |
|---|---|
| Read tasks, lists, folders, spaces | green |
| Search tasks | green |
| Create or update a task | red |
| Comment, assign, change status | red |
| Delete, change members | red |

## Scope hints

- A personal token acts as the full user in every workspace. Rely on the door's tiers.
- If your plan offers a guest or limited member, consider a separate member for agent reads.

## Smoke test

Read the authorized user, then one task.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection clickup --tool <read task tool> --args '{}' --auth-kind api-key --whoami-tool <current user tool>
```

## Gotchas

- Rate limits depend on the plan. A busy agent can hit them.
- Personal tokens do not expire on their own. Regenerate the token to revoke it.
