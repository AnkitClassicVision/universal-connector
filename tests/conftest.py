"""Test helpers. Every test runs on fixtures only: a fake home, a fake root and fake CLIs.

Planted values all match `Qz9FAKE...x`. The leak checks collect every one of them
from the fixture files and assert that no 8-character slice of any of them appears
in what the tools print or write.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
FIX = ROOT / "tests" / "fixtures"
PLANT = re.compile(r"Qz9FAKE[A-Za-z0-9$]*x")
ENV_PLANTED = {"DEMO_SERVICE_TOKEN": "Qz9FAKEenv01x", "BW_SESSION": "Qz9FAKEenv02x"}
FAKE_CLIS = ("op", "bw", "gopass", "busctl")

sys.path.insert(0, str(TOOLS))


def planted_values() -> set[str]:
    values = set(ENV_PLANTED.values())
    for p in FIX.rglob("*"):
        if p.is_file():
            values.update(PLANT.findall(p.read_text(encoding="utf-8", errors="replace")))
    return values


def slices(value: str, n: int = 8) -> set[str]:
    return {value[i:i + n] for i in range(len(value) - n + 1)}


def assert_no_leak(*texts: str, values: set[str] | None = None) -> None:
    if values is None:
        values = planted_values()
        assert len(values) >= 40, "the fixtures should plant many distinct values"
    for value in sorted(values):
        for piece in slices(value):
            for i, text in enumerate(texts):
                assert piece not in text, f"output #{i} holds a slice of a planted value (tag {value[7:]})"


def _fake_bin(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    fake = FIX / "bin" / "fake_cli.py"
    for name in FAKE_CLIS:
        w = dest / name
        w.write_text(f"#!{sys.executable}\nimport runpy, sys\nsys.argv = [sys.argv[0], {name!r}] + sys.argv[1:]\n"
                     f"runpy.run_path({str(fake)!r}, run_name='__main__')\n", encoding="utf-8")
        w.chmod(0o755)
    return dest


@pytest.fixture
def full_tree(tmp_path: Path) -> dict[str, Path]:
    """A copy of the full fixture with the home path filled in and /proc socket links made."""
    base = tmp_path / "full"
    shutil.copytree(FIX / "full", base, symlinks=True)
    home, root = base / "home", base / "root"
    cj = home / ".claude.json"
    cj.write_text(cj.read_text(encoding="utf-8").replace("@HOME@", str(home)), encoding="utf-8")
    for pid, fd, inode in (("4242", "3", "1001"), ("4343", "5", "1002"), ("4343", "6", "1003")):
        fdir = root / "proc" / pid / "fd"
        fdir.mkdir(parents=True, exist_ok=True)
        os.symlink(f"socket:[{inode}]", fdir / fd)
    return {"home": home, "root": root, "project": home / "work" / "demo", "bin": _fake_bin(tmp_path / "bin"),
            "out": tmp_path / "out"}


def scan_env(bin_dir: Path, home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {"PATH": str(bin_dir), "HOME": str(home), "LANG": "C.UTF-8", "SSH_AUTH_SOCK": "/tmp/agent.sock",
           "GOOGLE_APPLICATION_CREDENTIALS": "~/keys/sa.json", **ENV_PLANTED}
    env.update(extra or {})
    return env


def run_tool(script: str, args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOLS / script), *args], env=env, cwd=cwd,
                          capture_output=True, text=True, timeout=120, check=False)


def scan_args(tree: dict[str, Path], *more: str) -> list[str]:
    return ["--home", str(tree["home"]), "--root", str(tree["root"]), "--platform", "linux",
            "--project", str(tree["project"]), *more]


def load_inventory(out: Path) -> dict:
    return json.loads((out / "inventory.json").read_text(encoding="utf-8"))


def by_name(inv: dict) -> dict[tuple[str, str], list[dict]]:
    index: dict[tuple[str, str], list[dict]] = {}
    for f in inv["findings"]:
        index.setdefault((f["source"], f["name"]), []).append(f)
    return index
