# Service name

One or two lines: what the service is and what an agent usually reads from it.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | Say when a key fits this service. | The person creates the key in the vendor UI and stores it with the vault's own command. The value never passes through the agent. |
| OAuth | Say when a sign-in fits this service. | The person signs in once through the door's login flow or the vendor's. The agent never handles codes or tokens. |
| Service account | Say if the service offers one, and who may create it. | The person places the key file with mode 0600. The door reads it by path. |
| Website login (browser lane) | Only when there is no API. | The person signs in themselves in the browser lane. Passwords stay in their password manager. |

Delete the rows that do not apply. The kit never asks for, collects, stores, prints or moves a password, one-time code or recovery code.

## Connect it

- Official MCP server: yes, no, or "check the vendor docs". Say remote or local, and OAuth or key.
- Community MCP servers: say if they exist, or "check the vendor docs".
- Direct API adapter: say when the door needs its own adapter instead of an MCP server.

Do not write an address, package name or endpoint you are not sure of. Say "find the server address in the vendor's MCP docs".

## Tiers

| Tool type | Tier |
|---|---|
| Read or search | green |
| Reversible draft that nobody else acts on | yellow |
| Send, post, delete, pay, deploy, change permissions, or write records other people act on | red |

When unsure, red.

## Scope hints

- Ask for read-only scopes or roles first. Name them, or say "check the vendor docs".
- Keep work and personal accounts as separate connections.

## Smoke test

Name one read call that proves the credential works without showing it. Prefer a "signed in as <account name>" read when the API offers one.

```bash
python tools/smoke_connection.py --url <door url> --key-env DOOR_KEY --connection <name> --tool <read tool> --args '{}' --auth-kind <api-key|oauth|service-account|browser-session>
```

Add `--whoami-tool <tool>` when a who-am-I read exists.

## Gotchas

- Short bullets: paging cursors, rate limits, admin consent, tokens that expire.
