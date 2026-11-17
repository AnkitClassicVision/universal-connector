# 05m-connect-other

## Purpose

Connect any other MCP-capable client the person named, using the generic form: the door URL plus one `Authorization` header, with its own door key.

## Inputs

| Source | Location | Why |
|---|---|---|
| Plan | `<run folder>/02-plan/output/harnesses.yaml` | Which other clients; their settings places; server name |
| Door | `<run folder>/04-door/output/door.md` | The door URL, and the https route if the client needs one |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Formats and limits | `skills/connector-options/references/harnesses.md` | The generic entry |

Read only what is listed here. Never open the client's config. The person's yes comes in step 2 of the common steps, once per client.

## Process

Follow `skills/connect-harness` once per other client. The client-specific parts:

1. **Ask** the client's name and version, where its MCP settings live, whether it needs https, whether it can hold a key by reference, and whether it has a read-timeout setting. Write "unknown" where the person does not know, and check the client's docs together.
2. **Entry**: `python tools/entry.py --harness other --url <door url>` prints the URL and the header with a placeholder. The person puts this client's door key in the client's own settings screen or command. The agent does not edit the client's files.
3. **https**: if the client needs it, use the https route from `04-door`.
4. **Check**: the client lists the door's tools and answers one read question.
5. **Smoke**, once per client: `python tools/smoke_harness.py --harness other --url <url> --key-file <that client's key file> --server-name <the name the client uses> --plan <run folder>/02-plan/output/manifest-draft.yaml --json`.

## Output

Write to `<run folder>/05m-connect-other/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/connector-options`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
