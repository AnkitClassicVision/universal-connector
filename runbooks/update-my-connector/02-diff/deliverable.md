# Deliverable: 02-diff

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

- `diff.json`: the output of `tools/diff_inventory.py --json`.
- `changes.md`: the change list with the person's decisions.
- `manifest-changes.yaml`: the connection and harness changes the person said yes to, in the same shape as `build-my-connector`'s `manifest-draft.yaml` and `harnesses.yaml`, with an `action` field (`add`, `remove`, `rotate`, `change`) on each item.

## Format

`changes.md`: a table with one row per change: Change, Kind, Why (from the diff or the person), Decision (yes, no, changed), Decided by and when. Then sections: Connections to add (with auth kind, vault entry name, scopes, tiers), Harnesses to add (with server name, key holding, read timeout, https), Removals, Rotations, Skills.

## Must be true

- Every item in `diff.json` and every item the person raised has a row and a decision.
- Every new connection and harness is planned as fully as in a build: auth kind, secret pointer, scopes, tiers with everything unknown red; server name, key holding, read timeout.
- `manifest-changes.yaml` holds only items with a yes.
- No value appears anywhere.

## Out of scope

- Making any change. That is `03a` and `03b`.
