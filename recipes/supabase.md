# Supabase

A hosted Postgres database platform with auth, storage and functions. Agents usually read tables and run read-only queries.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use Supabase's own MCP server with a sign-in. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |
| API key | You use a personal access token with the MCP server. | The person creates the token in the Supabase dashboard and stores it with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: yes, from Supabase. It can run in a read-only mode and can be limited to one project. Find the server address and options in the vendor's MCP docs.
- Community MCP servers: exist. Prefer the official one.
- Direct API adapter: not usually needed. For plain database reads, see `postgres.md`.

## Tiers

| Tool type | Tier |
|---|---|
| List tables, read schema, read-only SQL | green |
| Read logs and advisors | green |
| Apply a migration, run write SQL | red |
| Deploy a function, create or merge a branch | red |
| Read or change project keys and secrets | red |

## Scope hints

- Turn on the server's read-only mode.
- Limit the server to one project. Never point it at production with writes on.
- A personal access token reaches every project in the account. Prefer the sign-in or a scoped option (check the vendor docs).

## Smoke test

List the tables of the project.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection supabase --tool <list tables tool> --args '{}' --auth-kind oauth
```

## Gotchas

- Query results can hold user data. Keep queries narrow.
- Tools that show project keys are red, even though they only read.
