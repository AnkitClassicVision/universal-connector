"""The only code that writes to the vault. It writes one place: entries under `connector/oauth/`.

`vault.py` stays read-only. The writer goes to the backend the machine file names
(`writer_for`), the same one the door reads:
- keyring: `set_password` under the keyring service.
- aws: `CreateSecret`, then `PutSecretValue` when the entry already exists. It never deletes,
  lists, tags or changes a policy.
- memory: refused, since nothing would be kept.
Errors carry fixed text only.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

PREFIX = "connector/oauth/"
_NAME = re.compile(r"connector/oauth/[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
MEMORY_KEEPS_NOTHING = "the memory vault keeps nothing; set vault: keyring or aws in the machine file"

Writer = Callable[[str, str], None]


class SaveRefused(Exception):
    """The save did not happen. The text is fixed and holds no value."""


def _check(name: str, value: str) -> None:
    if not isinstance(name, str) or not _NAME.fullmatch(name) or ".." in name:
        raise SaveRefused(f"refused: vault writes are limited to {PREFIX}")
    if not isinstance(value, str) or not value:
        raise SaveRefused("refused: nothing to save")


def _client(profile: str, region: str) -> Any:
    import boto3

    session = boto3.session.Session(profile_name=profile, region_name=region)
    return session.client("secretsmanager")


def _code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code")
    return None


def save_login_aws(profile: str, region: str, name: str, value: str) -> None:
    """Save `value` under `name` in AWS Secrets Manager. Refuses any name outside the prefix."""
    _check(name, value)
    failed = False
    client: Any = None
    try:
        client = _client(profile, region)
    except Exception:  # noqa: BLE001 - mapped; the original text is never kept
        failed = True
    if failed:
        raise SaveRefused("the vault could not be reached")
    exists = False
    try:
        client.create_secret(Name=name, SecretString=value)
    except Exception as exc:  # noqa: BLE001 - mapped; the original text is never kept
        if _code(exc) == "ResourceExistsException":
            exists = True
        else:
            failed = True
    if failed:  # raised outside the handler so no context is chained
        raise SaveRefused("the vault refused the new entry")
    if not exists:
        return
    try:
        client.put_secret_value(SecretId=name, SecretString=value)
    except Exception:  # noqa: BLE001 - mapped; the original text is never kept
        failed = True
    if failed:
        raise SaveRefused("the vault refused the new value")


def save_login_keyring(
    service: str,
    name: str,
    value: str,
    backend: Any | None = None,
    allowed_backend: str | None = None,
) -> None:
    """Save `value` under (`service`, `name`) in the system keyring.

    The backend passes the same rule as the reader: a known system store, or the one class path
    the machine file names in `allow_keyring_backend`.
    """
    _check(name, value)
    from universal_connector.vault import SecretUnavailable, system_keyring

    unsafe = False
    failed = False
    try:
        target = backend if backend is not None else system_keyring(allowed_backend)
        target.set_password(service, name, value)
    except SecretUnavailable:
        unsafe = True
    except Exception:  # noqa: BLE001 - mapped; the original text is never kept
        failed = True
    if unsafe:  # raised outside the handler so no context is chained
        raise SaveRefused("refused: the keyring backend is not a known system store")
    if failed:
        raise SaveRefused("the keyring refused the new entry")


def writer_for(machine: dict) -> Writer:
    """The writer for the machine file's vault. Raise ValueError with a fixed text when there is
    none: a bad setting, or the memory vault."""
    from universal_connector import machine as settings
    from universal_connector.vault import NO_AWS_EXTRA

    kind = settings.vault_kind(machine)
    if kind == "memory":
        raise ValueError(MEMORY_KEEPS_NOTHING)
    if kind == "aws":
        profile, region = settings.aws_profile(machine), settings.aws_region(machine)
        import importlib.util

        if importlib.util.find_spec("boto3") is None:
            raise ValueError(NO_AWS_EXTRA)
        return lambda name, value: save_login_aws(profile, region, name, value)
    service, allowed = settings.keyring_service(machine), settings.allowed_keyring_backend(machine)
    return lambda name, value: save_login_keyring(service, name, value, allowed_backend=allowed)
