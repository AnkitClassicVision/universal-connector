---
name: build-my-connector
description: "Builds one portable connector (the door) from the connections a person already has. Scans every agent harness, credential store and skill folder on their machine for names only, asks what else they use and where it lives, plans tiers and scopes, sets up each credential without the agent seeing it, runs the door, connects each chosen harness side by side, and smoke-tests every connection and harness. Use when someone wants to gather their MCP servers, API keys, OAuth logins and skills into one door that Claude Code, Codex, Oddboro and other harnesses share."
---

# Build my connector

## Outcome

The person ends with their own door: one service on their machine that holds all their connections, with one revocable key per harness. Every chosen harness reaches the door, every connection answers one read call, and the person has a sheet that says what is connected where and how to revoke it. No password, key or token was ever shown to, typed by or stored by the agent.

## Start a run

Start when someone asks to gather their connectors, keys, logins or skills into one place, or to plug their connections into another harness. Before stage 01 begins:

1. Read `skills/handle-secrets/SKILL.md`. Its rules apply to every stage.
2. Make the run folder (see `AGENTS.md`). Stages 01a and 01b start at once, side by side.
3. Tell the person in one line what will happen: a names-only scan, a short interview, a plan they approve, then one approved change at a time.

## Stage map

| Stage | Does | Needs | Gate |
|---|---|---|---|
| `01a-scan` | Names-only inventory of harness configs, credential stores, skills, ports | none | yes |
| `01b-ask` | Interview: what else they use and where each connection lives | none | yes |
| `02-plan` | Harness choice, one connection per real service, tiers, scopes, vault, auth plan | `01a-scan`, `01b-ask` | yes |
| `03-vault` | The person stores each secret, signs in, or places key files | `02-plan` | no |
| `04-door` | Install the door, run it on loopback, add an https route if a harness needs one | `02-plan`, `03-vault` | no |
| `05a` to `05m` `connect-<harness>` | One harness each, side by side, backup first | `02-plan`, `04-door` | no |
| `05n-carry-skills` | Copy portable skills into the chosen harnesses | `02-plan` | no |
| `06a-smoke-connections` | One read call per connection, by auth kind | `02-plan`, `04-door` | yes |
| `06b-smoke-harnesses` | Per harness: list, one call, refusals, revoke, gotchas | all `05a` to `05m` | yes |
| `07-handoff` | The owner sheet | `03-vault`, `04-door`, `05n`, `06a`, `06b` | no |

A connect stage for a harness the plan did not choose hands in `output/skipped.md` with one line, which completes it. Order, parallel work and gates come from `process.yaml`. Human yes points are in `human_gate`. Follow `AGENTS.md` at the repo root to run it.

## Shared skills

- `skills/handle-secrets`: the rules on values, passwords and sign-ins. Every stage.
- `skills/connector-options`: vaults, where the door runs, harness formats and known limits, auth kinds, tiers and scopes.
- `skills/connect-harness`: backup, edit, check and roll back one harness config.
- `recipes/`: one file per common service: auth kinds, MCP server status, tiers, scopes, smoke test.

## Done means

`07-handoff/output/owner-sheet.md` exists, every gate passed, and the person has the sheet. The run folder holds the inventory, the plan, each harness's backup path and every smoke result.
