# QuickBooks

QuickBooks Online accounting: company info, invoices, bills and reports. Agents usually read reports and records.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | Always. QuickBooks Online uses OAuth 2.0 through an Intuit developer app. | The person creates the app in Intuit's developer portal, then signs in once through the door's login flow and picks the company. The agent never handles codes or tokens. The door keeps the sign-in in the vault. |

## Connect it

- Official MCP server: Intuit has published an MCP server for QuickBooks. Its status and setup may change: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: a reasonable choice for report and record reads.

## Tiers

| Tool type | Tier |
|---|---|
| Read company info, reports, invoices, bills, customers | green |
| Create a draft invoice or estimate | red, unless the owner decides yellow |
| Create, send or void an invoice, record a payment | red |
| Change accounts, delete records | red |

Finance writes are red. Other people act on these records.

## Scope hints

- The accounting scope is `com.intuit.quickbooks.accounting`. It allows writes, so the door's tiers are the real limit.
- Start with a sandbox company. Make a separate connection for the real company.

## Smoke test

Read the company info, which shows the company name.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection quickbooks --tool <read company info tool> --args '{}' --auth-kind oauth --whoami-tool <company info tool>
```

## Gotchas

- Access lasts about an hour. The refresh value changes each time it is used, so the door must save the new one in the vault every time.
- If the refresh fails, the person signs in again. The agent never repairs it.
- Report reads can be slow. Set the client read timeout above the door's worst case.
