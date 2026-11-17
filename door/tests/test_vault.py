from __future__ import annotations

import json

import pytest

from universal_connector.vault import AwsSecretStore, MemorySecretStore, SecretUnavailable

FAKE_VALUE = "fake-value-not-a-real-secret-0001"


class FakeClient:
    def __init__(self, values: dict[str, str], fail: bool = False) -> None:
        self.values = values
        self.fail = fail
        self.get_calls = 0
        self.describe_calls = 0
        self.list_calls = 0

    def get_secret_value(self, SecretId: str) -> dict:
        self.get_calls += 1
        if self.fail or SecretId not in self.values:
            raise RuntimeError(f"boom while reading {SecretId}")
        return {"Name": SecretId, "SecretString": self.values[SecretId]}

    def describe_secret(self, SecretId: str) -> dict:
        self.describe_calls += 1
        if SecretId not in self.values:
            err = RuntimeError("not found")
            err.response = {"Error": {"Code": "ResourceNotFoundException"}}
            raise err
        return {"Name": SecretId}

    def list_secrets(self, **kwargs) -> dict:
        self.list_calls += 1
        names = sorted(self.values)
        if "NextToken" not in kwargs:
            return {"SecretList": [{"Name": n} for n in names[:1]], "NextToken": "page-2"}
        return {"SecretList": [{"Name": n} for n in names[1:]]}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def store(values: dict[str, str], **kw) -> tuple[AwsSecretStore, FakeClient, Clock]:
    client = FakeClient(values, fail=kw.pop("fail", False))
    clock = Clock()
    return AwsSecretStore(client=client, clock=clock, **kw), client, clock


def test_cache_hit():
    s, client, _ = store({"a/b": FAKE_VALUE})
    assert s.get("a/b") == FAKE_VALUE
    assert s.get("a/b") == FAKE_VALUE
    assert client.get_calls == 1


def test_cache_expiry():
    s, client, clock = store({"a/b": FAKE_VALUE})
    s.get("a/b")
    clock.now += 901
    s.get("a/b")
    assert client.get_calls == 2


def test_client_error_becomes_unavailable():
    s, _, _ = store({"a/b": FAKE_VALUE}, fail=True)
    with pytest.raises(SecretUnavailable) as err:
        s.get("a/b")
    assert "a/b" in str(err.value)
    assert FAKE_VALUE not in str(err.value)
    assert err.value.__cause__ is None


def test_exists_uses_describe_only():
    s, client, _ = store({"a/b": FAKE_VALUE})
    assert s.exists("a/b") is True
    assert s.exists("missing/entry") is False
    assert client.get_calls == 0
    assert client.describe_calls == 2


def test_field_and_field_names():
    value = json.dumps({"zeta": "fake-z", "alpha": "fake-a"})
    s, _, _ = store({"json/entry": value, "plain/entry": FAKE_VALUE})
    assert s.field_names("json/entry") == ["alpha", "zeta"]
    assert s.field("json/entry", "zeta") == "fake-z"
    assert s.field_names("plain/entry") == []
    with pytest.raises(SecretUnavailable) as err:
        s.field("json/entry", "missing")
    assert "fake-z" not in str(err.value) and "fake-a" not in str(err.value)


def test_repr_is_safe():
    s, _, _ = store({"a/b": FAKE_VALUE})
    s.get("a/b")
    assert FAKE_VALUE not in repr(s)
    assert FAKE_VALUE not in str(s)
    memory = MemorySecretStore({"a/b": FAKE_VALUE})
    assert FAKE_VALUE not in repr(memory)
    assert FAKE_VALUE not in str(memory)


def test_list_names_follows_pages():
    s, client, _ = store({"a/b": FAKE_VALUE, "c/d": FAKE_VALUE})
    assert s.list_names() == ["a/b", "c/d"]
    assert client.get_calls == 0 and client.list_calls == 2


def test_memory_store():
    memory = MemorySecretStore({"j/e": json.dumps({"k": "fake-v"}), "p/e": FAKE_VALUE})
    assert memory.get("p/e") == FAKE_VALUE
    assert memory.exists("p/e") is True and memory.exists("nope") is False
    assert memory.field("j/e", "k") == "fake-v"
    assert memory.field_names("j/e") == ["k"]
    with pytest.raises(SecretUnavailable):
        memory.get("nope")


def test_import_needs_no_aws_setup():
    s = AwsSecretStore(profile="no-such-profile-for-tests")
    assert "no-such-profile-for-tests" in repr(s)


def test_expired_entries_are_purged_on_any_call():
    s, _, clock = store({"A": FAKE_VALUE, "B": FAKE_VALUE})
    s.get("A")
    clock.now += 901
    s.get("B")
    assert s.cached_names() == ["B"]


def test_purge_counts_removed_and_other_calls_purge_first():
    values = {"A": json.dumps({"k": "fake-v"}), "B": FAKE_VALUE}
    s, _, clock = store(values)
    s.get("A")
    clock.now += 901
    assert s.purge() == 1
    assert s.cached_names() == []
    for call in (lambda: s.exists("A"), lambda: s.field("A", "k"), lambda: s.field_names("A")):
        s.get("B")
        clock.now += 901
        call()
        assert "B" not in s.cached_names()


def _no_chain(err):
    return err.value.__cause__ is None and err.value.__context__ is None


def test_unavailable_has_no_chained_context():
    s, client, _ = store({"a/b": FAKE_VALUE}, fail=True)
    with pytest.raises(SecretUnavailable) as err:
        s.get("a/b")
    assert _no_chain(err)

    def boom(**kwargs):
        raise RuntimeError("boom")

    client.describe_secret = boom
    client.list_secrets = boom
    for call in (lambda: s.exists("a/b"), s.list_names):
        with pytest.raises(SecretUnavailable) as err:
            call()
        assert _no_chain(err)
