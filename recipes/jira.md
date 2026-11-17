# Jira

Atlassian's issue tracker. Agents usually search and read issues, sprints and boards.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use Atlassian's own MCP server. This is the usual path for Jira Cloud. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |
| API key | A community server or direct adapter needs an API token. | The person creates an API token in their Atlassian account settings and stores it with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: yes, Atlassian runs a remote MCP server that signs in with OAuth. Its scope and status may change: check the vendor docs. Find the server address in the vendor's MCP docs.
- Community MCP servers: exist, and some support Jira Server or Data Center with a token.
- Direct API adapter: for self-managed Jira, if no server fits.

## Tiers

| Tool type | Tier |
|---|---|
| Search issues, read an issue, read boards and sprints | green |
| Create an issue | red |
| Comment, transition, assign, log work | red |
| Delete, change permissions or workflows | red |

## Scope hints

- Ask for read scopes only. Scope names: check the vendor docs.
- Atlassian also offers API tokens with scopes. Prefer a scoped token with an expiry date (check the vendor docs).
- Keep separate sites as separate connections.

## Smoke test

Read the current user, then search for one issue.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection jira --tool <search issues tool> --args '{}' --auth-kind oauth --whoami-tool <current user tool>
```

## Gotchas

- An unscoped API token acts as the full user on every site the account can reach.
- Search results page with offsets or tokens. The door must drop paging tokens from results.
- Some sites need an admin to allow the app before anyone can sign in.
