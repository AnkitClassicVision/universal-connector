# Deliverable: 05i-connect-hermes

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connect.md` and one `smoke-<profile>.json` per connected profile, or `skipped.md` if the plan did not choose Hermes.

## Format

`connect.md` has one section per connected profile, each with: Profile; Yes (who, when); Config changed (path); Backup (path, or "new file"); Entry (server name, URL, how the key is held); Read timeout; In-harness check (tool count seen, the read question, answered yes or no); Smoke (the command, with no key, and its result lines); Rollback (the exact command that restores the backup).

## Must be true

- Each section of `connect.md` has a **Method** line: `tools/add_entry.py` (with its receipt) or "the person, in the harness's settings". The agent never opened a config or `.env` file; backups sit in the run folder, owner-only.
- Each connected profile has its own door key, its own backup and its own smoke result.
- Only the configs of the connected profiles changed.
- No upstream key sits in any Hermes config.
- No value appears anywhere.

## Out of scope

- Removing Hermes's old MCP servers. That is a later, separate yes.
- Any other harness.
