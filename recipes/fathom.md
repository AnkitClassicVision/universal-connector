# Fathom

A meeting recorder and note taker. Agents usually read meeting lists, summaries and transcripts.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | Fathom offers API keys for its public API (check the vendor docs). | The person creates the key in Fathom's settings and stores it with the vault's own command. The value never passes through the agent. |
| OAuth | An app signs in on the person's behalf, if Fathom offers it (check the vendor docs). | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: check the vendor docs.
- Direct API adapter: a reasonable choice for a few read tools.

## Tiers

| Tool type | Tier |
|---|---|
| List meetings, read summaries and transcripts | green |
| Search meetings | green |
| Create or change webhooks | red |
| Share or delete recordings | red |

## Scope hints

- A key may reach every meeting the account can see, including shared team meetings. Check what the key covers (check the vendor docs).
- Keep work and personal accounts as separate connections.

## Smoke test

List one meeting.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection fathom --tool <list meetings tool> --args '{}' --auth-kind api-key
```

## Gotchas

- Transcripts hold everything people said. Treat them as sensitive and keep reads narrow.
- List results may page with cursors. The door must drop cursors from results.
