# Deliverable: 04-resmoke

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

- `connections/<name>.json` for every connection tested.
- `harnesses/<id>.json`, `harnesses/<id>-canary.json` and `harnesses/<id>-revoked.json` for every connected harness.
- `resmoke.md`.

## Format

`resmoke.md`: the connection table and the harness table in the same form as `build-my-connector`'s `smoke-connections.md` and `smoke-harnesses.md`, then "Changed since last run".

## Must be true

- Every connection in the current manifest and every connected harness was tested, not only the changed ones.
- The tables match the JSON files.
- Removed harnesses no longer reach the door: their revoked key is refused.
- No value appears anywhere.

## Out of scope

- Fixing a failure. A failure goes back to `03a` or `03b`.
