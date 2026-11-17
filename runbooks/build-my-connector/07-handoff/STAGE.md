# 07-handoff

## Purpose

Give the person one sheet that says what is connected where, how to revoke or rotate anything, how to add a connection, and what is left for them to clean up.

## Inputs

| Source | Location | Why |
|---|---|---|
| Vault receipt | `<run folder>/03-vault/output/vault-receipt.md` | Entry names and old plain-file copies |
| Door | `<run folder>/04-door/output/door.md` | Door address, service and folders |
| Carried skills | `<run folder>/05n-carry-skills/output/` | What was carried where |
| Connection smoke | `<run folder>/06a-smoke-connections/output/smoke-connections.md` | Which connections work |
| Harness smoke | `<run folder>/06b-smoke-harnesses/output/smoke-harnesses.md` | Which harnesses work |

Read only what is listed here.

## Process

1. Ask the person to revoke the `smoke` key from `06a` with the door's own command. Record that they did.
2. Write `owner-sheet.md` with the sections in `deliverable.md`, in plain words, for the person (not for an agent).
3. Write the baseline path for `update-my-connector` into the sheet: `<run folder>/01a-scan/output/inventory.json`. Write the path only; this stage does not read that file.
4. Read the "Still to do" list to the person. Each item there is theirs to decide and do; none is done by this run.

## Output

Write to `<run folder>/07-handoff/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/handle-secrets`
