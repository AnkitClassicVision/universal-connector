# Microsoft 365

Outlook mail, calendar and OneDrive or SharePoint files. The door reaches them through Microsoft Graph.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You read as yourself with delegated permissions. This is the usual path. | The person registers an app in Microsoft Entra ID (or uses one their admin gives them), then signs in once through the door's login flow. The agent never handles codes or tokens. |
| Service account | A tenant admin wants app-only access. Avoid it for personal use: it reaches every mailbox. | The admin registers the app. The person stores the client secret with the vault's own command, or places a certificate file with mode 0600 for the door to read by path. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: exist for Microsoft Graph.
- Direct API adapter: a reasonable choice. The door calls Graph with one sign-in per account.

## Tiers

| Tool type | Tier |
|---|---|
| Read or search mail, events, files | green |
| Create a mail draft | yellow, with a warning below |
| Send mail, reply, forward | red |
| Create or change events, share files | red |
| Delete mail, events or files | red |

## Scope hints

- Delegated read permissions: `User.Read`, `Mail.Read`, `Calendars.Read`, `Files.Read`, plus `offline_access`.
- Drafts need `Mail.ReadWrite`, which also allows changing and deleting mail. Sending is a separate permission, `Mail.Send`; leave it out.
- Keep work and personal accounts as separate connections.

## Smoke test

Read the signed-in user's profile, then list one calendar event.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection m365-work --tool <list events tool> --args '{}' --auth-kind oauth --whoami-tool <current user tool>
```

## Gotchas

- Graph pages results with a next link that carries a token. The door must drop it from results.
- Some permissions need a tenant admin to consent first.
- Personal Microsoft accounts and work accounts sign in differently. Pick the right account type when you register the app.
