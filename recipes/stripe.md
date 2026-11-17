# Stripe

Payments, customers, invoices and subscriptions. Agents usually read balances, customers and invoices.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | You use a restricted key. This is the usual path. | The person creates a restricted key in the Stripe dashboard, gives it read permissions only, and stores it with the vault's own command. The value never passes through the agent. |
| OAuth | You use Stripe's hosted MCP server with a sign-in (check the vendor docs). | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |

## Connect it

- Official MCP server: yes. Stripe offers a hosted remote server and a local server that takes a key. Find the server address in the vendor's MCP docs.
- Community MCP servers: exist. Prefer the official one.
- Direct API adapter: not usually needed.

## Tiers

| Tool type | Tier |
|---|---|
| Read balance, customers, invoices, charges, subscriptions | green |
| Search records | green |
| Create a draft invoice | red, unless the owner decides yellow |
| Create a payment link, charge, refund or payout | red |
| Cancel a subscription, delete a customer | red |

Payments are red. A draft invoice is reversible, but billing staff may act on it, so it starts red.

## Scope hints

- Use a restricted key with read access to only the resources the agent needs. Never use the full secret key.
- Start in test mode. Make a separate connection for live mode.

## Smoke test

Read the account balance.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection stripe --tool <read balance tool> --args '{}' --auth-kind api-key
```

## Gotchas

- List results page with a `starting_after` cursor. The door must drop cursors from results.
- Test-mode and live-mode keys are separate. A test key cannot read live data.
- Customer records hold personal and payment data. Keep reads narrow.
