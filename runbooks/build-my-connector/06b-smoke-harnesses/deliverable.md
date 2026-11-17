# Deliverable: 06b-smoke-harnesses

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

- `harnesses/<id>.json`, `harnesses/<id>-canary.json` and `harnesses/<id>-revoked.json` for every connected harness or agent, and `harnesses/<id>-tools.json` (names and read-only marks).
- `smoke-harnesses.md`: the summary.

## Format

`smoke-harnesses.md`: a table with one row per connected harness or agent: Harness, URL, Server name, Live key result, Canary result, Revoked result, Read limit, Route Host (or "loopback"), In-harness check, Failing checks, Entry added by. Then a list of harnesses that were skipped in `05x`, with the reason.

"Entry added by" is the Method line from that harness's `connect.md`: the harness's own command, `tools/add_entry.py`, or the person in the harness's settings.

## Must be true

- Every connected harness has all of its JSON files, and the table matches them.
- Every live and canary run passes. A failure is fixed in that harness's `05x` stage and tested again here.
- The live key lists tools and makes one read-only call; no key, a wrong key and a browser Origin are refused; an unlisted Host is refused.
- The canary key was revoked, and the revoked run shows the refusal. The live key was not revoked.
- Every full tool name fits each harness's limit, and harnesses that read only the first page see every tool.
- Each harness's read timeout is above the door's slowest call.
- No entry was added by opening a config in an editor or by reading it into the agent's context.
- No value appears anywhere.

## Out of scope

- Changing a harness config. A failure goes back to that harness's `05x` stage.
