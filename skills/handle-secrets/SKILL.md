---
name: handle-secrets
description: "The rules for keys, tokens, passwords and sign-ins in every Universal Connector stage: the agent never asks for, sees, prints, stores or moves a secret value, and the person does each secret step themselves with their own tools. Use before any stage that touches a connection, a credential store, a harness config or a smoke test."
---

# Handle secrets

These rules hold in every stage. They are stricter than any convenience.

## Firm rules

1. **Never ask for a value.** Not a key, token, password, one-time code, recovery code, cookie, connection string, private key or account id. Ask only for names and where things live.
2. **Never show, print, log, store or move a value.** The agent never reads a credential file, never runs a command that prints a secret (for example `secret-tool lookup`, `op read`, `pass show`, `security find-generic-password -w`, `cat` of a key file), and never writes a value into any file, message, task card or commit.
3. **Passwords stay in the person's password manager.** 1Password, Bitwarden, KeePassXC, the OS keychain or the browser's manager. The kit never collects, stores or moves a password, a one-time code or a recovery code, not even into the vault. Website sign-ins happen in the person's own browser, by the person.
4. **The person does every secret step.** They create keys in the vendor's console, run the vault's own store command in their own terminal, sign in through the browser, and place key files. The agent prepares the exact command with names filled in and waits.
5. **Values move in one process or not at all.** When an existing key must move from a plain file into a vault, the person runs a single command that reads the file and writes the vault (for example a store command fed from the file), so the value is never printed. Prefer issuing a fresh, narrower key over moving an old one.
6. **Names are fine; values are not.** Server names, variable names, vault entry names, profile names, host names, file paths and account display names may be shown.
7. **A safety hook is final.** If a hook blocks a command, stop that step and tell the person. Never look for another route to the same data.

## If a value appears

- If a value is pasted into the chat, printed by a tool, or seen in output: do not repeat it, quote it or copy it anywhere.
- Tell the person plainly that the value is exposed and should be rotated in that service.
- Record only "a value was exposed for <service>; rotation advised" in the stage output.
- If a kit tool printed it, that is a bug: stop and report it.

## Checks you can run

- `python tools/keyshape.py <folder>` before you hand in any output folder. It prints file, line and rule name only.
- The scanner and smoke tests run every output through a key-shape guard and stop rather than print a match.

These checks catch key shapes, not every secret. The rules above are the real protection.
