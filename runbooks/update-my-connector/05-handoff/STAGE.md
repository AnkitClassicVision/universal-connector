# 05-handoff

## Purpose

Give the person an updated owner sheet and a new baseline for next time.

## Inputs

| Source | Location | Why |
|---|---|---|
| Changes | `<run folder>/02-diff/output/changes.md` | What was decided |
| Connection changes | `<run folder>/03a-update-connections/output/` | What was done to connections |
| Harness changes | `<run folder>/03b-update-harnesses/output/` | What was done to harnesses |
| Smoke | `<run folder>/04-resmoke/output/resmoke.md` | What works now |
| The last owner sheet | The path the person gives (the previous run's `owner-sheet.md`) | Everything that did not change carries over from it |
| The sheet's sections | `runbooks/build-my-connector/07-handoff/deliverable.md` | The same layout as the build's sheet |

Read only what is listed here.

## Process

1. Ask the person to revoke this run's `smoke` key and delete its key file. Record it.
2. List this run's backups (from `03b`); ask whether to delete them now that `04-resmoke` passed, and delete only on a yes.
3. Start from the last owner sheet. Write `owner-sheet.md` in the build's layout, with every row that did not change carried over, this run's changes applied, and a "Changed in this run" section at the top.
4. Set the baseline to this run's `<run folder>/01-rescan/output/inventory.json` and saved tool lists (the paths only).

## Output

Write to `<run folder>/05-handoff/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/handle-secrets`
