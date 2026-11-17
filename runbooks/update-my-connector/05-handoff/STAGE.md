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
| The sheet's sections | `runbooks/build-my-connector/07-handoff/deliverable.md` | The same layout as the build's sheet |

Read only what is listed here.

## Process

1. Ask the person to revoke this run's `smoke` key. Record it.
2. Write `owner-sheet.md` in the build's layout, updated with this run's changes, plus a "Changed in this run" section at the top.
3. Set the baseline to this run's `<run folder>/01-rescan/output/inventory.json` (the path only).

## Output

Write to `<run folder>/05-handoff/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/handle-secrets`
