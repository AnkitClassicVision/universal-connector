"""The vault backends: keyring (default), AWS (optional), memory. Fake backends only.

No test reaches a real keyring (see conftest.py) or AWS: each passes a fake object in.
"""

from __future__ import annotations

import importlib.util
import json
import re
import types

import pytest

from universal_connector import vault, vault_write
from universal_connector.vault import (
    AwsSecretStore,
    KeyringSecretStore,
    MemorySecretStore,
    SecretUnavailable,
    keyring_backend_ok,
    store_for,
)

VALUE = "fake-value-Q7x-long-enough"


class FakeKeyring:
    """Has only the two keyring calls the door may use."""

    def __init__(self, values: dict[tuple[str, str], str] | None = None, fail: bool = False):
        self.values = dict(values or {})
        self.fail = fail
        self.reads: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str]] = []

    def get_password(self, service: str, name: str) -> str | None:
        self.reads.append((service, name))
        if self.fail:
            raise RuntimeError(f"keyring broke near {VALUE}")
        return self.values.get((service, name))

    def set_password(self, service: str, name: str, value: str) -> None:
        if self.fail:
            raise RuntimeError(f"keyring broke near {value}")
        self.writes.append((service, name))
        self.values[(service, name)] = value


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def keyring_store(values=None, **kw):
    backend = FakeKeyring(values, **{k: v for k, v in kw.items() if k == "fail"})
    clock = Clock()
    store = KeyringSecretStore("door-test", backend=backend, clock=clock)
    return store, backend, clock


# -- keyring reads -------------------------------------------------------------------------------


def test_keyring_reads_under_the_service_and_caches_for_900_seconds():
    store, backend, clock = keyring_store({("door-test", "a/b"): VALUE})
    assert store.ttl_s == 900
    assert store.get("a/b") == VALUE
    assert store.get("a/b") == VALUE
    assert backend.reads == [("door-test", "a/b")]  # the second read came from memory
    clock.now = 899.9
    store.get("a/b")
    assert len(backend.reads) == 1
    clock.now = 900.0
    assert store.purge() == 1 and store.cached_names() == []
    store.get("a/b")
    assert len(backend.reads) == 2


def test_keyring_missing_entry_is_unavailable_with_the_name_only():
    store, _, _ = keyring_store()
    with pytest.raises(SecretUnavailable) as err:
        store.get("a/missing")
    assert str(err.value) == "vault entry not available: a/missing"
    assert store.exists("a/missing") is False


def test_keyring_exists_reads_but_never_caches():
    store, backend, _ = keyring_store({("door-test", "a/b"): VALUE})
    assert store.exists("a/b") is True
    assert store.cached_names() == []
    assert backend.reads == [("door-test", "a/b")]


def test_keyring_error_fails_closed_with_fixed_text_and_no_chain():
    store, _, _ = keyring_store(fail=True)
    for call in (lambda: store.get("a/b"), lambda: store.exists("a/b")):
        with pytest.raises(SecretUnavailable) as err:
            call()
        assert str(err.value) == "keyring not available for entry: a/b"
        assert err.value.__cause__ is None and err.value.__context__ is None
        assert VALUE not in str(err.value)


def test_keyring_fields_and_repr_hold_no_value():
    record = json.dumps({"client_id": "cid", "refresh_token": VALUE})
    store, _, _ = keyring_store({("door-test", "g/rec"): record})
    assert store.field("g/rec", "client_id") == "cid"
    assert store.field_names("g/rec") == ["client_id", "refresh_token"]
    assert VALUE not in repr(store) and VALUE not in str(store)
    assert repr(store) == "KeyringSecretStore(service='door-test', cached=1)"


def _backend_of(module: str, name: str = "Keyring"):
    cls = type(name, (), {})
    cls.__module__ = module
    return cls()


@pytest.mark.parametrize(
    "module",
    ["keyring.backends.fail", "keyring.backends.null", "keyrings.alt.file", "keyrings.alt"],
)
def test_unsafe_keyring_backends_are_refused(module, monkeypatch):
    import sys

    assert keyring_backend_ok(_backend_of(module)) is False
    store = KeyringSecretStore("door-test", backend=None)
    fake_module = types.SimpleNamespace(get_keyring=lambda: _backend_of(module))
    monkeypatch.setitem(sys.modules, "keyring", fake_module)
    with pytest.raises(SecretUnavailable) as err:
        store.get("a/b")
    assert str(err.value) == vault.UNSAFE_KEYRING


KNOWN = [
    ("keyring.backends.macOS", "Keyring"),
    ("keyring.backends.Windows", "WinVaultKeyring"),
    ("keyring.backends.SecretService", "Keyring"),
    ("keyring.backends.libsecret", "Keyring"),
    ("keyring.backends.kwallet", "DBusKeyring"),
    ("keyring.backends.kwallet", "DBusKeyringKWallet4"),
]
UNKNOWN = [
    ("keyrings.cryptfile.file", "PlaintextKeyring"),
    ("keyrings.envvars", "EnvvarsKeyring"),
    ("my_home_backend", "PlainFile"),
    ("keyring.backends.Windows", "Persistence"),  # a known module, not a known class
    ("keyring.backends.macOS", "Other"),
]


