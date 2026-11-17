# Deliverable: 05k-connect-oddboro

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`connect.md` and `smoke.json`, or `skipped.md` if the plan did not choose Oddboro.

## Format

`connect.md` fields: Oddboro address and kind; Version (and how it was found); Yes (who, when); Service (id as Oddboro shows it, the https address, "Takes a key", header name); Grant (which Odd, Read only); Key (saved on the desk task by the person; no value); Connected (yes or no, and the tool count shown); Read-only marks checked (yes or no); Odd chat check (the tool called, answered yes or no, Ledger clean of "could not start during a run"); Door audit (the calls seen, names only); Smoke (the command, with no key, and its result lines); Rollback (how to remove the grant and the service, and the note that the key may need pasting again).

`smoke.json` is the `--json` output of `tools/smoke_harness.py --harness oddboro`.

## Must be true

- Oddboro is v0.0.6 or later, and the version and how it was found are recorded. For v0.0.6 or v0.0.7, each runner's own limits are noted.
- The service address is https with the exact path and no redirect, and its host is in the door's host list.
- The grant is Read only, to one Odd.
- Every granted tool's full name fits Oddboro's limit, and all tools sit on the first page.
- The key was saved by the person on the desk task. No value appears anywhere.
- The Connected status, the Odd's read answer, the audit lines and the smoke result are recorded as they came out.

## Out of scope

- Grants to more Odds, or any Read and write grant. Those are later decisions by the person.
- Any other harness.
