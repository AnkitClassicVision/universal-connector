# Google Workspace (Gmail, Calendar, Drive)

Mail, calendar and files in a Google account. Agents usually read mail, events and documents.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You read as yourself. This is the usual path. | The person creates an OAuth client in a Google Cloud project, then signs in once through the door's login flow. The agent never handles codes or tokens. The door keeps the sign-in in the vault. |
| Service account | A Workspace admin grants domain-wide access. Avoid it for personal use: it can reach every user. | The admin creates it and grants delegation. The person places the key file with mode 0600, and the door reads it by path. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: a reasonable choice. The door calls the Gmail, Calendar and Drive APIs with one sign-in per account.

## Tiers

| Tool type | Tier |
|---|---|
| Read or search mail, events, files | green |
| Create a mail draft | yellow, with a warning below |
| Send mail, reply, forward | red |
| Create or change events, share files | red |
| Delete mail, events or files | red |

## Scope hints

- Read scopes: `gmail.readonly`, `calendar.readonly`, `drive.readonly`.
- Drafts need `gmail.compose`, which also allows sending. Google has no scope for drafts alone. The door must block sends itself.
- Keep work and personal accounts as separate connections.

## Smoke test

Read the Gmail profile, which shows the signed-in address, then list one calendar event.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection google-work --tool <list events tool> --args '{}' --auth-kind oauth --whoami-tool <mail profile tool>
```

## Gotchas

- List results carry `nextPageToken` paging cursors that trip key-shaped scans. The door must drop cursors from results.
- An OAuth client left in "testing" mode can issue sign-ins that expire after about a week (check the vendor docs).
- Workspace admins can block unverified apps. Ask the admin first.
