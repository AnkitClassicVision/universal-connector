---
name: connector-options
description: "Plain trade-offs for every Universal Connector setup choice: which vault holds the secrets, where the door runs, how each harness connects and its known limits, how each auth kind is set up and who does each step, and how to pick tiers and scopes. Use when a person must choose an option in the plan, vault, door or connect stages, or asks which option fits them."
---

# Connector options

Show the person the options that apply, with the trade-offs in these files, and let them choose. Record the choice in the plan. Recommend the first option in each list unless their answers point elsewhere.

| Choice | Read | Default |
|---|---|---|
| Where secrets live | `references/vaults.md` | The OS keyring |
| Where the door runs | `references/door-placement.md` | This machine, loopback only |
| How each harness connects, and its limits | `references/harnesses.md` | One entry per harness, key by reference |
| Oddboro versions, address rules and smoke test | `references/oddboro.md` | v0.0.6 or later, short https address |
| How each connection signs in, and who does what | `references/auth-and-logins.md` | A fresh read-scoped API key, or one OAuth sign-in |
| Tiers and scopes | `references/tiers-scopes.md` | Read only (green); everything unknown is red |

Rules that hold for every choice:

- The person makes every choice that changes access. The agent explains and records.
- An option marked "check the vendor docs" is not verified here. Say so when you offer it.
- `skills/handle-secrets` applies to every option.
