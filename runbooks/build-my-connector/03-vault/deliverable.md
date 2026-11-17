# Deliverable: 03-vault

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`vault-receipt.md`.

## Format

1. **Yes**: who said yes to the vault writes, and when.
2. **Receipts**: a table with one row per connection in the plan. Columns: Connection, Auth kind, Vault entry name or key file path, Done by (always the person), Status (`stored`, `fresh key stored`, `moved from a plain file`, `sign-in in 04-door`, `key file placed`, `browser lane signed in`, `hosted, not portable`, `skipped: <reason>`).
3. **Old copies**: every plain file that still holds an old value, to be cleaned after the smoke tests pass.
4. **Exposed values**: any value that was pasted or shown, as "rotation advised for <service>", or "none".

## Must be true

- Every connection in the plan has a row.
- Every secret step was done by the person. The agent typed, pasted or read no value.
- No value appears anywhere in the output.

## Out of scope

- Checking a value by printing it.
- Installing the door or editing a harness config.
