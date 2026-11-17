"""Per-machine settings that never go in the manifest. See `examples/machine.yaml`.

Every key is optional:
- `vault`: `keyring` (the default), `aws` or `memory`.
- `keyring_service`: the service name the keyring entries sit under. Default `universal-connector`.
- `allow_keyring_backend`: the exact class path of one more keyring backend to trust. Without
  it only the macOS, Windows, Secret Service and KWallet stores pass.
- `aws_region` and `aws_profile`: for `vault: aws`. No region is assumed; the profile defaults to
  `default`.
- `google_client_entry`: the vault entry that holds your Google Desktop OAuth client JSON.
- `google_scopes`: the scopes `uconnector login google` asks for; a subset of the read and
  draft scopes below.
- `google_accounts`: `{label: address}`, the mailbox each sign-in label must be.
- `door_hosts`: extra exact `Host` values, for a tailnet route or a local https proxy.

Every bad value raises ValueError with a fixed text that never quotes the value.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

ENV_NAME = "UCONNECTOR_MACHINE_FILE"
DEFAULT_NAME = "machine.yaml"

VAULTS = ("keyring", "aws", "memory")
DEFAULT_VAULT = "keyring"
DEFAULT_KEYRING_SERVICE = "universal-connector"
DEFAULT_AWS_PROFILE = "default"
DEFAULT_GOOGLE_CLIENT_ENTRY = "connector/google/oauth-client"
GOOGLE_SCOPE_CHOICES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.readonly",
)

BAD_VAULT = "bad vault setting: use keyring, aws or memory"
BAD_KEYRING_SERVICE = "bad keyring_service setting"
NO_AWS_REGION = "vault aws needs aws_region in the machine file"
BAD_AWS_REGION = "bad aws_region setting"
BAD_AWS_PROFILE = "bad aws_profile setting"
BAD_CLIENT_ENTRY = "bad google_client_entry setting"
BAD_SCOPES = "bad google_scopes setting: use a non-empty list of the read and draft scopes"
BAD_ACCOUNTS = "bad google_accounts setting: use label: address"
BAD_DOOR_HOST = "bad door_hosts entry"
BAD_KEYRING_BACKEND = "bad allow_keyring_backend setting: use one exact module.Class path"
MISSING_MACHINE_FILE = (
    "the machine file named by --machine-file or UCONNECTOR_MACHINE_FILE does not exist"
)
MAX_DOOR_HOSTS = 4
_CLASS_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")


class MachineFileMissing(ValueError):
    """A machine file was named explicitly and is not there. Only the default may be missing."""

_SERVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_REGION = re.compile(r"[a-z]{2}(?:-[a-z]+)+-[0-9]{1,2}")
_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_ENTRY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-/]{0,127}")
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_PORT = r"(?::([1-9][0-9]{0,4}))?"
# Exact values only: `<label>.<tailnet>.ts.net` for a tailnet route, `<label>.localhost` for a
# local https proxy. Never a wildcard, scheme, path, user info, IP address or upper case.
_DOOR_HOSTS = (
    re.compile(rf"{_LABEL}\.{_LABEL}\.ts\.net{_PORT}"),
    re.compile(rf"{_LABEL}\.localhost{_PORT}"),
)


def _text(machine: dict, key: str, default: str, pattern: re.Pattern[str], problem: str) -> str:
    if key not in machine:
        return default
    value = machine[key]
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(problem)
    return value


def vault_kind(machine: dict) -> str:
    """`keyring`, `aws` or `memory`. A missing key gives the keyring."""
    value = machine.get("vault", DEFAULT_VAULT)
    if not isinstance(value, str) or value not in VAULTS:
        raise ValueError(BAD_VAULT)
    return value


def keyring_service(machine: dict) -> str:
    return _text(machine, "keyring_service", DEFAULT_KEYRING_SERVICE, _SERVICE, BAD_KEYRING_SERVICE)


def allowed_keyring_backend(machine: dict) -> str | None:
    """The one extra keyring backend class path to trust, or None."""
    if "allow_keyring_backend" not in machine:
        return None
    value = machine["allow_keyring_backend"]
    if not isinstance(value, str) or len(value) > 200 or not _CLASS_PATH.fullmatch(value):
        raise ValueError(BAD_KEYRING_BACKEND)
    return value


def aws_profile(machine: dict) -> str:
    """The AWS profile for vault reads and the sign-in writer. Default is `default`."""
    return _text(machine, "aws_profile", DEFAULT_AWS_PROFILE, _PROFILE, BAD_AWS_PROFILE)


def aws_region(machine: dict) -> str:
    """The AWS Region. There is no default: a vault in the wrong Region must not be guessed."""
    if "aws_region" not in machine:
        raise ValueError(NO_AWS_REGION)
    return _text(machine, "aws_region", "", _REGION, BAD_AWS_REGION)


def google_client_entry(machine: dict) -> str:
    value = _text(
        machine, "google_client_entry", DEFAULT_GOOGLE_CLIENT_ENTRY, _ENTRY, BAD_CLIENT_ENTRY
    )
    if ".." in value or value.endswith("/"):
        raise ValueError(BAD_CLIENT_ENTRY)
    return value


def google_scopes(machine: dict) -> tuple[str, ...]:
    """The scopes to ask Google for. Only read and draft scopes; never a send or full-mail scope."""
    if "google_scopes" not in machine:
        return GOOGLE_SCOPE_CHOICES
    value = machine["google_scopes"]
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(s, str) or s not in GOOGLE_SCOPE_CHOICES for s in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(BAD_SCOPES)
    return tuple(value)


def google_accounts(machine: dict) -> dict[str, str]:
    """`{label: address}`. None set gives `{}`."""
    accounts = machine.get("google_accounts", {})
    if accounts is None:
        return {}
    if not isinstance(accounts, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in accounts.items()
    ):
        raise ValueError(BAD_ACCOUNTS)
    return dict(accounts)


def door_hosts(machine: dict) -> list[str]:
    """Exact `Host` values the door also accepts. None set gives `[]`.

    Each is lower-case `<label>.<tailnet>.ts.net` or `<label>.localhost`, with an optional
    `:<port>` (1 to 65535). Any bad entry raises ValueError with a fixed text.
    """
    if "door_hosts" not in machine:
        return []
    entries = machine["door_hosts"]
    if not isinstance(entries, list) or len(entries) > MAX_DOOR_HOSTS:
        raise ValueError(BAD_DOOR_HOST)
    for entry in entries:
        if not isinstance(entry, str):
            raise ValueError(BAD_DOOR_HOST)  # noqa: TRY004 - one fixed refusal for every bad entry
        match = next((m for p in _DOOR_HOSTS if (m := p.fullmatch(entry))), None)
        if match is None or (match.group(1) and int(match.group(1)) > 65535):
            raise ValueError(BAD_DOOR_HOST)
    return list(entries)


def problems(machine: dict) -> list[str]:
    """Every fixed problem in the machine file, so a command can stop before it starts work."""
    found: list[str] = []
    checks = [
        vault_kind, keyring_service, allowed_keyring_backend, aws_profile, google_client_entry,
        google_scopes, google_accounts, door_hosts,
    ]  # fmt: skip
    for check in checks:
        try:
            check(machine)
        except ValueError as err:
            found.append(str(err))
    if machine.get("vault") == "aws":
        try:
            aws_region(machine)
        except ValueError as err:
            found.append(str(err))
    return found


def machine_path(path: Path | None = None) -> Path:
    """`path`, else the file named by `UCONNECTOR_MACHINE_FILE`, else `machine.yaml` here."""
    if path is not None:
        return Path(path)
    env = os.environ.get(ENV_NAME)
    return Path(env) if env else Path(DEFAULT_NAME)


def load_machine(path: Path | None = None) -> dict:
    """Load the machine file. A non-mapping top level raises ValueError.

    Only the default `./machine.yaml` may be missing, which gives `{}`. A file named by `path`
    or by `UCONNECTOR_MACHINE_FILE` that is not there raises `MachineFileMissing`: a typo must
    never start the door silently on default settings.
    """
    explicit = path is not None or bool(os.environ.get(ENV_NAME))
    path = machine_path(path)
    if not path.is_file():
        if explicit:
            raise MachineFileMissing(MISSING_MACHINE_FILE)
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("machine file top level must be a mapping")  # noqa: TRY004 - ruled type
    return data
