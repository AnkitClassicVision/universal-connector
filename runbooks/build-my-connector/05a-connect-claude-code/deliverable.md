# Deliverable: 05a-connect-claude-code

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connect.md` and `smoke.json`, or `skipped.md` if the plan did not choose Claude Code.

## Format

`connect.md` fields: Harness and version; Yes (who, when); Config changed (path); Backup (path, or "new file"); Entry (server name, URL, how the key is held, by variable name); Read timeout (setting and value); In-harness check (tool count seen, the read question, answered yes or no); Smoke (the command, with no key, and its result lines); Rollback (the exact command that restores the backup).

`smoke.json` is the `--json` output of `tools/smoke_harness.py` for this harness.

## Must be true

- Only Claude Code's config changed, and a backup existed before the change.
- The entry uses Claude Code's own door key, held by reference. No upstream key sits in the config.
- The in-harness check and the smoke test were both run, and their results are recorded as they came out.
- No value appears anywhere.

## Out of scope

- Removing Claude Code's old connectors. That is a later, separate yes in the owner sheet.
- Any other harness.
