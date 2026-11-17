# Multica

A work board for issues and agent runs. It can be self-hosted or used as a cloud service. Agents usually read issues, comments and run status.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | The board offers personal access tokens (check the vendor docs). | The person creates a token in the board's settings and stores it with the vault's own command. The value never passes through the agent. |
| Website login (browser lane) | Only if your deployment has no token option. | The person signs in themselves in the browser lane. Passwords stay in their password manager. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: check the vendor docs.
- Direct API adapter: likely needed. The door calls the board's API with the token and exposes a few read tools.
- A self-hosted board has its own address. Use the address your deployment gives you; never copy one from an example.

## Tiers

| Tool type | Tier |
|---|---|
| List or read issues, comments, run status | green |
| Create an issue or card | red |
| Comment, change status, assign | red |
| Delete or archive | red |

Comments and cards are red because other people and agents act on them and would read an agent's text as the owner's.

## Scope hints

- Use a token for one workspace only, if the board allows it.
- Prefer a token with an expiry date.
- If the board supports a separate bot identity, use it so other lanes can tell agent text apart.

## Smoke test

Read the current user or one issue.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection multica --tool <read issue tool> --args '{}' --auth-kind api-key
```

Add `--whoami-tool <tool>` if the door exposes a current-user read.

## Gotchas

- A token may act as the full user. The door's tiers are the real limit.
- Self-hosted deployments may differ in API version. Check the version your board runs.
