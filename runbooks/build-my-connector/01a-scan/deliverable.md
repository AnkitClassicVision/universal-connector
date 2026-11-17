# Deliverable: 01a-scan

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

- `inventory.json` and `inventory.md`, exactly as `tools/scan.py` wrote them.
- `scan-notes.md`, written by you from `inventory.json`.

## Format

`scan-notes.md` has these sections, in this order:

1. **Command**: the scan command as run, with its flags. Paths are fine. No values.
2. **Choices**: whether the person said yes or no to listing vault entry names, and which extra places they named.
3. **Needs a look**: every source or place with status `malformed`, `unreadable`, `too-large` or `error`, with the status. The person checks these themselves.
4. **Keys in plain files**: the count, and the names of the connections or variables involved.
5. **Auth summary**: how many connections use OAuth, an API key, a service account, a browser session, a password, and how many have no credential found.
6. **Skills**: counts by class, and the names of the external-api skills.

## Must be true

- The two inventory files are the scanner's own output, not edited or retyped.
- No value appears anywhere in the output folder: no key, token, password, cookie, one-time code, recovery code, connection string or account id.
- Every source the scanner knows shows a status, so nothing was silently skipped.
- Vault entry names appear only if the person said yes to that question, and `Choices` says what they said.
- Every number in `scan-notes.md` matches `inventory.json`.

## Out of scope

- Changing, moving or deleting any config, key or file.
- Opening any config or credential file directly.
- Unlocking a password manager or signing in to anything.
- Deciding tiers, scopes or which harnesses to connect. That is `02-plan`.
