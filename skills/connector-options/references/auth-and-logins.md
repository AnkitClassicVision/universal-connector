# Auth, passwords and website logins

## Firm rules

- The kit never asks for, collects, stores, prints or moves a password, a one-time code or a recovery code.
- Passwords stay in the person's password manager: 1Password, Bitwarden, KeePassXC, the OS keychain or the browser's own manager.
- The agent never handles OAuth codes or tokens, never types a password, and never reads a key file.
- Every secret step below is done by the person. The agent prepares names and commands, then waits.

## Per auth kind: how it is set up, and who does each step

| Auth kind | Setup | The person does | The agent does |
|---|---|---|---|
| API key | A key in the vault; the manifest names the entry | Creates a fresh key with read-only scope in the vendor's console. Runs the vault's own store command in their own terminal (see `vaults.md`); the value never passes through the agent | Names the vault entry, fills in the command, records "stored" when told, checks with the door doctor |
| OAuth | The door holds its own sign-in for the connection | Signs in once, fresh, through the door's own login flow or the vendor's page, in their browser. Approves only the scopes in the plan | Starts the door's login command when asked, then checks the doctor shows the connection signed in. Never sees codes or tokens |
| Service account | A key file the door reads by path, or the key stored in the vault | Creates the account with a read-only role in the vendor console, downloads the key, puts it at the agreed path and runs `chmod 600` on it | Records the path in the manifest, never opens the file |
| Website login with no API | A browser lane: a browser profile used only by the door, with the person's own saved session | Opens the lane's profile and signs in themselves. Their password manager may fill the form; one-time codes are typed by them | Records which site uses the lane. Never sees the password. Treats every action on the site as red unless the plan says otherwise |
| Vendor-hosted connector | The login lives on the vendor's servers (for example connectors inside a chat app) | Nothing now | Lists it as "hosted, not portable yet", with the one consent or export that would make it portable |

## Plain-file tokens

The scan flags keys and tokens in plain files (config files, `.env` files, shell profiles, CLI stores). For each one, suggest moving it into the vault, with the person doing the move (see `vaults.md`), then rotating it if it was ever shared or committed. A harness's own sign-in (for example its OAuth token cache) stays where it is; the door gets its own sign-in.

## Smoke test per auth kind

| Auth kind | Proof that the credential works, without showing it |
|---|---|
| API key | One read call through the door succeeds |
| OAuth | One read call succeeds, plus a "signed in as <account name>" read where the API offers one |
| Service account | One read call succeeds; a who-am-I read where the API offers one |
| Website login | A "signed in as" check on the site through the lane is required |

`tools/smoke_connection.py --auth-kind <kind>` runs these. It prints the account name, never the credential.
