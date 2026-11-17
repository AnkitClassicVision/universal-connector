# Trello

Boards, lists and cards. Agents usually read boards and cards.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| API key | You use an API key and a user token from a Trello Power-Up. | The person creates the Power-Up, approves the token for their account, and stores both values with the vault's own command. The values never pass through the agent. |
| OAuth | An app signs in on the person's behalf (check the vendor docs). | The person signs in once through the vendor's login flow. The agent never handles codes or tokens. |

## Connect it

- Official MCP server: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: a reasonable choice for a few read tools.

## Tiers

| Tool type | Tier |
|---|---|
| Read boards, lists, cards, members | green |
| Search cards | green |
| Create or move a card | red |
| Comment, assign, add a label | red |
| Delete, archive, change board members | red |

## Scope hints

- When you approve the token, choose read access only, if the screen offers it.
- Choose an expiry for the token instead of "never" when you can.

## Smoke test

Read the current member, then one board.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection trello --tool <read board tool> --args '{}' --auth-kind api-key --whoami-tool <current member tool>
```

## Gotchas

- A token approved with read and write reaches every board the person can see.
- The API key and the token are two separate values. Store both in the vault under separate names.
