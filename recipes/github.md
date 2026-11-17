# GitHub

Code hosting, issues and pull requests. Agents usually read code, issues, pull requests and checks.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use GitHub's hosted MCP server with a sign-in. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |
| API key | You use a fine-grained personal access token. | The person creates the token in GitHub's developer settings and stores it with the vault's own command. The value never passes through the agent. |
| Service account | An organisation wants a GitHub App instead of a person's token. | An org owner creates the app. The person places its private key file with mode 0600, and the door reads it by path. |

## Connect it

- Official MCP server: yes. GitHub offers a hosted remote server (OAuth or token) and a local server you run yourself. Find the server address in the vendor's MCP docs.
- Community MCP servers: exist. Prefer the official one.
- Direct API adapter: not usually needed.

## Tiers

| Tool type | Tier |
|---|---|
| Read code, files, issues, pull requests, checks | green |
| Search code and issues | green |
| Create an issue, comment, open a pull request | red |
| Push, merge, create a release, run a workflow | red |
| Delete, change settings or permissions | red |

Draft pull requests are still visible to other people, so they are red, not yellow.

## Scope hints

- Use a fine-grained token limited to the repositories it needs.
- Repository permissions: read-only for contents, issues, pull requests and metadata.
- Set an expiry date. Organisations may require approval for fine-grained tokens.
- Keep work and personal accounts as separate connections.

## Smoke test

Read the authenticated user, then one repository.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection github --tool <read repository tool> --args '{}' --auth-kind api-key --whoami-tool <current user tool>
```

## Gotchas

- Classic tokens with broad scopes reach every repository. Replace them with fine-grained tokens.
- Rate limits are per token. A busy agent can hit them.
- The hosted server exposes many tools. Keep only the read tools the door needs, so tool names stay short.
