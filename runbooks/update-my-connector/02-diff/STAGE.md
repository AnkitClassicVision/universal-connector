# 02-diff

## Purpose

Say exactly what changed since the last run, and get the person's decision on each change.

## Inputs

| Source | Location | Why |
|---|---|---|
| Rescan | `<run folder>/01-rescan/output/` | The new inventory and what the person said |
| Baseline | The inventory path named in `rescan-notes.md` | What it was last time |
| Last owner sheet | The path the person gives | What is connected now |
| Options guide | `skills/connector-options/` | Trade-offs for any new choice |
| Recipes | `recipes/` | For new services |

Read only what is listed here.

## Process

1. Run `python tools/diff_inventory.py <baseline> <run folder>/01-rescan/output/inventory.json --json` and save it as `diff.json`.
2. Build one change list from `diff.json` and from what the person said in `rescan-notes.md`. Each change is one of: add connection, remove connection, rotate key, move a plain-file key into the vault, change tier or scope, add harness, remove harness, re-key harness, carry skill, stop carrying skill.
3. For each new connection or harness, plan it the way `build-my-connector` stage `02-plan` does: auth kind and who does each step, vault entry name, scopes, tool tiers (anything unknown is red); for a harness: server name, key holding, read timeout, and https if it needs it.
4. Show the change list to the person. Ask for a yes, a no or a change on each item. Record their words and the date.
5. Write `changes.md` and `manifest-changes.yaml` as `deliverable.md` says.

## Output

Write to `<run folder>/02-diff/output/`. `deliverable.md` says what must be in it.

## Uses

- `tools/diff_inventory.py`
- `skills/connector-options`, `skills/handle-secrets`
- `recipes/`
