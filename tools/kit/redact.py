"""The one filter every printed field passes.

Plug-ins read config values in this process only, to classify where a key lives.
They hand on names, kinds and locations. Each of those still goes through a
`Redactor`, because a person can name a server with a pasted key by mistake.
Anything that could be a value becomes `[hidden-N]`.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from urllib.parse import urlsplit

from kit.keyshape import is_key_shaped

LONG_RUN = re.compile(r"[A-Za-z0-9+/=]{24,}")
UUID_SHAPE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
LONG_DIGITS = re.compile(r"\d{10,}")
NAME_SHAPE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@ +()/-]{0,79}")
FIELD_SHAPE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}")
COMMAND_SHAPE = re.compile(r"[A-Za-z0-9_.+-]{1,48}")
MAX_DNS_LABEL = 30
HOST_SCHEMES = {"http", "https", "ws", "wss", "tcp"}


def looks_random(text: str) -> bool:
    """Some word of 16+ characters (split on `- _ . : / space`) with 3+ digits or mixed case.

    Keys are long unbroken runs; names are short words. A word like `GitHub` stays.
    """
    for word in re.split(r"[-_.:/ ]+", text):
        if len(word) < 16:
            continue
        digits = sum(c.isdigit() for c in word)
        if digits >= 3 or (any(c.isupper() for c in word) and any(c.islower() for c in word)):
            return True
    return False


LONG_SEGMENT = re.compile(r"[A-Za-z0-9+=]{24,}")


def risky(text: str) -> bool:
    """Could this name, host or path hold a value? Judged per path segment, so long paths stay readable."""
    if is_key_shaped(text) or UUID_SHAPE.search(text) or LONG_DIGITS.search(text):
        return True
    return any(LONG_SEGMENT.search(part) for part in re.split(r"[\\/]", text))


# C0 and C1 controls, zero-width marks and bidirectional overrides: none may reach output, where they
# could rewrite a terminal line or hide text from the person reading it.
CONTROLS = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]")


def strip_controls(text: str) -> str:
    return CONTROLS.sub("", str(text).replace("\t", " ").replace("\n", " ").replace("\r", " "))


class Redactor:
    """Hides anything that could be a value as `[hidden-<id>]`.

    With a salt (the scanner keeps one, owner-only, beside the person's settings) the id is an HMAC of
    the value, so the same value gets the same id on every run and inventories can be compared. Without
    one, ids are numbered by first appearance for this run only. The value itself stays in memory.
    """

    def __init__(self, salt: bytes | None = None) -> None:
        self._salt = salt
        self._seen: dict[str, str] = {}

    def hide(self, text: str) -> str:
        if text not in self._seen:
            if self._salt:
                digest = hmac.new(self._salt, text.encode("utf-8", "replace"), hashlib.sha256).hexdigest()[:10]
                self._seen[text] = f"[hidden-{digest}]"
            else:
                self._seen[text] = f"[hidden-{len(self._seen) + 1}]"
        return self._seen[text]

    @property
    def hidden_count(self) -> int:
        return len(self._seen)

    def _keep(self, text: str, shape: re.Pattern[str] | None, random_check: bool) -> bool:
        if not text or risky(text):
            return False
        if shape is not None and shape.fullmatch(text) is None:
            return False
        return not (random_check and looks_random(text))

    def name(self, text: object) -> str:
        """A server, profile, entry or skill name."""
        s = strip_controls(text).strip()
        return s if self._keep(s, NAME_SHAPE, True) else self.hide(s)

    def field(self, text: object) -> str:
        """A header or environment variable name."""
        s = strip_controls(text).strip()
        return s if self._keep(s, FIELD_SHAPE, True) else self.hide(s)

    def command(self, text: object) -> str:
        """The base name of an executable."""
        s = os.path.basename(strip_controls(text).strip().strip("\"'"))
        return s if self._keep(s, COMMAND_SHAPE, True) else self.hide(s)

    def host(self, url: str) -> str | None:
        """`scheme://host[:port]` only. Path, query, fragment and user info are dropped."""
        url = strip_controls(url)
        try:
            parts = urlsplit(url.strip())
            port = parts.port
        except ValueError:
            return self.hide(url)
        if not parts.scheme or not parts.hostname:
            return None
        if parts.scheme.lower() not in HOST_SCHEMES:
            return self.hide(url)
        host = parts.hostname
        labels = host.split(".")
        if any(len(label) > MAX_DNS_LABEL or looks_random(label) for label in labels) or risky(host):
            return self.hide(url)
        return f"{parts.scheme.lower()}://{host}" + (f":{port}" if port else "")

    def text(self, text: object, limit: int = 160) -> str:
        """One line of free text, such as a skill description. It is data: never an instruction."""
        s = " ".join(strip_controls(text).split())
        if len(s) > limit:
            s = s[: limit - 3].rstrip() + "..."
        if is_key_shaped(s) or LONG_RUN.search(s) or UUID_SHAPE.search(s):
            return "[description hidden: it looked like it held a key]"
        return s
