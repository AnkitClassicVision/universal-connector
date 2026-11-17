from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
import threading
from contextlib import closing

import pytest

from universal_connector.keys import (
    KeyExists,
    NoActiveKey,
    has_active_key,
    mint,
    revoke,
    rotate,
    verify,
)
from universal_connector.state import StateDirError, open_state


@pytest.fixture
def d(tmp_path):
    return tmp_path / "state"


def test_mint_format(d):
    assert re.fullmatch(r"pc_[A-Za-z0-9_-]{43}", mint(d, "alpha"))


def test_verify_roundtrip(d):
    assert verify(d, mint(d, "alpha")) == "alpha"


def test_verify_picks_the_right_agent(d):
    a = mint(d, "alpha")
    b = mint(d, "beta")
    assert (verify(d, a), verify(d, b)) == ("alpha", "beta")


def test_verify_uses_constant_time_compare(d, monkeypatch):
    mint(d, "alpha")
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    assert verify(d, "pc_" + "x" * 43) is None
    assert len(calls) >= 1


def test_wrong_key_is_none(d):
    mint(d, "alpha")
    assert verify(d, "pc_" + "x" * 43) is None
    assert verify(d, "") is None
    assert verify(d, "x" * 10000) is None


def test_mint_twice_raises(d):
    mint(d, "alpha")
    with pytest.raises(KeyExists):
        mint(d, "alpha")


def test_revoke_takes_effect(d):
    key = mint(d, "alpha")
    assert revoke(d, "alpha") is True
    assert verify(d, key) is None
    assert has_active_key(d, "alpha") is False
    assert revoke(d, "alpha") is False


def test_rotate(d):
    old = mint(d, "alpha")
    new = rotate(d, "alpha")
    assert new != old
    assert verify(d, old) is None
    assert verify(d, new) == "alpha"
    assert has_active_key(d, "alpha") is True


def _state_bytes(d):
    files = [f for f in d.iterdir() if f.name.startswith("state.db")]
    assert files
    return b"".join(f.read_bytes() for f in files)


def _stored_hashes(d):
    with closing(open_state(d)) as db:
        return [r["key_sha256"] for r in db.execute("SELECT key_sha256 FROM agent_keys")]


def test_plaintext_key_not_on_disk(d):
    minted = mint(d, "alpha")
    assert _stored_hashes(d) == [hashlib.sha256(minted.encode()).hexdigest()]
    rotated = rotate(d, "alpha")
    assert _stored_hashes(d) == [hashlib.sha256(rotated.encode()).hexdigest()]
    data = _state_bytes(d)
    assert minted.encode() not in data
    assert rotated.encode() not in data


def test_rotate_without_active_key_raises(d):
    with pytest.raises(NoActiveKey):
        rotate(d, "never-minted")
    mint(d, "alpha")
    revoke(d, "alpha")
    with pytest.raises(NoActiveKey):
        rotate(d, "alpha")
    assert has_active_key(d, "alpha") is False


def test_concurrent_mint_one_wins(d):
    open_state(d).close()
    barrier = threading.Barrier(2)
    results = []

    def worker():
        barrier.wait()
        try:
            results.append(("key", mint(d, "alpha")))
        except KeyExists:
            results.append(("exists", None))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(kind for kind, _ in results) == ["exists", "key"]
    winner = next(value for kind, value in results if kind == "key")
    assert verify(d, winner) == "alpha"


def test_verify_odd_inputs_return_none(d):
    mint(d, "alpha")
    odd = ["pc_" + "\ud800" * 43, None, b"pc_" + b"x" * 43, 12345]
    assert all(verify(d, value) is None for value in odd)


def test_existing_loose_folder_is_tightened(d):
    d.mkdir()
    os.chmod(d, 0o755)
    (d / "state.db").touch()
    os.chmod(d / "state.db", 0o644)
    open_state(d).close()
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(d / "state.db").st_mode) == 0o600


def test_open_state_refuses_foreign_folder(d):
    d.mkdir()
    os.chmod(d, 0o755)
    (d / "notes.txt").write_text("not ours\n")
    with pytest.raises(StateDirError):
        open_state(d)
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o755
    assert not (d / "state.db").exists()


def test_open_state_accepts_empty_existing_folder(d):
    d.mkdir()
    os.chmod(d, 0o755)
    open_state(d).close()
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    assert (d / "state.db").exists()


def test_modes(d):
    open_state(d).close()
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(d / "state.db").st_mode) == 0o600
