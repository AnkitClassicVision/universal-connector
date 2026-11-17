# Asana

Work management for tasks and projects. Agents usually read tasks, projects and due dates.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use Asana's own MCP server. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |
| API key | The door uses a direct adapter with a personal access token. | The person creates the token in Asana's developer console and stores it with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: Asana has released a remote MCP server that signs in with OAuth. Its status may change: check the vendor docs. Find the server address in the vendor's MCP docs.
- Community MCP servers: exist.
- Direct API adapter: when you need a token instead of a sign-in.

## Tiers

| Tool type | Tier |
|---|---|
| Read tasks, projects, sections, workspaces | green |
| Search tasks | green |
| Create or update a task | red |
| Comment, assign, complete | red |
| Delete, change members or permissions | red |

## Scope hints

- A personal access token acts as the full user. Rely on the door's tiers.
- OAuth scopes: ask for read only if offered (check the vendor docs).
- Use separate connections for separate workspaces.

## Smoke test

Read the current user, then one task.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection asana --tool <read task tool> --args '{}' --auth-kind oauth --whoami-tool <current user tool>
```

## Gotchas

- List results page with offset tokens. The door must drop them from results.
- Personal access tokens do not expire on their own. Revoke old ones.
