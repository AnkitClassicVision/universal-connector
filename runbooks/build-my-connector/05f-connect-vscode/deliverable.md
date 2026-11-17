# Deliverable: 05f-connect-vscode

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connect.md` and one `smoke-<agent>.json` per connected agent (`native`, `cline`, `continue`), or `skipped.md` if the plan chose none of them.

## Format

`connect.md` has one section per connected agent, each with: Agent and version; Yes (who, when); Config changed (path); Backup (path, or "new file"); Entry (server name, URL, how the key is held); Read timeout; In-harness check (tool count seen, the read question, answered yes or no); Smoke (the command, with no key, and its result lines); Rollback (the exact command that restores the backup).

## Must be true

- Each connected agent has its own door key, its own backup and its own smoke result.
- Only the files of the connected agents changed, and each had a backup before the change.
- No upstream key sits in any of these configs.
- No value appears anywhere.

## Out of scope

- Removing old connectors. That is a later, separate yes.
- Any other harness.
