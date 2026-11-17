---
name: connect-harness
description: "The common steps for connecting one agent harness to the door: confirm the plan chose it, close the app, back up its config, add one entry with this harness's own door key by reference, set the read timeout, check it in the harness, smoke-test it on its own, and roll back if anything fails. Use inside every 05x-connect stage of build-my-connector and in update-my-connector."
---

# Connect one harness

Each `05x-connect-<harness>` stage gives the facts for one harness: where its config lives on each operating system, the entry format, the read-timeout setting and its known limits. These steps are the same for all of them.

## Steps

1. **Chosen?** Read `harnesses.yaml` from `02-plan/output/`. If this harness is not chosen, write `output/skipped.md` with one line, "Not chosen in the plan", and stop.
2. **Ask for the yes.** Say exactly which file you will change and what you will add. Wait for the person's yes. This stage is a human yes point.
3. **Close the app** if it is a desktop app or editor. Some apps rewrite their config when they quit and would undo the edit.
4. **Back up.** Copy the config file to `<file>.bak-<run id>` next to it, and record that path. If the file does not exist yet, record "new file". Never overwrite an earlier backup.
5. **Get this harness's key.** Ask the person to issue one door key for this harness with the door's own command. The door writes it to the place the plan names (an environment variable for the harness, the OS keyring, or a 0600 file). Never paste it into chat. One key per harness; never reuse another harness's key.
6. **Add one entry.** Print it with `python tools/entry.py --harness <id> --url <door url from 04-door> --key-env <name from the plan> --read-timeout <seconds>`. Add it with the harness's own command if it has one, or edit the file with the editing tool. Change nothing else in the file. Where the harness can only hold the key in its own settings screen, the person pastes it there themselves.
7. **Set the read timeout** above the door's slowest call, using the setting named in the stage.
8. **Check in the harness.** Start the harness. Ask it to list the door's tools, then to answer one read question. The person confirms what they saw.
9. **Smoke-test this harness on its own:** `python tools/smoke_harness.py --harness <id> --url <the URL this harness uses> --key-env <name> --server-name <name>`. Save the JSON output.
10. **If anything fails,** restore the backup (copy it back over the file), restart the harness, and record what failed. Do not try a second, different edit without telling the person.
11. **Write `connect.md`** with the fields in the stage's `deliverable.md`.

## Never

- Put an upstream key (a service's own API key or token) into a harness config. Only this harness's door key.
- Remove the harness's old connectors in this stage. That happens after `06b` passes, as a separate yes, listed in the owner sheet.
- Edit a second harness in the same stage.
