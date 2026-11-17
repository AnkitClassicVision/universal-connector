"""Vault access. Values stay in memory inside this process and never reach text output.

Three backends, chosen by `vault:` in the machine file (`store_for`):
- `keyring` (default): the system keyring through the `keyring` library. macOS Keychain,
  Windows Credential Manager, Linux Secret Service or KWallet. Any other backend is refused
  unless the machine file names its exact class path in `allow_keyring_backend`.
- `aws`: AWS Secrets Manager, read-only. Needs the `aws` extra, `aws_region` and a profile.
- `memory`: an empty in-memory store. Every entry is missing; for a dry run and tests.
"""

from __future__ import annotations

import importlib.util
import json
import time
from collections.abc import Callable
from typing import Any, Protocol

DEFAULT_TTL_S = 900
NO_AWS_EXTRA = "vault aws needs the aws extra: install universal-connector[aws]"
UNSAFE_KEYRING = (
    "the keyring backend is not a known system store; refused "
    "(name it exactly in allow_keyring_backend to use it)"
)
# The system stores the door trusts, by exact class path: macOS Keychain, Windows Credential
# Manager, and on Linux the Secret Service (two clients) or KWallet. Anything else is refused
# unless the machine file names its exact class path in `allow_keyring_backend`.
KNOWN_KEYRING_BACKENDS = frozenset(
    {
        "keyring.backends.macOS.Keyring",
        "keyring.backends.Windows.WinVaultKeyring",
        "keyring.backends.SecretService.Keyring",
        "keyring.backends.libsecret.Keyring",
        "keyring.backends.kwallet.DBusKeyring",
        "keyring.backends.kwallet.DBusKeyringKWallet4",
    }
)
CHAINER = "keyring.backends.chainer.ChainerBackend"
# Never allowed, even when named: a failing or null store, or the plain-text files of keyrings.alt.
_REFUSED_BACKENDS = ("keyring.backends.fail", "keyring.backends.null", "keyrings.alt")


class SecretUnavailable(Exception):
    """A vault entry could not be read. The text holds the entry name, never a value."""


class SecretStore(Protocol):
    def get(self, name: str) -> str: ...

    def exists(self, name: str) -> bool: ...

    def field(self, name: str, key: str) -> str: ...

    def field_names(self, name: str) -> list[str]: ...


