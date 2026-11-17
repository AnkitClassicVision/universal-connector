# 03-vault

## Purpose

Get every credential the plan needs into place, with the person doing each secret step and no value ever passing through the agent.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/` | The connections, their auth kinds, vault entry names and the chosen vault |
| Options guide | `skills/connector-options/references/vaults.md` and `auth-and-logins.md` | The exact store command per vault, and who does what per auth kind |
| Secret rules | `skills/handle-secrets/SKILL.md` | The firm rules |

Read only what is listed here. This stage is a human yes point: start only after the person says yes to the list of vault writes.

## Process

1. Show the person the list of connections that need a credential, grouped by auth kind, with the vault entry name for each. Ask for their yes. Record it.
2. Work through the list one connection at a time. For each, give the person the steps for its auth kind, with every name filled in, then wait for them to say it is done:
   - **API key**: they create a fresh key with read-only scope in the vendor's console, then run the vault's own store command in their own terminal (from `vaults.md`). The value is typed or pasted only into that prompt. If an old key in a plain file must move instead, they run the one-process move command from `vaults.md`.
   - **OAuth**: nothing is stored yet. The sign-in happens through the door's own login flow in `04-door`, by the person, in their browser.
   - **Service account**: they create the account with a read-only role, download its key file to the path in the plan, and run `chmod 600` on it. You never open the file.
   - **Browser lane**: they open the lane's own browser profile and sign in themselves. Their password manager may fill the form. They type any one-time code.
   - **Hosted, not portable**: no action. Note it.
3. Never run a command that prints a secret to check it. The door doctor in `04-door` checks that each entry is present without showing it.
4. If the person pastes a value into the chat, follow "If a value appears" in `skills/handle-secrets`.
5. Write `vault-receipt.md` with the fields in `deliverable.md`.

## Output

Write to `<run folder>/03-vault/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connector-options`, `skills/handle-secrets`
