# Deliverable: 03b-update-harnesses

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`harnesses-update.md` and one `smoke-<harness>.json` per added or re-keyed harness, or `skipped.md` if no harness change had a yes.

## Format

Yes (who, when); then one section per harness change: Harness, Action, Config changed, Method (the harness's own command, `tools/add_entry.py`, or the person in its settings), Backup (its path in the run folder), Entry (server name, URL, how the key is held), Old key revoked (yes, no, not applicable), Smoke (the command, with no key, and its result lines), Rollback.

## Must be true

- Every harness change with a yes in `02-diff` has a section; nothing without a yes was changed.
- Every config change had a backup first, in the run folder (owner-only), and only that harness's config changed.
- No config was opened by the agent; each change used the harness's own command, `tools/add_entry.py`, or the person.
- A re-keyed harness works on its new key, and its old key was revoked by the person.
- No value appears anywhere.

## Out of scope

- Connections in the door's manifest. That is `03a`.
