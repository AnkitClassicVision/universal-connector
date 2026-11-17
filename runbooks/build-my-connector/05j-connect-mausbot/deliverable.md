# Deliverable: 05j-connect-mausbot

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connect.md` and `smoke.json`, or `skipped.md` if the plan did not choose OpenMausBot.

## Format

`connect.md` fields: Harness and version; Yes (who, when); App stopped before the edit (yes or no); Config changed (path); Backup (path, or "new file"); Entry (server name, URL, key held in the file, file mode); Read timeout; In-harness check (tool count seen, the read question, answered yes or no); Smoke (the command, with no key, and its result lines); Rollback (the exact command that restores the backup).

`smoke.json` is the `--json` output of `tools/smoke_harness.py` for this harness.

## Must be true

- `connect.md` has a **Method** line: `tools/add_entry.py` (with its receipt) or "the person, in the app's settings". The agent never opened the config; backups sit in the run folder, owner-only.
- Only OpenMausBot's config changed, and a backup existed before the change.
- The key in the file is OpenMausBot's own door key, and the file is readable only by the person.
- The in-harness check and the smoke test were both run, and their results are recorded as they came out.
- No value appears anywhere.

## Out of scope

- Switching off its older connectors. That is a later, separate yes.
- Any other harness.
