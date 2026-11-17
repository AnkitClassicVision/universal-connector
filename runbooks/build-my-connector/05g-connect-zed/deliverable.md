# Deliverable: 05g-connect-zed

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connect.md` and `smoke.json`, or `skipped.md` if the plan did not choose Zed.

## Format

`connect.md` fields: Harness and version; Yes (who, when); Config changed (path); Backup (path, or "new file"); Entry (server name, URL, how the key is held); Read timeout; In-harness check (tool count seen, the read question, answered yes or no); Smoke (the command, with no key, and its result lines); Rollback (the exact command that restores the backup).

`smoke.json` is the `--json` output of `tools/smoke_harness.py` for this harness.

## Must be true

- `connect.md` has a **Method** line: the harness's own screen, `tools/add_entry.py` (with its receipt), or "the person, in the harness's settings". The agent never opened the settings file; backups sit in the run folder, owner-only.
- Only Zed's settings changed, comments and other entries kept, and a backup existed before the change.
- The key is Zed's own door key. No upstream key sits in the settings. If the key had to sit in the file, the file is readable only by the person.
- The in-harness check and the smoke test were both run, and their results are recorded as they came out.
- No value appears anywhere.

## Out of scope

- Removing Zed's old context servers. That is a later, separate yes.
- Any other harness.
