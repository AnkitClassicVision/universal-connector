from __future__ import annotations

import re

import pytest

from universal_connector.audit import is_paused, record, set_paused, tail


@pytest.fixture
def d(tmp_path):
    return tmp_path / "state"


def entry(d, outcome: str, args: dict | None = None) -> None:
    record(d, agent="alpha", connection="brain_work", tool="search_thoughts", tier="green",
           outcome=outcome, duration_ms=12, args=args or {})


def test_audit_stores_hash_not_args(d):
    entry(d, "ok", {"q": "find-me-123"})
    assert b"find-me-123" not in (d / "state.db").read_bytes()
    row = tail(d, 1)[0]
    assert re.fullmatch(r"[0-9a-f]{64}", row["args_sha256"])
    assert row["outcome"] == "ok" and row["agent"] == "alpha" and row["duration_ms"] == 12


def test_audit_tail_order(d):
    for outcome in ("first", "second", "third"):
        entry(d, outcome)
    assert [r["outcome"] for r in tail(d)] == ["third", "second", "first"]
    assert [r["outcome"] for r in tail(d, 2)] == ["third", "second"]


def test_same_args_same_hash(d):
    entry(d, "ok", {"a": 1, "b": 2})
    entry(d, "ok", {"b": 2, "a": 1})
    first, second = tail(d, 2)
    assert first["args_sha256"] == second["args_sha256"]


def test_audit_names_cut_and_cleaned(d):
    record(d, agent="alpha", connection="c" * 50_000, tool="t" + chr(0xE9) + "\n\x00" + chr(0x202E) + "t" * 500,
           tier="", outcome="denied:unlisted", duration_ms=1, args={})
    record(d, agent="alpha", connection="ok name~", tool="a\tb\x7f", tier="", outcome="ok",
           duration_ms=1, args={})
    second, first = tail(d, 2)
    assert first["connection"] == "c" * 128
    assert first["tool"] == "t????" + "t" * 123 and len(first["tool"]) == 128
    assert second["connection"] == "ok name~" and second["tool"] == "a?b?"


def test_args_hash_is_salted_per_state(tmp_path):
    import hashlib
    import json

    args = {"to": "guess@example.invalid"}
    plain = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
    one, two = tmp_path / "one", tmp_path / "two"
    for directory in (one, two):
        entry(directory, "ok", args)
        entry(directory, "ok", args)
    first_one, second_one = (r["args_sha256"] for r in tail(one, 2))
    first_two = tail(two, 1)[0]["args_sha256"]
    assert first_one == second_one  # one state folder, one salt
    assert first_one != first_two  # another folder, another salt
    assert plain not in (first_one, first_two)  # an unsalted guess cannot be confirmed


def test_pause_flag(d):
    assert is_paused(d) is False
    set_paused(d, True)
    assert is_paused(d) is True
    set_paused(d, False)
    assert is_paused(d) is False
