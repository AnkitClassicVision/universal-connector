# The door (universal connector)

One front door on your own computer. It holds your connections and gives each agent system one
revocable key. Real keys stay in your vault. The door listens on loopback only (`127.0.0.1` or
`::1`).

Three stores:

- Manifest (your files): the shape. Connection names, tool tiers and vault entry names. Never a
  secret value. Examples: `examples/manifest/`.
- Vault: the values. Your system keyring by default. AWS Secrets Manager is optional.
- Local state: a per-user folder, owner-only. Key hashes, the audit log, the pause flag and the
  reload counter. Only the SHA-256 of each agent key is stored.

Works on: Linux, tested. macOS and Windows: their code paths are tested by simulation in the test
suite, not on real machines yet.

## Install

Python 3.11 or newer, through [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/AnkitClassicVision/universal-connector@v0.1.0#subdirectory=door
```

With AWS Secrets Manager as the vault:

```sh
uv tool install "universal-connector[aws] @ git+https://github.com/AnkitClassicVision/universal-connector@v0.1.0#subdirectory=door"
```

The door lives in the `door/` folder of that repository. The command is `uconnector`.

## Set up

1. Copy `examples/manifest/` to a folder of your own, and `examples/machine.yaml` beside it.
   Edit the connections. Every address and entry name in the examples is fake.
2. Choose the vault in the machine file: `vault: keyring` (default), `aws` or `memory`.
   - keyring: the door trusts only these system stores: macOS Keychain, Windows Credential
     Manager, and on Linux the Secret Service (through `SecretService` or `libsecret`, for
     example GNOME Keyring) or KWallet. Any other backend the `keyring` library picks is
     refused, unless the machine file names its exact class path in `allow_keyring_backend`
     (for example `keyrings.cryptfile.cryptfile.CryptFileKeyring`). The fail and null backends
     and the plain-text `keyrings.alt` ones are refused even when named. Entries sit under the
     service name `keyring_service` (default `universal-connector`); the user name is the entry
     name from the manifest. Add one with the keyring tool:
     `uvx keyring set universal-connector <entry name>`.
   - aws: needs the `aws` extra, `aws_region` (never assumed) and `aws_profile`. An optional,
     narrow IAM policy example is in `examples/aws/door-read-policy.json`.
   - memory: an empty store, for a dry run. Every entry reads as missing.
3. Check the manifest: `uconnector check --manifest <your manifest folder>`.
4. Run the door in the foreground: `uconnector serve --manifest <folder> --machine-file <file>`.
5. Connect an agent system, yourself, in your own terminal:
   `uconnector connect <name> --manifest <folder> --reach starter --scopes work --key-file <private path>`.
   It writes the new key to a new owner-only file at that path and prints the config entry
   without it. This is the default way. Without `--key-file`, `connect` prints the key on screen
   once: use that only in your own terminal, and never through an agent, because the key would
   land in the agent's context and logs.
6. Check the connections: `uconnector doctor --manifest <folder> --machine-file <file>`.

`--state` is optional everywhere. The default is a per-user folder:
`~/Library/Application Support/universal-connector/state` on macOS and
`$XDG_STATE_HOME/universal-connector/state` (else `~/.local/state/...`) on Linux, kept at
modes 0700 and 0600. On Windows the default is `%LOCALAPPDATA%\universal-connector\state`,
which Windows keeps private to your user account. Windows has no 0600 mode, so a custom
`--state` there must be a folder only your account can read.

`--machine-file` (or `UCONNECTOR_MACHINE_FILE`) must name a file that exists; a missing one
stops the command with a fixed message. Only the default, `machine.yaml` in the current folder,
may be missing, which means default settings.

## Google

Make your own Google Cloud project and a Desktop OAuth client. Store its JSON (the one with an
`installed` key) in the vault under `google_client_entry` (default
`connector/google/oauth-client`). `google_scopes` picks from Gmail read, Gmail draft and Calendar
read; Gmail connections need both Gmail scopes. While the project's consent screen is in
Testing, Google ends a refresh token after 7 days, so sign in again then. Then:

```sh
uconnector login google --account work --manifest <folder> --machine-file <file>
```

The sign-in record goes to the same vault the door reads, under `connector/oauth/google-<label>`.
The signed-in mailbox must match `google_accounts.<label>` in the machine file.

## Oddboro

`uconnector connect <name> --manifest <folder> --format oddboro --url https://<host>/mcp --key-file <private path>`,
run by you in your own terminal, as in step 5 above. Paste the key from that file into Oddboro's
own key field yourself.

- The agent sees the 5 fixed tools only. `--pinned` shows pinned tools too.
- Each call gets 40 seconds in total, retry included (`call_timeout_s: 40`), inside Oddboro's
  safe wait of under 45 seconds. The first try gets the tool's own timeout, capped at the
  budget. A read tool retries once after a timeout or transport error, with only the time
  that is left, and not at all when none is left. `initialize` and `tools/list` never call an
  upstream, so they answer at once.
- Oddboro names a granted tool `mcp__<service id>__<tool>` and refuses a run when one is longer
  than 64 characters. The service id is the address host plus path (no port, no query), lower
  case, every run of other characters made one `-`, one `-` trimmed from each end. `connect`
  refuses with the computed length when a visible tool would be too long, and warns past 57
  characters, before anything changes. It also refuses a pinned tool name that is not
  snake_case, and an address whose host or path Oddboro's URL parser would rewrite.
  `set-tools --pinned` cannot check the address; run `uconnector smoke oddboro` after it.
- Read tools carry `readOnlyHint: true` and `destructiveHint: false`, and no name with one of
  Oddboro's 42 change words is marked read-only. No tool has an `outputSchema`; the tool list
  is one page.
- The Authorization header may hold `Bearer <key>` or the bare `<key>`. Either way the key
  passes the same hash check, and neither is ever logged.
- Oddboro needs an `https://` address. Use a tailnet route, or a local https proxy on a
  `<name>.localhost` host. Put the exact Host value in `door_hosts` in the machine file. The door
  still binds `127.0.0.1` and checks the key on every request.

### Smoke check

`uconnector smoke oddboro --url https://<host>/mcp --key-file <path>` talks to the running door
the way Oddboro's client does (protocol 2025-11-25, no `Origin` header, `Accept` JSON and event
stream, no redirects) and prints pass or fail for: initialize, 401 without the key, GET gives 405
or a stream, a one-page tool list, the tool shape and name budget for the computed service id,
and one call per read tool that returns a content array within 40 seconds. It never prints the
key or any tool result. Exit 0 when every check passes, 1 otherwise, 2 for bad input.

