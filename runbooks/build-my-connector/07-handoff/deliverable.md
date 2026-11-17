# Deliverable: 07-handoff

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`owner-sheet.md`.

## Format

Sections, in this order:

1. **Your door**: address (and https route), the service name, how to stop, start and check it, where its manifest and state live.
2. **Harnesses**: one row per harness in `harnesses.yaml`: harness, chosen or not, how the entry was added (Method), server name, where its key is held (the key file path and, where used, the variable name; for harnesses that keep the door key in their own config, say so), how to revoke that key, smoke result.
3. **Connections**: one row each: connection, auth kind, vault entry name or key file path, tiers in short, scopes, smoke result.
4. **Revoke or rotate**: revoke one harness's key; rotate an upstream key (the person stores a fresh one with the vault's own command, then runs that connection's smoke test); sign in again for OAuth.
5. **Add a connection or a harness**: run `update-my-connector`.
6. **Skills carried**: which, where, and how to remove each.
7. **Still to do (yours)**: old keys still in plain files (remove, then rotate if ever shared); old connectors in each harness to switch off; hosted logins that are not portable; anything that failed a smoke test.
8. **Backups**: every backup path from the connect stages, all in the run folder, and whether the person said yes to deleting them after `06b` passed (deleted, or kept until they say so).
9. **Baseline**: the path of the inventory and of the saved tool lists to compare against next time.
10. **Smoke key**: revoked and its key file deleted (yes or no).

## Must be true

- Every harness in `harnesses.yaml` and every connection appears, with its smoke result or why it was skipped.
- Every backup is listed until the person says yes to deleting it; none is deleted without that yes.
- Every revoke and rotate step names the command or screen, and says who does it.
- Every old plain-file copy from the vault receipt appears under "Still to do".
- No value appears anywhere.

## Out of scope

- Doing any item under "Still to do".
