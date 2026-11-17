# Deliverable: 05b-connect-claude-desktop

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connect.md` and `smoke.json`, or `skipped.md` if the plan did not choose Claude Desktop.

## Format

`connect.md` fields: Harness and version; Yes (who, when); App quit before the edit (yes or no); Config changed (path); Backup (path, or "new file"); Bridge (which program, and who decided to trust it); Entry (server name, URL, key file path and its mode); Read timeout; In-harness check (tool count seen, the read question, answered yes or no); Smoke (the command, with no key, and its result lines); Rollback (the exact command that restores the backup).

`smoke.json` is the `--json` output of `tools/smoke_harness.py` for this harness.

## Must be true

- `connect.md` has a **Method** line: the harness's own command (as run), `tools/add_entry.py` (with its receipt), or "the person, in the harness's settings". The agent never opened the config; backups sit in the run folder, owner-only.
- The app was quit before the edit, and a backup existed before the change.
- Only Claude Desktop's config changed.
- The key is this harness's own door key, in a file only the person can read, and not in the JSON.
- The in-harness check and the smoke test were both run, and their results are recorded as they came out.
- No value appears anywhere.

## Out of scope

- Removing old connectors or extensions. That is a later, separate yes.
- Any other harness.
