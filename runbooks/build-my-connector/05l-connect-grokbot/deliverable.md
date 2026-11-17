# Deliverable: 05l-connect-grokbot

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connect.md`, plus `smoke.json` when GrokBot has its own entry; or `skipped.md` if the plan did not choose GrokBot.

## Format

`connect.md` fields: Harness and version; Route (own entry, or shares Claude Code's entry); Yes (who, when); Config changed and Backup (own entry only); Entry (server name, URL, how the key is held); In-harness check (tool count seen, the read question, answered yes or no); Smoke (own entry only: the command, with no key, and its result lines); Desktop app (its connectors listed as hosted, not portable yet); Rollback.

## Must be true

- `connect.md` has a **Method** line: GrokBot's own command, "shares Claude Code's entry", or "the person, in its settings". The agent never opened a GrokBot config.
- If GrokBot shares Claude Code's entry, that is stated plainly, with what revoking Claude Code's key does to GrokBot.
- If GrokBot has its own entry, it has its own door key, a backup existed before the change, and its smoke result is recorded.
- No upstream key sits in any GrokBot config.
- No value appears anywhere.

## Out of scope

- Moving the desktop app's hosted logins.
- Any other harness.
