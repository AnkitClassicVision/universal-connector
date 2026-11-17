# 01-rescan

## Purpose

Take a fresh names-only inventory, and ask what is new that a scan cannot see.

## Inputs

| Source | Location | Why |
|---|---|---|
| The machine, through the scanner only | `tools/scan.py` | Names, kinds and locations, never values |
| The last owner sheet | The path the person gives | The flags used last time (projects, extra files, vault opt-in) |
| Missed places checklist | `runbooks/build-my-connector/01b-ask/references/missed-places.md` | The same checklist as the build |
| Secret rules | `skills/handle-secrets/SKILL.md` | The firm rules |

Read only what is listed here. Never open a config or credential file yourself.

## Process

1. Ask whether to reuse last time's choices: project folders, extra files, and the yes or no on listing vault entry names. Ask the vault question again; last time's yes does not carry over.
2. Run `python tools/scan.py --out <run folder>/01-rescan/output` with those flags.
3. Run `python tools/keyshape.py <run folder>/01-rescan/output`. Any hit: stop, delete the output, report a bug.
4. Ask: "Since last time, what is new: a service, a website login, a database, a harness, a skill? Anything you stopped using? Any key that should be rotated?" Use the missed places checklist for prompts. Names and places only.
5. Write `rescan-notes.md` with the sections in `deliverable.md`.

## Output

Write to `<run folder>/01-rescan/output/`. `deliverable.md` says what must be in it.

## Uses

- `tools/scan.py`, `tools/keyshape.py`
- `skills/handle-secrets`