## Reload

`uconnector reload` asks the running door to read the manifest again. It works on every system:
it adds one to a counter in the state folder's own database, the door checks the counter every
3 seconds, reloads, and writes the outcome back. The door reads the counter before it reads the
files, so a reload asked while it is still starting is applied as soon as it is up. The command
waits up to 15 seconds (`--wait`) and exits 0 reloaded, 1 the new manifest did not load (the
last good one keeps serving), 2 no state folder, or 3 no door answered in time. SIGHUP still
works on Linux and macOS. A changed machine file needs a restart.

## Run at login

`uconnector install-service --print --machine-file <abs> --manifest <abs> [--state <abs>]`
prints the service file for this system, filled in: a systemd user unit on Linux, a launchd agent
on macOS, or a Task Scheduler logon task on Windows. Templates are in `deploy/`. It installs
nothing; the steps to turn it on are printed to standard error for you to run. Foreground
`uconnector serve` is the fallback everywhere.

## Commands

`serve`, `connect`, `revoke`, `rotate`, `list`, `set-tools`, `doctor`, `check`, `login`,
`pause`, `resume`, `reload`, `install-service`, `smoke`. `connect --format` takes `generic`
(an `mcpServers` JSON entry) or `oddboro` (three lines for its Services tab).

## Safety rules the code keeps

- Only the SHA-256 of an agent key is stored. A key is `pc_` plus `secrets.token_urlsafe(32)`
  and is shown once.
- Upstream keys live in memory for at most 900 seconds.
- Tools are an allow-list with tiers: green reads, yellow drafts (needs the `drafts` add-on),
  red and black never run. A connection is visible only to an agent holding all its scopes.
  The `restricted` scope cannot be granted in this version, so a connection marked with it is
  closed to every agent.
- An agent sees at most 25 tools: 5 fixed plus at most 20 pinned.
- Loopback bind only (`127.0.0.1` or `::1`), a bearer check on every request, any non-empty
  `Origin` header refused with 403, and an exact `Host` allow-list.

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.

## Development

```sh
uv sync --extra dev
uv run pytest -q -m "not live"
uv run ruff check
uv run uconnector check --manifest examples/manifest
```

Tests are offline and never touch a real keyring: `tests/conftest.py` replaces the `keyring`
library with a fake that fails on use.
