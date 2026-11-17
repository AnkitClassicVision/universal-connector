# Microsoft Teams

Team chat and channels in Microsoft 365. The door reaches it through Microsoft Graph.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You read as yourself with delegated permissions. This is the usual path. | The person signs in once through the door's login flow or Microsoft's. The agent never handles codes or tokens. |
| Service account | A tenant admin wants app-only access. Avoid it for personal use: it reaches the whole tenant. | The admin registers the app. The person stores the client secret with the vault's own command, or places a certificate file with mode 0600 for the door to read by path. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: exist for Microsoft Graph.
- Direct API adapter: a reasonable choice. Register an app in Microsoft Entra ID and let the door call Graph.

## Tiers

| Tool type | Tier |
|---|---|
| Read chats, channel messages, team lists | green |
| Search messages | green |
| Send a chat or channel message | red |
| Create a meeting, add members | red |
| Delete, change team settings | red |

## Scope hints

- Delegated read permissions: `User.Read`, `Chat.Read`, `ChannelMessage.Read.All`. Some need admin consent.
- Add `offline_access` so the sign-in lasts without asking again.
- Keep work and personal accounts as separate connections.

## Smoke test

Read the signed-in user's profile, then one chat.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection teams --tool <read chat tool> --args '{}' --auth-kind oauth --whoami-tool <current user tool>
```

## Gotchas

- Graph pages results with a next link that carries a token. The door must drop it from results.
- Many read permissions need a tenant admin to consent first.
- App-only access reads every team in the tenant. Only a tenant admin should decide on it.
