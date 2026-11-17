"""Key-shape rules. Reports rule names and line numbers only, never the matched text.

The rules look for strings shaped like real credentials. A hit means "this text
must not be printed, stored or committed". A miss proves nothing about short keys,
which is why the scanner never copies values in the first place.
"""

from __future__ import annotations

import re

RULES: dict[str, re.Pattern[str]] = {
    "aws-access-key": re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    "aws-secret-key": re.compile(
        r"(?i)aws_?secret_?access_?key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"
    ),
    "openai-style-key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "github-fine-grained-token": re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
    "gitlab-token": re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
    "slack-token": re.compile(r"xox[baprse]-[A-Za-z0-9-]{10,}"),
    "slack-webhook": re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]{20,}"),
    "google-api-key": re.compile(r"AIza[A-Za-z0-9_-]{35}"),
    "google-access-token": re.compile(r"ya29\.[A-Za-z0-9_-]{20,}"),
    "google-refresh-token": re.compile(r"1//[A-Za-z0-9_-]{20,}"),
    "stripe-style-key": re.compile(r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    "npm-token": re.compile(r"npm_[A-Za-z0-9]{36}"),
    "pypi-token": re.compile(r"pypi-[A-Za-z0-9_-]{50,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "url-credential": re.compile(r"[a-z][a-z0-9+.-]*://[^\s/:@\"'<>]+:[^\s/@\"'<>{}$]{6,}@[A-Za-z0-9.-]+"),
    "bearer-value": re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.+/=]{24,}"),
    "assigned-secret": re.compile(
        r"(?i)(key|token|secret|password|passwd|authorization)[\"']?\s*[:=]\s*[\"']?"
        r"(?P<value>[A-Za-z0-9_\-+/=.]{24,})"
    ),
    "long-hex": re.compile(r"\b[0-9a-fA-F]{40,}\b"),
}

_VAULT_CHARS = re.compile(r"[a-z0-9_.\-/]+")
_LONG_ALNUM_RUN = re.compile(r"[a-z0-9]{24,}")


def _is_vault_name(value: str) -> bool:
    """A vault pointer such as `work/github/read-token` is a name, not a value."""
    return "/" in value and _VAULT_CHARS.fullmatch(value) is not None and _LONG_ALNUM_RUN.search(value) is None


def rule_hits(text: str) -> list[str]:
    """Sorted names of the rules that match `text`. Never the matched text."""
    hits: set[str] = set()
    for name, pattern in RULES.items():
        if name == "assigned-secret":
            if any(not _is_vault_name(m.group("value")) for m in pattern.finditer(text)):
                hits.add(name)
        elif pattern.search(text):
            hits.add(name)
    return sorted(hits)


def line_hits(text: str) -> list[tuple[int, str]]:
    """(line number, rule name) for every line that matches a rule."""
    out: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        out.extend((number, rule) for rule in rule_hits(line))
    return out


def is_key_shaped(text: str) -> bool:
    return bool(rule_hits(text))
