from __future__ import annotations

from universal_connector.upstreams.base import HoldBook, scrub


def test_scrub_replaces_every_value():
    text = "a one-111 b two-222 c one-111 and one-111-longer"
    out = scrub(text, ["one-111", "two-222", "one-111-longer"])
    assert out == "a [redacted] b [redacted] c [redacted] and [redacted]"
    assert "-longer" not in out


def test_scrub_ignores_empty_values():
    assert scrub("plain text", ["", "", ""]) == "plain text"
    assert scrub("plain text", []) == "plain text"


def test_scrub_longest_first_leaves_no_tail():
    short, longer = "fake-key-0001", "fake-key-0001-tail-9"
    for values in ([short, longer], [longer, short]):
        out = scrub(f"x {longer} y {short} z", values)
        assert out == "x [redacted] y [redacted] z"
        assert "-tail-9" not in out and "tail" not in out


def test_scrub_one_character_value():
    key = "fake-key-0001"
    # "e" is inside the key and inside the marker; "(" is a regex symbol.
    out = scrub(f"see {key} (end)", ["e", "(", key])
    bare = out.replace("[redacted]", "")
    assert key not in out and "0001" not in out and "-k" not in out
    assert "e" not in bare and "(" not in bare
    assert scrub("e", ["e"]) == "[redacted]"
    assert scrub("", ["e"]) == ""


def test_holdbook_drops_at_ttl_and_dedupes():
    now = [0.0]
    book = HoldBook(lambda: now[0], 900)
    book.put("a", object(), ["v", "v"])
    book.put("b", object(), ["v", ""])
    assert book.values() == ["v"]
    now[0] = 899
    assert book.drop_expired() == 0
    now[0] = 900
    assert book.drop_expired() == 2
    assert book.values() == []
