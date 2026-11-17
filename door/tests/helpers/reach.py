"""Walk the objects reachable from one object and look for a planted fake key."""

from __future__ import annotations

import gc
import types
from typing import Any


def reaches_text(root: Any, needle: str, skip: list[Any] | None = None, max_depth: int = 8) -> bool:
    """True when a str or bytes holding `needle` is reachable from `root` within `max_depth` steps.

    Modules, classes and built-in functions are not entered. A function is entered only through
    its closure and defaults. Objects in `skip` (a test's own vault stand-in) are not entered.
    """
    skip_ids = {id(obj) for obj in (skip or [])}
    seen: set[int] = set()
    frontier: list[tuple[Any, int]] = [(root, 0)]
    wanted = needle.encode("utf-8")
    while frontier:
        obj, depth = frontier.pop()
        if id(obj) in seen or id(obj) in skip_ids:
            continue
        seen.add(id(obj))
        if isinstance(obj, str):
            if needle in obj:
                return True
            continue
        if isinstance(obj, (bytes, bytearray)):
            if wanted in bytes(obj):
                return True
            continue
        if isinstance(obj, (types.ModuleType, type, types.BuiltinFunctionType)):
            continue
        if depth >= max_depth:
            continue
        if isinstance(obj, types.FunctionType):
            children: list[Any] = [obj.__closure__, obj.__defaults__, obj.__kwdefaults__]
        else:
            children = gc.get_referents(obj)
        frontier.extend((child, depth + 1) for child in children if child is not None)
    return False
