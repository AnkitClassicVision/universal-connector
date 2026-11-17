"""Shared pytest setup. Tests are offline unless marked `live`.

No test may reach the system keyring. The `keyring` library is replaced, for every test, by a
module that refuses every use and records it; a test that touches it fails at teardown. Tests
that need a keyring pass a fake backend object in.
"""

from __future__ import annotations

import sys
import types

import pytest


class _RefusingKeyring(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("keyring")
        self.touched: list[str] = []

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        self.touched.append(name)
        raise RuntimeError("tests never use the real keyring")


@pytest.fixture(autouse=True)
def no_real_keyring(monkeypatch):
    fake = _RefusingKeyring()
    monkeypatch.setitem(sys.modules, "keyring", fake)
    yield fake
    assert fake.touched == [], "a test reached for the real keyring"
