# Salesforce

A CRM for accounts, contacts, opportunities and cases. Agents usually read and query records.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You read as yourself or as an integration user. This is the usual path. | An admin sets up a connected app (or its newer equivalent). The person signs in once through the door's login flow or Salesforce's. The agent never handles codes or tokens. |
| Service account | Server-to-server access with a signed certificate. | An admin sets up the app and an integration user. The person places the private key file with mode 0600, and the door reads it by path. |

## Connect it

- Official MCP server: Salesforce has announced MCP support in its products and a developer server. Which fits a door: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: a reasonable choice for read queries.

## Tiers

| Tool type | Tier |
|---|---|
| Query and read records | green |
| Read reports and dashboards | green |
| Create or update a record, log an activity | red |
| Send email, change ownership | red |
| Delete, change sharing, profiles or permission sets | red |

## Scope hints

- Use an integration user with a read-only permission set.
- OAuth scopes: ask for API access and refresh only (check the vendor docs for current scope names).
- Keep a sandbox connection separate from production.

## Smoke test

Read the signed-in user's identity, then query one record.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection salesforce --tool <query tool> --args '{}' --auth-kind oauth --whoami-tool <identity tool>
```

## Gotchas

- Query results page with a next-records locator. The door must drop it from results.
- Admins may restrict which apps users can sign in to.
- API calls count against a daily org limit.
