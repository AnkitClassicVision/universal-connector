"""Secret scanner. Reports rule names only, never the matched text."""

from __future__ import annotations

import re

RULES: dict[str, re.Pattern[str]] = {
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "connector-key": re.compile(r"pc_[A-Za-z0-9_-]{43}"),
    "openai-style-key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "slack-token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "google-access-token": re.compile(r"ya29\.[A-Za-z0-9_-]{20,}"),
    "google-refresh-token": re.compile(r"1//[A-Za-z0-9_-]{20,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "assigned-secret": re.compile(
        r"(?i)(key|token|secret|password|passwd|authorization)[\"']?\s*[:=]\s*[\"']?"
        r"(?P<value>[A-Za-z0-9_\-+/=.]{24,})"
    ),
    "long-hex": re.compile(r"\b[0-9a-fA-F]{40,}\b"),
    "bearer-value": re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.+/=]{24,}"),
    "google-api-key": re.compile(r"AIza[A-Za-z0-9_-]{35}"),
    "github-fine-grained-token": re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
    "stripe-style-key": re.compile(r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    "aws-secret-key": re.compile(
        r"(?i)aws_?secret_?access_?key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"
    ),
}

_VAULT_CHARS = re.compile(r"[a-z0-9_.\-/]+")
_LONG_ALNUM_RUN = re.compile(r"[a-z0-9]{24,}")


def _is_vault_name(value: str) -> bool:
    """A vault entry name has `/`, only lower-case letters, digits and `_ . - /`, and no
    unbroken run of 24 or more lower-case letters and digits."""
    return (
        "/" in value
        and _VAULT_CHARS.fullmatch(value) is not None
        and _LONG_ALNUM_RUN.search(value) is None
    )


def _assigned_secret_hits(text: str) -> bool:
    pattern = RULES["assigned-secret"]
    return any(not _is_vault_name(m.group("value")) for m in pattern.finditer(text))


def find_secrets(text: str) -> list[str]:
    """Return the sorted, de-duplicated names of the rules that match `text`."""
    hits: set[str] = set()
    for name, pattern in RULES.items():
        if name == "assigned-secret":
            if _assigned_secret_hits(text):
                hits.add(name)
        elif pattern.search(text):
            hits.add(name)
    return sorted(hits)
