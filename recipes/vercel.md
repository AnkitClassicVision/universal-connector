# Vercel

Hosting and deployments for web apps. Agents usually read projects, deployments and logs.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use Vercel's own MCP server. This is the usual path. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |
| API key | You use an access token with a direct adapter. | The person creates the token in Vercel's account settings, limits it to one team, and stores it with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: yes, from Vercel, remote, signs in with OAuth. Find the server address in the vendor's MCP docs.
- Community MCP servers: exist.
- Direct API adapter: only when you need a token instead of a sign-in.

## Tiers

| Tool type | Tier |
|---|---|
| Read projects, deployments, build logs, domains | green |
| Search docs | green |
| Read environment variable values | red |
| Deploy, promote, roll back | red |
| Change environment variables, domains or team members | red |

Reading environment variable values is red, because they often hold keys.

## Scope hints

- Limit a token to one team and set an expiry date.
- Keep personal and team accounts as separate connections.

## Smoke test

Read the current user, then list one project.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection vercel --tool <list projects tool> --args '{}' --auth-kind oauth --whoami-tool <current user tool>
```

## Gotchas

- List results page with a `next` value. The door must drop it from results.
- Build logs can print values from the app's environment. Treat them as sensitive.
