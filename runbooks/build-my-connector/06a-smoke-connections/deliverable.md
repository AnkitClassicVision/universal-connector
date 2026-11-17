# Deliverable: 06a-smoke-connections

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

- `connections/<name>.json`: the `--json` output of `tools/smoke_connection.py`, one file per tested connection.
- `smoke-connections.md`: the summary.

## Format

`smoke-connections.md`: the door URL; the smoke key file's path (never the key); a table with one row per connection in the manifest: Connection, Auth kind, Read tool, Result (PASS or FAIL), Failing check, Fix hint, Signed in as (where shown). Then a list of connections not tested, each with its reason.

## Must be true

- Every connection in the manifest is either tested on its own or listed as not tested with a reason.
- Every tested connection passes. A failure is fixed in the stage that owns it (`02-plan`, `03-vault` or `04-door`) and tested again here. A connection the person decides to drop is listed as not tested, with their words.
- Every tested connection has its own JSON file, and the table matches those files.
- Each test used exactly one read tool from the connection's green tools, plus a who-am-I read where one was used.
- A browser-lane connection shows a signed-in check.
- No value appears anywhere: no key, no tool result content, no cursor.

## Out of scope

- Fixing a failing connection by changing its tier, scope or tools. A fix goes back to the stage that owns it.
- Testing harnesses. That is `06b`.
