# 03a-update-connections

## Purpose

Make the connection changes the person said yes to: add, remove, rotate, move a plain-file key into the vault, or change a tier or scope. The person does every secret step.

## Inputs

| Source | Location | Why |
|---|---|---|
| Changes | `<run folder>/02-diff/output/manifest-changes.yaml` and `changes.md` | Only the items with a yes |
| Auth and vault steps | `skills/connector-options/references/auth-and-logins.md` and `vaults.md` | Who does what per auth kind; the store command per vault |
| Secret rules | `skills/handle-secrets/SKILL.md` | The firm rules |

Read only what is listed here. This stage is a human yes point. It runs side by side with `03b-update-harnesses` and does not read its output.

## Process

1. Confirm the list with the person and get their yes for this stage's changes.
2. **Add**: the person sets up the credential as in `build-my-connector` stage `03-vault`, then you add the connection to the door's manifest with the door's own command or format, and the person signs in for OAuth through the door's login flow.
3. **Rotate**: the person creates a fresh key in the vendor's console, stores it under the same vault entry name with the vault's own command, then revokes the old key in the vendor's console. For OAuth, the person signs in again through the door.
4. **Move a plain-file key**: as in `vaults.md`, by the person, in one process. The old file is cleaned only after `04-resmoke` passes.
5. **Remove**: take the connection out of the door's manifest. The person deletes its vault entry and revokes its key in the vendor's console when they choose.
6. **Tier or scope change**: edit the manifest. A move to a lower tier (red to yellow, yellow to green) needs the person's words recorded.
7. Reload the door and run its doctor. Record each row.
8. Write `connections-update.md`.

## Output

Write to `<run folder>/03a-update-connections/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connector-options`, `skills/handle-secrets`
