---
name: update-my-connector
description: "Keeps an existing Universal Connector door current. Rescans the machine for names only, diffs against the last inventory, adds, removes or rotates connections and harness entries with the owner's yes, and re-runs every smoke test. Use when a new tool, key, harness or skill appeared, a key must be rotated, a harness is retired, or a regular check is due."
---

# Update my connector

## Outcome

The door matches what the person uses today. New connections and harnesses are added the same way the build added them, retired ones are removed, keys due for rotation are rotated, every smoke test passes again, and the owner sheet is current.

## Start a run

Start when the person asks to add, remove or rotate something, or when their regular check is due (they choose how often). Before `01-rescan`:

1. Read `skills/handle-secrets/SKILL.md`.
2. Find the last owner sheet and its baseline inventory path. Without them, run `build-my-connector` instead.

## Stage map

| Stage | Does | Needs | Gate |
|---|---|---|---|
| `01-rescan` | Names-only scan, plus "anything new?" questions | none | yes |
| `02-diff` | What changed since the baseline, and the person's decision on each change | `01-rescan` | yes |
| `03a-update-connections` | Add, remove or rotate connections: vault and door manifest | `02-diff` | no |
| `03b-update-harnesses` | Add, remove or re-key harness entries | `02-diff` | no |
| `04-resmoke` | Every connection and harness smoke test again | `03a`, `03b` | yes |
| `05-handoff` | The updated owner sheet and a new baseline | `02-diff`, `03a`, `03b`, `04-resmoke` | no |

Order, parallel work and gates come from `process.yaml`. Follow `AGENTS.md` at the repo root to run it.

## Shared skills

- `skills/handle-secrets`, `skills/connector-options`, `skills/connect-harness`
- `runbooks/build-my-connector`: its `05x` stages hold each harness's places and steps, and its `01b-ask` checklist is reused.

## Done means

`05-handoff/output/owner-sheet.md` is the new sheet, its baseline points at this run's inventory, and every gate passed.
