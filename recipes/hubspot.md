# HubSpot

A CRM for contacts, companies, deals and marketing. Agents usually read CRM records.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use HubSpot's hosted MCP server. | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |
| API key | You use a private app access token with a local server or direct adapter. | The person creates the private app in HubSpot's settings, picks its scopes, and stores the token with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: yes. HubSpot offers a hosted remote server that signs in with OAuth, and has offered a local server that uses a private app token. Which one is current: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: not usually needed.

## Tiers

| Tool type | Tier |
|---|---|
| Read or search contacts, companies, deals, tickets | green |
| Read reports and properties | green |
| Create or update a record, add a note | red |
| Send email, enroll in a sequence | red |
| Delete, merge, change owners or permissions | red |

CRM writes are red because other people act on these records.

## Scope hints

- Private app read scopes, for example `crm.objects.contacts.read` and `crm.objects.companies.read`. Add only what you need.
- A separate user for agent reads makes audit trails clearer.

## Smoke test

Read the account details, then one contact.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection hubspot --tool <read contact tool> --args '{}' --auth-kind api-key --whoami-tool <account details tool>
```

## Gotchas

- Search and list results page with an `after` cursor. The door must drop cursors from results.
- Daily and burst rate limits depend on the plan.
- Records can hold personal data about customers. Keep reads narrow.
