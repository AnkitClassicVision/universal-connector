"""What each Oddboro version can do with a door, and the address rules it enforces.

Facts here come from a compatibility analysis of Oddboro releases. The per-version table
in the options guide is generated from `VERSIONS`, and a test keeps the two equal.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
FIRST_KEYED = (0, 0, 6)
GATEWAY_FROM = (0, 0, 8)
REFRESH_FROM = (0, 0, 11)
SLUG_LIMIT = 25

VERSIONS = [
    ("v0.0.1 to v0.0.5", "no: sign-in only, a pasted key cannot be used", "-", "-",
     "Update Oddboro first"),
    ("v0.0.6 to v0.0.7", "yes: + Add service, Takes a key", "each Odd's runner (Claude, Codex, Grok, Gemini) calls the door with its own client, so that runner's tool-name and timeout limits apply",
     "remove and re-add the Read grant (the key may need pasting again)", "Check each runner's limits"),
    ("v0.0.8 to v0.0.10", "yes", "through Oddboro's office gateway", "remove and re-add the Read grant (the key may need pasting again)", ""),
    ("v0.0.11 and later", "yes", "through Oddboro's office gateway", "a refresh button", "GET /api/health reports the version"),
]


def parse(text: str | None) -> tuple[int, int, int] | None:
    m = VERSION_RE.search(text or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def show(v: tuple[int, int, int] | None) -> str:
    return "unknown" if v is None else "v" + ".".join(map(str, v))


def facts(v: tuple[int, int, int] | None) -> dict:
    """What this version means for the connect stage. None means unknown."""
    if v is None:
        return {"version": "unknown", "supported": None,
                "next": "Read the version in Oddboro's Setup window, Updates section. A 'Takes a key' button means v0.0.6 or later."}
    if v < FIRST_KEYED:
        return {"version": show(v), "supported": False,
                "next": "Update Oddboro first: versions before v0.0.6 cannot use a pasted key."}
    return {
        "version": show(v), "supported": True,
        "calls": "direct from each runner" if v < GATEWAY_FROM else "office gateway",
        "new_door_tools": "refresh button" if v >= REFRESH_FROM else "remove and re-add the grant",
        "health_endpoint": v >= REFRESH_FROM,
        "next": ("Check each runner's own tool-name and timeout limits." if v < GATEWAY_FROM else "Go ahead."),
    }


def address_problems(url: str) -> tuple[list[str], list[str]]:
    """(failures, warnings) for an Oddboro service address."""
    fails, warns = [], []
    try:
        parts = urlsplit(url)
    except ValueError:
        return ["the address is not a URL"], []
    if parts.scheme != "https":
        fails.append("Oddboro accepts only https:// addresses with a publicly trusted certificate")
    if parts.query or parts.fragment:
        fails.append("use the exact path with no query or fragment")
    if parts.username or parts.password:
        fails.append("the address must not carry a user name or password")
    slug = len(parts.hostname or "") + len(parts.path.strip("/"))
    if slug > SLUG_LIMIT:
        warns.append(f"host plus path is {slug} characters; keep it near {SLUG_LIMIT} or less so tool names stay under 64")
    return fails, warns


def version_table() -> str:
    rows = ["| Oddboro version | Pasted key | How Odds' calls reach the door | New door tools reach an existing Read grant by | Note |",
            "|---|---|---|---|---|"]
    rows += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in VERSIONS]
    return "\n".join(rows) + "\n"
