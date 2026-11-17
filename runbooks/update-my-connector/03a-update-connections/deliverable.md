# Deliverable: 03a-update-connections

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connections-update.md`, or `skipped.md` if no connection change had a yes.

## Format

Yes (who, when); then a table with one row per change: Connection, Action, Done by, Vault entry name, Old key revoked (yes, no, not applicable), Doctor row after. Then: Old copies left to clean; Exposed values ("rotation advised for <service>", or "none").

## Must be true

- Every connection change with a yes in `02-diff` has a row; nothing without a yes was changed.
- Every secret step was done by the person.
- A lower tier has the person's words recorded.
- The door's doctor ran after the changes.
- No value appears anywhere.

## Out of scope

- Harness entries. That is `03b`.
