# 03b-update-harnesses

## Purpose

Make the harness changes the person said yes to: add a harness, remove one, or give one a fresh door key.

## Inputs

| Source | Location | Why |
|---|---|---|
| Changes | `<run folder>/02-diff/output/manifest-changes.yaml` and `changes.md` | Only the items with a yes |
| Common steps | `skills/connect-harness/SKILL.md` | Backup, edit, check, smoke, roll back |
| Per-harness facts | `runbooks/build-my-connector/05x-connect-<harness>/STAGE.md` for the harness in hand | Its config places, entry, read timeout and limits |
| Secret rules | `skills/handle-secrets/SKILL.md` | The firm rules |

Read only what is listed here. This stage is a human yes point. It runs side by side with `03a-update-connections` and does not read its output.

## Process

For each harness change, on its own:

1. **Add**: follow `skills/connect-harness` with the facts from that harness's `05x` stage in `build-my-connector`. Never open the config: the harness's own command or `tools/add_entry.py`.
2. **Re-key**: the person issues a fresh door key for the harness into a new 0600 file and puts it where the harness holds its key (for a plain-key harness, `tools/add_entry.py --key-file <new file> --replace`), you run that harness's smoke test with `--key-file <new file>`, then the person revokes the old key with the door's own command, and you run `tools/smoke_harness.py ... --key-file <old key file> --expect-revoked` if they kept the old file, or skip that check and say so. The person then deletes the old key file.
3. **Remove**: remove only the door entry, with the harness's own command or in its own settings (the person), and the person revokes that harness's door key. If a backup is made, it goes into this stage's `backup/` folder in the run folder, never beside the config.
4. Write `harnesses-update.md`.

## Output

Write to `<run folder>/03b-update-harnesses/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/connect-harness`, `skills/handle-secrets`
- `tools/entry.py`, `tools/smoke_harness.py`
