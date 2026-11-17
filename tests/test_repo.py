"""Repository hygiene: no key shapes, no personal data, docs in step with the code."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from conftest import ROOT
from kit import __version__
from kit.harnesses import HARNESSES, limits_table
from kit.keyshape import file_line_hits
from kit.oddboro import version_table
from kit.plugins import all_plugins

SKIP = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv"}
RECIPE_HEADINGS = ["## Auth kinds", "## Connect it", "## Tiers", "## Scope hints", "## Smoke test", "## Gotchas"]


def repo_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for name in filenames:
            yield Path(dirpath) / name


def texts():
    for p in repo_files():
        try:
            yield p, p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def test_no_key_shaped_string_anywhere():
    hits = [(str(p.relative_to(ROOT)), line, rule) for p, t in texts() for line, rule in file_line_hits(p.name, t)]
    assert hits == []


def test_no_personal_data():
    owner = "an" + "kit"
    banned = [re.compile(x, re.I) for x in (
        "/" + "home/", "my" + "bcat", "clin" + "ic", "classic" + "vision", r"\b\d{12}\b",
        r"[a-z0-9-]+\.ts\.net",
    )]
    allowed_tailnet = re.compile(r"(tailnet-name|example)\.ts\.net", re.I)
    copyright_line = "Copyright 2026 " + owner.capitalize() + " Patel"
    # The one public place the owner's account appears: the install address the owner asked for.
    install = "github.com/" + owner.capitalize() + "Classic" + "Vision/universal-connector"
    for p, t in texts():
        rel = str(p.relative_to(ROOT))
        for n, line in enumerate(t.splitlines(), 1):
            if rel in ("NOTICE", "door/NOTICE") and line == copyright_line:
                continue
            if install in line and rel in ("README.md", "door/README.md", "runbooks/build-my-connector/04-door/STAGE.md"):
                continue
            if owner in line.lower():
                raise AssertionError(f"{rel}:{n} names the owner outside NOTICE")
            for rx in banned:
                for m in rx.finditer(line):
                    if rx.pattern.endswith(r"\.ts\.net") and allowed_tailnet.search(m.group(0)):
                        continue
                    raise AssertionError(f"{rel}:{n} matches a personal-data rule")


def test_the_door_ships_the_same_license_and_notice():
    for name in ("LICENSE", "NOTICE"):
        assert (ROOT / "door" / name).read_bytes() == (ROOT / name).read_bytes(), name


def test_the_root_test_run_leaves_the_door_tests_to_the_door():
    """`python -m pytest` here collects `tests/` only; the door's tests run inside `door/`."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    door = tomllib.loads((ROOT / "door" / "pyproject.toml").read_text(encoding="utf-8"))
    assert door["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_license_is_the_standard_text_and_notice_holds_the_copyright():
    import hashlib
    assert hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest().startswith("cfc7749b96f63bd3")
    assert (ROOT / "NOTICE").read_text(encoding="utf-8").splitlines()[0] == "Universal Connector"


def test_readme_names_every_plugin():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for p in all_plugins():
        assert f"`{p.id}`" in readme, p.id


def test_recipes_have_every_section_in_order():
    files = sorted((ROOT / "recipes").glob("*.md"))
    services = [f for f in files if f.name not in ("README.md", "_template.md")]
    assert len(services) >= 29
    index = (ROOT / "recipes" / "README.md").read_text(encoding="utf-8")
    for f in services:
        text = f.read_text(encoding="utf-8")
        positions = [text.find(h + "\n") for h in RECIPE_HEADINGS]
        assert all(pos >= 0 for pos in positions) and positions == sorted(positions), f.name
        assert f.name in index, f"{f.name} is missing from recipes/README.md"
        assert "--auth-kind" in text, f"{f.name} smoke test has no command"


def _between(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0].strip() + "\n"


def test_generated_tables_match_the_code():
    harn = (ROOT / "skills/connector-options/references/harnesses.md").read_text(encoding="utf-8")
    assert _between(harn, "<!-- limits:start -->", "<!-- limits:end -->") == limits_table()
    odd = (ROOT / "skills/connector-options/references/oddboro.md").read_text(encoding="utf-8")
    assert _between(odd, "<!-- oddboro:start -->", "<!-- oddboro:end -->") == version_table()


def test_every_harness_has_its_connect_stage():
    rb = ROOT / "runbooks" / "build-my-connector"
    for h in HARNESSES.values():
        assert (rb / h.stage / "STAGE.md").is_file(), h.stage


def test_versions_agree():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    first = re.search(r"^## \[(\d+\.\d+\.\d+)\]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M).group(1)
    assert version == project == first == __version__


def test_every_tool_named_in_a_stage_exists():
    for stage in (ROOT / "runbooks").rglob("STAGE.md"):
        for tool in re.findall(r"tools/([a-z_]+\.py)", stage.read_text(encoding="utf-8")):
            assert (ROOT / "tools" / tool).is_file(), f"{stage}: tools/{tool}"