def _chain(parts):
    """The library's chainer class path, holding `parts` (or no `backends` at all for None)."""
    backend = _backend_of("keyring.backends.chainer", "ChainerBackend")
    if parts is not None:
        backend.backends = parts
    return backend


@pytest.mark.parametrize(("module", "name"), KNOWN)
def test_the_known_os_backends_are_allowed(module, name):
    assert keyring_backend_ok(_backend_of(module, name))


@pytest.mark.parametrize(("module", "name"), UNKNOWN)
def test_any_other_backend_is_refused_unless_named_exactly(module, name):
    backend = _backend_of(module, name)
    assert not keyring_backend_ok(backend)
    assert keyring_backend_ok(backend, allowed=f"{module}.{name}")
    assert not keyring_backend_ok(backend, allowed=f"{module}.{name}x")
    assert not keyring_backend_ok(backend, allowed=module)  # a module alone is not enough


def test_the_deny_list_wins_over_an_explicit_allow():
    for module, name in [("keyrings.alt.file", "PlaintextKeyring"), ("keyring.backends.null", "Keyring"),
                         ("keyring.backends.fail", "Keyring")]:  # fmt: skip
        assert not keyring_backend_ok(_backend_of(module, name), allowed=f"{module}.{name}")


def test_chains_pass_only_as_the_real_chainer_of_allowed_backends():
    safe = [_backend_of(m, n) for m, n in KNOWN[:3]]
    assert keyring_backend_ok(_chain(safe))
    assert keyring_backend_ok(_chain(tuple(safe)))
    assert not keyring_backend_ok(_chain([*safe, _backend_of("keyrings.alt.file", "PlaintextKeyring")]))
    assert not keyring_backend_ok(_chain([*safe, _backend_of("my_home_backend", "PlainFile")]))
    assert not keyring_backend_ok(_chain([]))
    assert not keyring_backend_ok(_chain({"x": safe[0]}))  # not a list
    assert not keyring_backend_ok(_chain(None))  # no chain at all
    assert not keyring_backend_ok(types.SimpleNamespace(backends=safe))  # not the chainer class
    custom = _backend_of("my_home_backend", "PlainFile")
    assert keyring_backend_ok(_chain([safe[0], custom]), allowed="my_home_backend.PlainFile")


class Reads:
    def get_password(self, service, name):
        return "v"

    def set_password(self, service, name, value):
        return None


@pytest.mark.parametrize(
    ("module", "name", "reads"),
    [*((m, n, True) for m, n in KNOWN), *((m, n, False) for m, n in UNKNOWN),
     ("keyring.backends.fail", "Keyring", False), ("keyrings.alt.file", "PlaintextKeyring", False)],
)  # fmt: skip
def test_store_and_writer_follow_the_same_rule(module, name, reads, monkeypatch):
    import sys

    cls = type(name, (Reads,), {})
    cls.__module__ = module
    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(get_keyring=cls))
    store = KeyringSecretStore("door-test")
    if reads:
        assert store.get("a/b") == "v"
        vault_write.save_login_keyring("door-test", ENTRY, VALUE)
    else:
        with pytest.raises(SecretUnavailable, match=f"^{re.escape(vault.UNSAFE_KEYRING)}$"):
            store.get("a/b")
        with pytest.raises(vault_write.SaveRefused):
            vault_write.save_login_keyring("door-test", ENTRY, VALUE)


def test_the_machine_file_names_one_extra_backend(monkeypatch):
    import sys

    from universal_connector import machine as settings

    path = "keyrings.cryptfile.cryptfile.CryptFileKeyring"
    cls = type("CryptFileKeyring", (Reads,), {})
    cls.__module__ = "keyrings.cryptfile.cryptfile"
    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(get_keyring=cls))
    with pytest.raises(SecretUnavailable):
        store_for({}).get("a/b")
    machine = {"allow_keyring_backend": path}
    assert settings.allowed_keyring_backend(machine) == path
    assert store_for(machine).get("a/b") == "v"
    vault_write.writer_for(machine)(ENTRY, VALUE)  # the writer follows the same setting
    for bad in ("", "Crypt", "has space.X", "a..b", "a.b.", 5, ["a.b"]):
        with pytest.raises(ValueError, match="^bad allow_keyring_backend setting"):
            settings.allowed_keyring_backend({"allow_keyring_backend": bad})


def test_no_test_reaches_the_real_keyring(no_real_keyring):
    store = KeyringSecretStore("door-test")  # no backend: it would ask the library
    with pytest.raises(SecretUnavailable):
        store.get("a/b")
    assert no_real_keyring.touched == ["get_keyring"]
    no_real_keyring.touched.clear()  # this test reached for it on purpose