def _json_object(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


class _FieldsMixin:
    def get(self, name: str) -> str:  # pragma: no cover - provided by subclasses
        raise NotImplementedError

    def field(self, name: str, key: str) -> str:
        parsed = _json_object(self.get(name))
        if parsed is None or key not in parsed or not isinstance(parsed[key], str):
            raise SecretUnavailable(f"vault entry field not available: {name} [{key}]")
        return parsed[key]

    def field_names(self, name: str) -> list[str]:
        parsed = _json_object(self.get(name))
        return sorted(parsed) if parsed is not None else []


class MemorySecretStore(_FieldsMixin):
    """In-memory store for tests."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = dict(values)

    def __repr__(self) -> str:
        return f"MemorySecretStore(entries={len(self._values)})"

    __str__ = __repr__

    def get(self, name: str) -> str:
        if name not in self._values:
            raise SecretUnavailable(f"vault entry not available: {name}")
        return self._values[name]

    def exists(self, name: str) -> bool:
        return name in self._values


def _error_code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code")
    return None


class AwsSecretStore(_FieldsMixin):
    """AWS Secrets Manager, read-only. Values are cached in memory for at most `ttl_s` seconds."""

    def __init__(
        self,
        profile: str = "default",
        region: str | None = None,
        ttl_s: int = DEFAULT_TTL_S,
        client: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.profile = profile
        self.region = region
        self.ttl_s = ttl_s
        self._client_obj = client
        self._clock = clock
        self._cache: dict[str, tuple[float, str]] = {}

    def __repr__(self) -> str:
        return (
            f"AwsSecretStore(profile={self.profile!r}, region={self.region!r}, "
            f"cached={len(self._cache)})"
        )

    __str__ = __repr__

    def _client(self) -> Any:
        if self._client_obj is None:
            if not self.region:  # no Region is ever guessed; the callers turn this into refusals
                raise RuntimeError("no aws region")
            import boto3

            session = boto3.session.Session(profile_name=self.profile, region_name=self.region)
            self._client_obj = session.client("secretsmanager")
        return self._client_obj

    def purge(self) -> int:
        """Remove expired cache entries. Return how many were removed."""
        now = self._clock()
        expired = [n for n, (stamp, _) in self._cache.items() if now - stamp >= self.ttl_s]
        for name in expired:
            del self._cache[name]
        return len(expired)

    def cached_names(self) -> list[str]:
        """Names of cached entries. Never values."""
        return sorted(self._cache)

    def field(self, name: str, key: str) -> str:
        self.purge()
        return super().field(name, key)

    def field_names(self, name: str) -> list[str]:
        self.purge()
        return super().field_names(name)

    def get(self, name: str) -> str:
        self.purge()
        cached = self._cache.get(name)
        if cached is not None:
            return cached[1]
        now = self._clock()
        failed = False
        response: dict[str, Any] = {}
        try:
            response = self._client().get_secret_value(SecretId=name)
        except Exception:  # noqa: BLE001 - fail closed on any client error
            failed = True
        if failed:  # raised outside the handler so no context is chained
            raise SecretUnavailable(f"vault entry not available: {name}")
        value = response.get("SecretString")
        if not isinstance(value, str):
            raise SecretUnavailable(f"vault entry has no text value: {name}")
        self._cache[name] = (now, value)
        return value

    def exists(self, name: str) -> bool:
        """True when the entry exists. Uses `describe_secret` only, so no value is read."""
        self.purge()
        failed = False
        missing = False
        response: dict[str, Any] = {}
        try:
            response = self._client().describe_secret(SecretId=name)
        except Exception as exc:  # noqa: BLE001 - fail closed on any client error
            failed = True
            missing = _error_code(exc) == "ResourceNotFoundException"
        if missing:
            return False
        if failed:  # raised outside the handler so no context is chained
            raise SecretUnavailable(f"vault not reachable for entry: {name}")
        return "DeletedDate" not in response

    def list_names(self) -> list[str]:
        """Entry names only, through `list_secrets`. No value is read."""
        names: list[str] = []
        kwargs: dict[str, Any] = {"MaxResults": 100}
        while True:
            failed = False
            response: dict[str, Any] = {}
            try:
                response = self._client().list_secrets(**kwargs)
            except Exception:  # noqa: BLE001 - fail closed on any client error
                failed = True
            if failed:  # raised outside the handler so no context is chained
                raise SecretUnavailable("vault entry names not available")
            names.extend(str(item["Name"]) for item in response.get("SecretList", []))
            token = response.get("NextToken")
            if not token:
                return sorted(names)
            kwargs["NextToken"] = token


def backend_path(backend: Any) -> str:
    """`module.Class` of a keyring backend object."""
    kind = type(backend)
    return f"{kind.__module__}.{kind.__qualname__}"


def keyring_backend_ok(backend: Any, allowed: str | None = None) -> bool:
    """True only for a known system store, or the one class path `allowed` names exactly.

    The deny-list (fail, null, `keyrings.alt`) wins over everything. The library's chainer passes
    only when it is the real chainer class and every backend in its list or tuple passes.
    """
    path = backend_path(backend)
    module = type(backend).__module__
    if any(module == bad or module.startswith(bad + ".") for bad in _REFUSED_BACKENDS):
        return False
    if path == CHAINER:
        chain = getattr(backend, "backends", None)
        return (
            isinstance(chain, (list, tuple))
            and bool(chain)
            and all(keyring_backend_ok(part, allowed) for part in chain)
        )
    return path in KNOWN_KEYRING_BACKENDS or (allowed is not None and path == allowed)


def system_keyring(allowed: str | None = None) -> Any:
    """The `keyring` library's chosen backend. Raises SecretUnavailable unless it passes."""
    import keyring

    backend = keyring.get_keyring()
    if not keyring_backend_ok(backend, allowed):
        raise SecretUnavailable(UNSAFE_KEYRING)
    return backend


class KeyringSecretStore(_FieldsMixin):
    """The system keyring, read-only here. Each entry is a password under (`service`, entry name).

    Values are cached in memory for at most `ttl_s` seconds. `exists` has to read the value,
    since a keyring has no name-only lookup; it drops the value at once and never caches it.
    """

    def __init__(
        self,
        service: str,
        ttl_s: int = DEFAULT_TTL_S,
        backend: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
        allowed_backend: str | None = None,
    ) -> None:
        self.service = service
        self.ttl_s = ttl_s
        self.allowed_backend = allowed_backend
        self._backend_obj = backend
        self._clock = clock
        self._cache: dict[str, tuple[float, str]] = {}

    def __repr__(self) -> str:
        return f"KeyringSecretStore(service={self.service!r}, cached={len(self._cache)})"

    __str__ = __repr__

    def _backend(self) -> Any:
        if self._backend_obj is None:
            self._backend_obj = system_keyring(self.allowed_backend)
        return self._backend_obj

    def _read(self, name: str) -> str | None:
        """The value, or None when the entry is missing. Any fault: SecretUnavailable."""
        failed = False
        unsafe = False
        value: Any = None
        try:
            value = self._backend().get_password(self.service, name)
        except SecretUnavailable:
            unsafe = True
        except Exception:  # noqa: BLE001 - fail closed on any keyring error
            failed = True
        if unsafe:  # raised outside the handler so no context is chained
            raise SecretUnavailable(UNSAFE_KEYRING)
        if failed:
            raise SecretUnavailable(f"keyring not available for entry: {name}")
        if value is not None and not isinstance(value, str):
            raise SecretUnavailable(f"vault entry has no text value: {name}")
        return value

    def purge(self) -> int:
        """Remove expired cache entries. Return how many were removed."""
        now = self._clock()
        expired = [n for n, (stamp, _) in self._cache.items() if now - stamp >= self.ttl_s]
        for name in expired:
            del self._cache[name]
        return len(expired)

    def cached_names(self) -> list[str]:
        """Names of cached entries. Never values."""
        return sorted(self._cache)

    def field(self, name: str, key: str) -> str:
        self.purge()
        return super().field(name, key)

    def field_names(self, name: str) -> list[str]:
        self.purge()
        return super().field_names(name)

    def get(self, name: str) -> str:
        self.purge()
        cached = self._cache.get(name)
        if cached is not None:
            return cached[1]
        now = self._clock()
        value = self._read(name)
        if not value:
            raise SecretUnavailable(f"vault entry not available: {name}")
        self._cache[name] = (now, value)
        return value

    def exists(self, name: str) -> bool:
        self.purge()
        if name in self._cache:
            return True
        return bool(self._read(name))


def store_for(machine: dict) -> SecretStore:
    """The read store the machine file names. Raise ValueError with a fixed text on a bad setting."""
    from universal_connector import machine as settings

    kind = settings.vault_kind(machine)
    if kind == "memory":
        return MemorySecretStore({})
    if kind == "aws":
        region, profile = settings.aws_region(machine), settings.aws_profile(machine)
        if importlib.util.find_spec("boto3") is None:
            raise ValueError(NO_AWS_EXTRA)
        return AwsSecretStore(profile=profile, region=region)
    return KeyringSecretStore(
        service=settings.keyring_service(machine),
        allowed_backend=settings.allowed_keyring_backend(machine),
    )
