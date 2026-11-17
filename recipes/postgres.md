# Postgres

Any PostgreSQL database. Agents usually read schemas and run read-only queries.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | The door connects with a connection string for a read-only role. | A database admin creates the role. The person stores the connection string with the vault's own command. The value never passes through the agent and is never shown. |
| Service account | The database uses client certificates. | The person places the certificate and key files with mode 0600, and the door reads them by path. |

The connection string holds a password, so the whole string is **one secret value** under the vault rule: store it as a single entry, never split into parts and never as part of a larger file. If it sits inside a config today, prefer a fresh read-only role; otherwise move just that one field with `tools/move_field.py`. Never paste it, print it, or put it on a command line.

## Connect it

- Official MCP server: no single official server. An early reference server was archived: check the vendor docs for current options.
- Community MCP servers: exist.
- Direct API adapter: a reasonable choice. The door runs each query in a read-only transaction with a time limit.

## Tiers

| Tool type | Tier |
|---|---|
| List schemas and tables, describe a table | green |
| Read-only SELECT queries on tables and views | green |
| A SELECT that calls a function with side effects (for example `nextval`, `pg_notify`, `pg_terminate_backend`, `dblink`, or any user function not marked `STABLE` or `IMMUTABLE`) | yellow: a read-only transaction stops most writes, but not every side effect |
| INSERT, UPDATE, DELETE | red |
| CREATE, ALTER, DROP, GRANT | red |

## Scope hints

- Create a role with SELECT on only the schemas the agent needs.
- Set `default_transaction_read_only` on for that role, and set a `statement_timeout`.
- Use a replica if you have one, not the primary.
- Require TLS for any database that is not on this machine.

## Smoke test

Run a query that returns the current role name, which proves the sign-in without showing it.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection postgres --tool <read query tool> --args '{}' --auth-kind api-key --whoami-tool <current role tool>
```

## Gotchas

- Long queries can outlast the client's read timeout. Set the timeout above the door's worst case.
- Rows can hold personal data. Keep queries narrow and add a row limit.
