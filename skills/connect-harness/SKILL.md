---
name: connect-harness
description: "The common steps for connecting one agent harness to the door without the agent ever opening its config: confirm the plan chose it, get the person's yes, add one entry with the harness's own command or tools/add_entry.py (which backs the config up into the run folder), hold the harness's own door key in a 0600 file, set the read timeout, check it in the harness, smoke-test it on its own, and roll back if anything fails. Use inside every 05x-connect stage of build-my-connector and in update-my-connector."
---

# Connect one harness

Each `05x-connect-<harness>` stage gives the facts for one harness: where its config lives on each operating system, its own add command if it has one, the read-timeout setting and its known limits. These steps are the same for all of them.

## The rule that matters most

**Never open a harness config, not even to edit it.** Configs often hold other inline keys; an editor or a `cat` reads all of them into the agent's context. Add the entry with the harness's own command where one exists, otherwise with `python tools/add_entry.py`, which reads, backs up, adds and checks the file in its own process and prints only what it did. If neither fits, the person adds it in the harness's own settings screen. A safety hook that blocks a read is final: stop that step.

## Steps

1. **Chosen?** Read `harnesses.yaml` from `02-plan/output/`. If this harness is not chosen, write `output/skipped.md` with one line, "Not chosen in the plan", and stop. No yes is needed for that.
2. **Ask for the yes.** Say which file will change, by which command, and what one entry it adds. Wait for the person's yes and record who said it and when. Nothing changes before this.
3. **Close the app** if it is a desktop app or editor. Some apps rewrite their config when they quit and would undo the change.
4. **The key goes in a file.** The person issues one door key for this harness with the door's own command, written to a file only they can read (mode 600), at the path the plan names (for example `~/.config/universal-connector/keys/<harness>.key`). Never paste it into chat. One key per harness; never reuse another harness's key. Where the harness reads the key from an environment variable, the person makes that variable available to the harness from the file, themselves; the agent never reads, sets or prints it.
5. **Add one entry**, by one of these, in this order:
   - the harness's own command (named in the stage), with the entry from `python tools/entry.py --harness <id> --url <door url> --key-env <name> --read-timeout <seconds>`;
   - `python tools/add_entry.py --harness <id> --config <path> --url <door url> --key-env <name> --backup-dir <run folder>/<stage>/backup`, adding `--key-file <path>` for a harness that keeps the key in its own config. It backs the config up into the run folder (folder 0700, file 0600), never beside the config, refuses a file it cannot change safely, and prints the backup path;
   - the person, in the harness's own settings screen.
   Record which one was used, and the command line (it holds paths and names only).
6. **Set the read timeout** above the door's slowest call, using the setting named in the stage, by the same route as step 5.
7. **Check in the harness.** Start the harness. Ask it to list the door's tools, then to answer one read question. The person confirms what they saw.
8. **Smoke-test this harness on its own:** `python tools/smoke_harness.py --harness <id> --url <the URL this harness uses> --key-file <this harness's key file> --server-name <name> --read-timeout <seconds> --plan <run folder>/02-plan/output/manifest-draft.yaml --json`. The tool reads the key from the file itself. Save the output.
9. **If anything fails,** restore the backup (copy it from the run folder back over the config, or remove the new entry with the harness's own command), restart the harness, and record what failed. Do not try a second, different change without telling the person.
10. **Write `connect.md`** with the fields in the stage's `deliverable.md`.

## Backups

Backups live in the run folder only (`<run folder>/<stage>/backup/`, folder 0700, files 0600). They may hold other keys from the config, so they are listed in the owner sheet and deleted after `06b` passes, with the person's yes.

## Never

- Open, print or copy a harness config into the agent's context.
- Put an upstream key (a service's own API key or token) into a harness config. Only this harness's door key.
- Remove the harness's old connectors in this stage. That happens after `06b` passes, as a separate yes, listed in the owner sheet.
- Edit a second harness in the same stage.
