# Connection recipes

One short file per common service. Each says how to authenticate, how to connect it to the door, which tools are green, yellow or red, which scopes to ask for, and one read call that proves it works.

| Service | File | Auth kinds | MCP server |
|---|---|---|---|
| Multica | `multica.md` | API key, website login | check the vendor docs |
| Linear | `linear.md` | OAuth, API key | official, remote, OAuth |
| Jira | `jira.md` | OAuth, API key | official, remote, OAuth |
| GitHub | `github.md` | OAuth, API key, service account | official, remote and local |
| GitLab | `gitlab.md` | API key, OAuth | check the vendor docs |
| Notion | `notion.md` | OAuth, API key | official, remote OAuth and local token |
| Asana | `asana.md` | OAuth, API key | official, remote, OAuth (check the vendor docs) |
| ClickUp | `clickup.md` | API key, OAuth | check the vendor docs |
| Monday.com | `monday.md` | API key, OAuth | official, local and hosted |
| Trello | `trello.md` | API key, OAuth | check the vendor docs |
| Slack | `slack.md` | OAuth, API key | check the vendor docs |
| Microsoft Teams | `microsoft-teams.md` | OAuth, service account | check the vendor docs |
| Google Workspace (Gmail, Calendar, Drive) | `google-workspace.md` | OAuth, service account | check the vendor docs |
| Microsoft 365 | `microsoft-365.md` | OAuth, service account | check the vendor docs |
| HubSpot | `hubspot.md` | OAuth, API key | official, remote OAuth (check the vendor docs) |
| Salesforce | `salesforce.md` | OAuth, service account | check the vendor docs |
| Twenty CRM | `twenty.md` | API key | check the vendor docs |
| Zendesk | `zendesk.md` | OAuth, API key | check the vendor docs |
| Intercom | `intercom.md` | OAuth, API key | official, remote (check the vendor docs) |
| Stripe | `stripe.md` | API key, OAuth | official, remote and local |
| QuickBooks | `quickbooks.md` | OAuth | published by the vendor (check the vendor docs) |
| Fathom | `fathom.md` | API key, OAuth | check the vendor docs |
| Zoom | `zoom.md` | OAuth, service account | check the vendor docs |
| Airtable | `airtable.md` | API key, OAuth | check the vendor docs |
| Supabase | `supabase.md` | OAuth, API key | official, read-only mode |
| Postgres | `postgres.md` | API key (connection string), service account | community servers |
| AWS | `aws.md` | OAuth (single sign-on), service account, API key | official, local |
| Cloudflare | `cloudflare.md` | OAuth, API key | official, remote, OAuth |
| Vercel | `vercel.md` | OAuth, API key | official, remote, OAuth |

## How to use a recipe

1. In stage `02-plan`, open the recipe for each service the scan or the interview found.
2. Copy its auth kind, tiers and scope hints into that connection's row of the plan. The owner still confirms every tier and scope.
3. If a recipe says "check the vendor docs", check them before you plan that connection. Do not guess.
4. Use its smoke test line in stage `06a-smoke-connections`. Fill in the door address and the read tool the door exposes.
5. To add a service, copy `_template.md` to `<service>.md`, keep every heading, add a row to this table, and run the tests.

The kit never asks for, collects, stores, prints or moves a password, one-time code or recovery code. Every recipe follows that rule.
