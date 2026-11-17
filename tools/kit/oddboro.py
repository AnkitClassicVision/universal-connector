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
    sid = service_id(url)
    if len(sid) > SLUG_LIMIT:
        warns.append(f"the service id Oddboro makes from this address, {sid}, is {len(sid)} characters; "
                     f"keep it near {SLUG_LIMIT} or less so tool names stay under 64")
    return fails, warns


def service_id(url: str) -> str:
    """The service id Oddboro derives from an address: the lower-case host plus path, each run of
    characters that are not letters or digits turned into one '-', with the port and query dropped."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ""
    text = ((parts.hostname or "") + parts.path).lower()
    return "-".join(w for w in re.split(r"[^a-z0-9]+", text) if w)


def keyring_preflight(platform: str, which, runner, env: dict[str, str]) -> tuple[bool, str]:
    """Oddboro keeps pasted keys in the system's secret store. On Linux that is a Secret Service keyring
    reached through secret-tool. (ready, what to do). Names only: nothing is read from the store."""
    if platform in ("darwin", "windows"):
        return True, "the system's own store (Keychain or Credential Manager) is built in"
    if not which("secret-tool"):
        return False, "install secret-tool (package libsecret-tools or libsecret) so Oddboro can store the key"
    out = runner(["busctl", "--user", "list"], env, 10.0) if which("busctl") else None
    if out is None:
        return False, "could not list the session bus; check that a keyring (GNOME Keyring or KWallet) runs in your session"
    if "org.freedesktop.secrets" not in out:
        return False, "no Secret Service keyring is running in your session; start GNOME Keyring or KWallet and unlock it"
    return True, "a Secret Service keyring is running"


def version_table() -> str:
    rows = ["| Oddboro version | Pasted key | How Odds' calls reach the door | New door tools reach an existing Read grant by | Note |",
            "|---|---|---|---|---|"]
    rows += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in VERSIONS]
    return "\n".join(rows) + "\n"
