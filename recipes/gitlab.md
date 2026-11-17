# GitLab

Code hosting, issues, merge requests and pipelines, on GitLab.com or a self-managed instance.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | You use a personal, project or group access token. This is the usual path. | The person creates the token in GitLab's settings and stores it with the vault's own command. The value never passes through the agent. |
| OAuth | Your server or instance supports a sign-in flow (check the vendor docs). | The person signs in once through the door's or the vendor's login flow. The agent never handles codes or tokens. |

## Connect it

- Official MCP server: GitLab has published an MCP server in recent versions. Its status and setup may change: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: for older self-managed instances with no MCP support.

## Tiers

| Tool type | Tier |
|---|---|
| Read projects, files, issues, merge requests, pipelines | green |
| Search | green |
| Create an issue, comment, open a merge request | red |
| Merge, push, run or cancel a pipeline | red |
| Delete, change settings or members | red |

## Scope hints

- Use the `read_api` scope for a read-only token.
- Prefer a project or group access token over a personal one, so it reaches only what it needs.
- Set an expiry date.

## Smoke test

Read the current user, then one project.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection gitlab --tool <read project tool> --args '{}' --auth-kind api-key --whoami-tool <current user tool>
```

## Gotchas

- A self-managed instance has its own address. Use the one your instance gives you.
- The `api` scope allows writes. Avoid it for read connections.
- Group and project tokens act as a bot user, which helps other people tell agent actions apart.
