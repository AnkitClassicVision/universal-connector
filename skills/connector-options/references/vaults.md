# Where secrets live: vault options

The door reads each secret from the vault into memory when a call needs it. The manifest holds only the entry name. Pick one vault for the door; the person may keep using other managers for their own passwords.

| Vault | Good when | Watch out | The person stores a value with |
|---|---|---|---|
| OS keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service) | One machine, one person. Nothing to install | Tied to the login session; a headless server may have no unlocked keyring | macOS: `security add-generic-password -a universal-connector -s <entry> -w` with no value after `-w`, so it prompts. Linux: `secret-tool store --label="<entry>" service universal-connector account <entry>` (prompts). Windows: Credential Manager in Control Panel |
| 1Password (CLI `op`) | They already use 1Password; shared vaults; service accounts for servers | Needs the CLI signed in, or a service account token for unattended use | Create the item in the 1Password app and paste the value there. The manifest records the `op://<vault>/<item>/<field>` reference |
| Bitwarden (CLI `bw`) or Bitwarden Secrets Manager | They already use Bitwarden | The password-manager CLI must be unlocked per session; Secrets Manager is a separate product for machines | Create the item in the Bitwarden app. Check the vendor docs for Secrets Manager |
| AWS Secrets Manager | The door runs on a server in AWS, or a team shares secrets | Costs per secret per month; needs AWS sign-in on the machine | The AWS console's "Store a new secret" page. Avoid putting the value on a command line |
| HashiCorp Vault or OpenBao | A team already runs one | Someone must run and unseal it | `vault kv put <mount>/<entry> value=-` reads the value from standard input. Check the vendor docs for your mount |
| pass or gopass | They use a GPG-based store | GPG key handling; files sync through Git | `pass insert <entry>` or `gopass insert <entry>` (both prompt) |
| An encrypted file (sops, age) | No keyring and no manager, for example a container | The decryption key must live somewhere safe; easy to get wrong | Check the vendor docs. Never leave a decrypted copy |

## Moving a key that already sits in a plain file

Prefer a fresh, narrower key from the vendor. If the old key must move, the person runs one command that reads the file and writes the vault, so the value is never printed. For example, on Linux: `secret-tool store --label="<entry>" service universal-connector account <entry> < <the file>`. Then, after the smoke tests pass, they remove the value from the old file and rotate it if it was ever shared.

## Never

- Paste a value into chat, a task card, a commit or a config the agent edits.
- Put a value on a command line (other users can read command lines).
- Keep a second copy "just in case".