# -- the choice in the machine file ---------------------------------------------------------------


def test_store_for_each_vault_kind(monkeypatch):
    assert isinstance(store_for({}), KeyringSecretStore)  # the default; nothing read yet
    keyring_one = store_for({"vault": "keyring", "keyring_service": "my-door"})
    assert isinstance(keyring_one, KeyringSecretStore) and keyring_one.service == "my-door"
    memory = store_for({"vault": "memory"})
    assert isinstance(memory, MemorySecretStore) and not memory.exists("anything")
    real = importlib.util.find_spec
    monkeypatch.setattr(vault.importlib.util, "find_spec",
                        lambda name, *a: object() if name == "boto3" else real(name))  # fmt: skip
    aws = store_for({"vault": "aws", "aws_region": "eu-west-1", "aws_profile": "door-reader"})
    assert isinstance(aws, AwsSecretStore)
    assert (aws.region, aws.profile) == ("eu-west-1", "door-reader")
    with pytest.raises(ValueError, match="^vault aws needs aws_region in the machine file$"):
        store_for({"vault": "aws"})


def test_aws_store_without_a_region_never_guesses_one():
    store = AwsSecretStore(profile="no-such-profile-for-tests")
    assert store.region is None
    with pytest.raises(SecretUnavailable, match="^vault entry not available: a/b$"):
        store.get("a/b")  # fails closed before any client is made


# -- the writer `login` uses -----------------------------------------------------------------


ENTRY = "connector/oauth/google-work"


def test_writer_for_keyring_writes_under_the_same_service(monkeypatch):
    backend = FakeKeyring()
    allowed_seen: list = []
    monkeypatch.setattr(vault, "system_keyring", lambda allowed=None: allowed_seen.append(allowed) or backend)
    writer = vault_write.writer_for({"keyring_service": "my-door"})
    writer(ENTRY, VALUE)
    assert backend.writes == [("my-door", ENTRY)]
    assert allowed_seen == [None]  # no extra backend named in this machine file
    reader = store_for({"keyring_service": "my-door"})
    monkeypatch.setattr(reader, "_backend_obj", backend)
    assert reader.get(ENTRY) == VALUE  # the door reads what login saved


def test_keyring_writer_rules():
    backend = FakeKeyring()
    vault_write.save_login_keyring("door-test", ENTRY, VALUE, backend=backend)
    assert backend.writes == [("door-test", ENTRY)]
    for name in ("connector/other/x", "connector/oauth/../x", "connector/oauth/", ""):
        with pytest.raises(vault_write.SaveRefused):
            vault_write.save_login_keyring("door-test", name, VALUE, backend=backend)
    with pytest.raises(vault_write.SaveRefused, match="^refused: nothing to save$"):
        vault_write.save_login_keyring("door-test", ENTRY, "", backend=backend)
    with pytest.raises(vault_write.SaveRefused) as err:
        vault_write.save_login_keyring("door-test", ENTRY, VALUE, backend=FakeKeyring(fail=True))
    assert str(err.value) == "the keyring refused the new entry"
    assert err.value.__cause__ is None and err.value.__context__ is None
    assert backend.writes == [("door-test", ENTRY)]


def test_keyring_writer_refuses_an_unsafe_backend(monkeypatch):
    import sys

    unsafe = types.SimpleNamespace(
        get_keyring=lambda: _backend_of("keyrings.alt.file", "PlaintextKeyring")
    )
    monkeypatch.setitem(sys.modules, "keyring", unsafe)
    with pytest.raises(vault_write.SaveRefused, match="^refused: the keyring backend is not a known"):
        vault_write.save_login_keyring("door-test", ENTRY, VALUE)


def test_writer_for_memory_and_bad_settings():
    with pytest.raises(ValueError, match="^the memory vault keeps nothing"):
        vault_write.writer_for({"vault": "memory"})
    with pytest.raises(ValueError, match="^bad vault setting"):
        vault_write.writer_for({"vault": "files"})
    with pytest.raises(ValueError, match="^vault aws needs aws_region"):
        vault_write.writer_for({"vault": "aws"})


def test_writer_for_aws_uses_the_machine_file_region(monkeypatch):
    seen = []

    class Secrets:
        def create_secret(self, Name, SecretString):
            seen.append(("create", Name))

    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a: object() if name == "boto3" else real(name))  # fmt: skip
    monkeypatch.setattr(vault_write, "_client",
                        lambda profile, region: seen.append((profile, region)) or Secrets())  # fmt: skip
    writer = vault_write.writer_for({"vault": "aws", "aws_region": "ap-south-1"})
    writer(ENTRY, VALUE)
    assert seen == [("default", "ap-south-1"), ("create", ENTRY)]
