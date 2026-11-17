"""The public tree holds no personal data and no secret shape.

Generic shapes only: this file must itself stay free of any real name, so it lists patterns,
never people or hosts. Its own examples are built at run time, and it skips itself.
"""

from __future__ import annotations

import re
from pathlib import Path

from universal_connector.cli import _load_allow, _read_text, _repo_files
from universal_connector.scan import find_secrets

ROOT = Path(__file__).resolve().parents[1]
SELF = "tests/test_public_tree.py"
FAKE_USER = "someone"
# Reserved names (RFC 2606, RFC 6761): no person or company can own them.
RESERVED = (".invalid", ".example", ".test", ".localhost", ".example.com", ".example.org")

SHAPES = {
    "a home folder": re.compile(rf"/(?:home|Users)/(?!{FAKE_USER}\b)[A-Za-z0-9_.-]+"),
    "a Windows home folder": re.compile(
        rf"(?i)[A-Z]:\\{{1,2}}Users\\{{1,2}}(?!{FAKE_USER}\b)[A-Za-z0-9_.-]+"
    ),
    "a 12-digit account id": re.compile(r"(?<![0-9A-Za-z])[0-9]{12}(?![0-9A-Za-z])"),
}
TAILNET = re.compile(r"\b[a-z0-9-]+\.([a-z0-9-]+)\.ts\.net\b")
# A domain ends in letters, so a git ref such as `repo@v0.1.0` is not read as an address.
MAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")


def _texts():
    for rel in _repo_files(ROOT):
        if rel in ("uv.lock", SELF):  # the lock holds package names, versions and hashes only
            continue
        text = _read_text(ROOT / rel)
        if text is not None:
            yield rel, text


def _reserved(domain: str) -> bool:
    domain = domain.lower()
    return domain in ("example.com", "example.org") or domain.endswith(RESERVED) or (
        domain.endswith(".ts.net") and ".tailnet-name." in f".{domain}"
    )


def personal_shapes(text: str) -> list[str]:
    found = [label for label, pattern in SHAPES.items() if pattern.search(text)]
    fake_tailnets = ("tailnet-name", "example")  # the same two fakes the kit repository allows
    if any(m.group(1) not in fake_tailnets and len(m.group(1)) > 2 for m in TAILNET.finditer(text)):
        found.append("a tailnet name")
    if any(not _reserved(m.group(1)) for m in MAIL.finditer(text)):
        found.append("a mail address")
    return found


def test_no_personal_data_shapes():
    found = [f"{rel}: {label}" for rel, text in _texts() for label in personal_shapes(text)]
    assert found == []


def test_no_secret_shape_outside_the_allow_list():
    allow, problems = _load_allow(ROOT)
    assert problems == []
    found = [
        f"{rel}: {rule}"
        for rel, text in _texts()
        for rule in find_secrets(text)
        if rule not in allow.get(rel, set())
    ]
    assert found == []


def test_the_shapes_catch_what_they_must():
    slash, back = "/", "\\"
    assert personal_shapes(f"{slash}home{slash}jdoe{slash}x") == ["a home folder"]
    assert personal_shapes(f"{slash}home{slash}{FAKE_USER}{slash}x") == []
    assert personal_shapes(f"C:{back}Users{back}jdoe") == ["a Windows home folder"]
    assert personal_shapes("arn:aws:iam::" + "1234567890" + "12:role/x") == ["a 12-digit account id"]
    ts = ".ts" + ".net"
    assert personal_shapes("door.tail" + "abc123" + ts) == ["a tailnet name"]
    assert personal_shapes("door.tailnet-name.ts.net and a.b2" + ts) == []
    assert personal_shapes("jdoe" + "@" + "company.net") == ["a mail address"]
    assert personal_shapes("you" + "@" + "example.com, x" + "@door.localhost") == []
    assert personal_shapes("git+https://example.invalid/door" + "@" + "v0.1.0#x") == []


# The SHA-256 of the Apache License 2.0 text as the Apache Software Foundation publishes it,
# in two halves so no line of this file looks like a long secret.
APACHE_2_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf75" + "6814053e847c10f3eb003417bc523d30"


def test_license_is_the_apache_2_text_with_a_notice():
    import hashlib
    import tomllib

    assert hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest() == APACHE_2_SHA256
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Copyright 2026 " in notice and "Apache License, Version 2.0" in notice
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE", "NOTICE"]


SOURCE_FILE_NAME = re.compile(r"\b[\w-]+\.(?:ts|tsx|svelte)(?![\w.])")
COMMIT_HASH = re.compile(r"(?i)\bcommit [0-9a-f]{7,40}\b")


def test_no_reference_to_non_public_source():
    found = []
    for rel, text in _texts():
        if not rel.endswith(".py") and rel != "README.md":
            continue
        if SOURCE_FILE_NAME.search(text) or COMMIT_HASH.search(text) or "packages/" in text:
            found.append(rel)
    assert found == []
    assert SOURCE_FILE_NAME.search("see " + "registry" + ".ts here")
    assert not SOURCE_FILE_NAME.search("door.tailnet-name.ts.net")


def _git_top() -> Path:
    import subprocess

    done = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, check=False)  # fmt: skip
    return Path(done.stdout.strip()).resolve() if done.returncode == 0 and done.stdout.strip() else ROOT


def test_the_repository_allow_file_matches_this_one_with_a_prefix():
    """`check` reads the allow file at the Git top level. Inside a larger repository that file
    must hold exactly this folder's entries, each with this folder's path in front."""
    top = _git_top()
    if top == ROOT.resolve():
        return  # the door on its own: this file is the one `check` reads
    prefix = ROOT.resolve().relative_to(top).as_posix() + "/"
    mine, problems = _load_allow(ROOT)
    theirs, top_problems = _load_allow(top)
    assert problems == [] and top_problems == []
    expected = {prefix + path: rules for path, rules in mine.items()}
    assert {p: r for p, r in theirs.items() if p.startswith(prefix)} == expected


def test_only_public_parts_are_shipped():
    top = {p.split("/", 1)[0] for p in _repo_files(ROOT)}
    assert top <= {
        ".gitignore", "README.md", "LICENSE", "NOTICE", "pyproject.toml", "uv.lock",
        "scan-allow.yaml", "src", "tests", "examples", "deploy",
    }  # fmt: skip
    for gone in ("infra", "handoffs", "out", "manifest", "machine.yaml", "resume.md"):
        assert not (ROOT / gone).exists(), gone
    files = set(_repo_files(ROOT))
    for example in ("examples/machine.yaml", "examples/manifest/connector.yaml",
                    "examples/manifest/agents.yaml", "examples/aws/door-read-policy.json"):  # fmt: skip
        assert example in files, example  # shipped, not hidden by an ignore rule
