# Slack

Team chat. Agents usually read channels, threads and user profiles.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You install a Slack app or use a hosted server that signs in. | The person installs the app or signs in once through the vendor's flow. The agent never handles codes or tokens. |
| API key | You use the bot token of a Slack app you installed. | The person creates the app, installs it, and stores the bot token with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: Slack has announced its own MCP server. Its status and who may use it can change: check the vendor docs.
- Community MCP servers: exist. An older reference server was archived; check who maintains any you choose.
- Direct API adapter: a reasonable choice for a few read tools with a bot token.

## Tiers

| Tool type | Tier |
|---|---|
| Read channel history, threads, user profiles | green |
| Search messages | green |
| Post a message or reply | red |
| Add a reaction, pin, upload a file | red |
| Delete, invite, change channel settings | red |

Slack has no private draft that only the owner sees, so nothing here is yellow.

## Scope hints

- Bot read scopes: `channels:history`, `channels:read`, `users:read`. Add `groups:history` only for private channels you need.
- A bot sees only the channels it is invited to. Invite it to the smallest set.
- A user token acts as the person. Prefer a bot token.
- A workspace admin may need to approve the app.

## Smoke test

Run the token's auth test read, then read one channel.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection slack --tool <read channel tool> --args '{}' --auth-kind api-key --whoami-tool <auth test tool>
```

## Gotchas

- History results page with cursors. The door must drop cursors from results.
- Rate limits vary by method. History reads are among the strictest.
- Messages can hold sensitive text. Keep the channel list small.
