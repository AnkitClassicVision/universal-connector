# 04-resmoke

## Purpose

Run every smoke test again, for every connection and every harness, so the whole door is proven after the change, not only the parts that changed.

## Inputs

| Source | Location | Why |
|---|---|---|
| Connection changes | `<run folder>/03a-update-connections/output/` | What changed in the manifest |
| Harness changes | `<run folder>/03b-update-harnesses/output/` | What changed in the harnesses |
| The steps | `runbooks/build-my-connector/06a-smoke-connections/STAGE.md` and `06b-smoke-harnesses/STAGE.md` | The same tests as the build |

Read only what is listed here.

## Process

1. Follow `build-my-connector` stage `06a-smoke-connections` for every connection in the door's current manifest, with a fresh `smoke` key in a 0600 file.
2. Follow `build-my-connector` stage `06b-smoke-harnesses` for every connected harness, including the canary and revoke check, with `--baseline-tools <last run's harnesses/<id>-tools.json>` added: it fails when the door now offers a new tool that Oddboro's read-only rule would not call read-only. Each such tool needs a tier in the manifest and the person's yes before it is offered.
3. Write the same files those stages hand in, under `connections/` and `harnesses/`, plus `resmoke.md` with both summary tables, the new and removed door tools, and a list of what changed since the last run.

## Output

Write to `<run folder>/04-resmoke/output/`. `deliverable.md` says what must be in it.

## Uses

- `tools/smoke_connection.py`, `tools/smoke_harness.py`, `tools/gotchas.py`
