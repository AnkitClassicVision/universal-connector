# Deliverable: 01b-ask

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

`interview.md`.

## Format

Three sections:

1. **Services**: a table with one row per service the person named. Columns: Service, Group (saas, internal-api, website, database, local-tool, other-service), Where it lives, How they sign in, Work or personal, Notes.
2. **Missed places checklist**: every line of `references/missed-places.md`, each marked `yes`, `no` or `skip`, with a short note for each `yes`.
3. **Read back**: one line saying the person heard the summary, and any corrections they made.

Use the person's own words for service names. Write "I don't know" where they did not know. Never guess for them.

## Must be true

- Every group in the interview was asked, even if the answer was "none".
- Every service row has an answer for where it lives and how they sign in, even if the answer is "I don't know".
- Every checklist line is marked.
- No value appears: no password, key, token, one-time code, recovery code, cookie, connection string or account id. If one was pasted, the notes say only that rotation was advised.
- Vendor-hosted connectors (logins kept on a vendor's servers) are marked as such, because they may not be portable.

## Out of scope

- Reading the scan output. This stage runs side by side with the scan.
- Asking for, typing or storing any secret.
- Deciding what to connect. That is `02-plan`.
