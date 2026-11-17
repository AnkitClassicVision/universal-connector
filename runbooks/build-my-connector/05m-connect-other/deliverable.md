# Deliverable: 05m-connect-other

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connect.md` and one `smoke-<client>.json` per connected client, or `skipped.md` if the plan named no other client.

## Format

`connect.md` has one section per client: Client and version; Yes (who, when); Settings place; Backup (path, or "settings screen, no file", or "new file"); Entry (server name, URL, how the key is held); https needed (yes, no, unknown); Read timeout; In-harness check (tool count seen, the read question, answered yes or no); Smoke (the command, with no key, and its result lines); Rollback.

## Must be true

- Each section of `connect.md` has a **Method** line: the client's own command or screen, used by the person. The agent never opened a client config.
- Each client has its own door key and its own smoke result.
- Every unknown is written as unknown, not guessed.
- No upstream key sits in any client's settings.
- No value appears anywhere.

## Out of scope

- Any harness that has its own `05x` stage.
