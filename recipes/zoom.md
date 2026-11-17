# Zoom

Meetings, recordings and users. Agents usually read meeting lists and recordings.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You read as yourself with a user-level app. This is the safer path. | The person creates the app in Zoom's app marketplace, then signs in once through the door's login flow. The agent never handles codes or tokens. |
| Service account | An account admin wants a server-to-server app. It reaches the whole account. | The admin creates the app. The person stores its client secret with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: a reasonable choice for read tools.

## Tiers

| Tool type | Tier |
|---|---|
| Read the user, list meetings, list recordings | green |
| Read a transcript | green |
| Create or update a meeting | red |
| Invite people, start a meeting | red |
| Delete meetings or recordings, change account settings | red |

Creating a meeting sends invites to other people, so it is red.

## Scope hints

- Ask for read scopes only, for example user and meeting read. Zoom has changed its scope names: check the vendor docs.
- Prefer a user-level app over a server-to-server app.

## Smoke test

Read the current user, then list one meeting.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection zoom --tool <list meetings tool> --args '{}' --auth-kind oauth --whoami-tool <current user tool>
```

## Gotchas

- List results page with a `next_page_token`. The door must drop it from results.
- Recordings and transcripts hold what people said. Keep reads narrow.
