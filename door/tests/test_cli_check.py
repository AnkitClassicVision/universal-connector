from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from universal_connector.cli import main

ROOT = Path(__file__).resolve().parents[1]
OK = ROOT / "tests" / "fixtures" / "manifest_ok"


def test_check_ok_on_repo(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    assert main(["check", "--manifest", str(ROOT / "examples" / "manifest")]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_check_ok_from_the_repository_top_too(monkeypatch, capsys):
    """Inside a larger repository `check` scans from the Git top level wherever it starts, and
    reads the allow file there, so it gives the same answer from the top and from this folder."""
    done = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, check=False)  # fmt: skip
    top = Path(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else ROOT
    monkeypatch.chdir(top)
    assert main(["check", "--manifest", str(ROOT / "examples" / "manifest")]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_check_fails_on_planted_secret(tmp_path, monkeypatch, capsys):
    planted = "sk-" + "x" * 30
    (tmp_path / "notes.txt").write_text(f"pasted by mistake {planted}\n")
    monkeypatch.chdir(tmp_path)
    assert main(["check", "--manifest", str(OK)]) == 1
    out = capsys.readouterr().out
    assert "openai-style-key" in out
    assert "notes.txt" in out
    assert planted not in out


def test_check_passes_on_clean_folder(tmp_path, monkeypatch, capsys):
    (tmp_path / "notes.txt").write_text("nothing to see\n")
    monkeypatch.chdir(tmp_path)
    assert main(["check", "--manifest", str(OK)]) == 0


def test_check_reports_bad_manifest(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "manifest"
    bad.mkdir()
    (bad / "connector.yaml").write_text("version: 1\nconnections: []\n")
    (bad / "agents.yaml").write_text(
        "version: 1\nagents:\n  - {name: a, scopes: [restricted], reach: starter}\n"
    )
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 1
    assert "restricted cannot be granted in this version" in capsys.readouterr().out


def _check_with_allow(tmp_path, monkeypatch, capsys, allow_text):
    (tmp_path / "scan-allow.yaml").write_text(allow_text)
    monkeypatch.chdir(tmp_path)
    code = main(["check", "--manifest", str(OK)])
    return code, capsys.readouterr().out


@pytest.mark.parametrize("allow_text", [
    "allow: 42\n",
    "- just a list\n",
    "allow:\n  - 42\n",
    "allow:\n  - {path: 7, rules: [jwt], why: x}\n",
    "allow:\n  - {path: a.txt, rules: jwt, why: x}\n",
    "allow:\n  - {path: a.txt, rules: [jwt], why: 5}\n",
    "allow:\n  - {path: a.txt, rules: [no-such-rule], why: x}\n",
    "allow:\n  - {path: a.txt, rules: [[jwt]], why: x}\n",
    "allow:\n  - {path: a.txt, rules: [jwt]}\n",
])
def test_allow_list_bad_shape_is_problem_not_crash(tmp_path, monkeypatch, capsys, allow_text):
    (tmp_path / "a.txt").write_text("nothing\n")
    code, out = _check_with_allow(tmp_path, monkeypatch, capsys, allow_text)
    assert code == 1
    assert "scan-allow.yaml" in out


def test_allow_list_empty_rules_rejected(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.txt").write_text("nothing\n")
    code, out = _check_with_allow(
        tmp_path, monkeypatch, capsys, "allow:\n  - {path: a.txt, rules: [], why: because}\n"
    )
    assert code == 1
    assert "scan-allow.yaml" in out


def test_allow_list_empty_why_rejected(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.txt").write_text("nothing\n")
    code, _ = _check_with_allow(
        tmp_path, monkeypatch, capsys, "allow:\n  - {path: a.txt, rules: [jwt], why: '  '}\n"
    )
    assert code == 1


def test_allow_list_stale_path_rejected(tmp_path, monkeypatch, capsys):
    code, out = _check_with_allow(
        tmp_path, monkeypatch, capsys, "allow:\n  - {path: gone.txt, rules: [jwt], why: old}\n"
    )
    assert code == 1
    assert "gone.txt" in out


def test_check_uses_git_top_level(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    planted = "sk-" + "v" * 30
    (tmp_path / "top.txt").write_text(f"{planted}\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "ok.txt").write_text("nothing\n")
    monkeypatch.chdir(sub)
    assert main(["check", "--manifest", str(OK)]) == 1
    out = capsys.readouterr().out
    assert "top.txt" in out and "openai-style-key" in out
    assert planted not in out


def test_allow_list_permits_only_named_rules(tmp_path, monkeypatch, capsys):
    fake = "sk-" + "y" * 30
    (tmp_path / "fixture.txt").write_text(f"{fake}\n")
    (tmp_path / "scan-allow.yaml").write_text(
        "allow:\n  - path: fixture.txt\n    rules: [openai-style-key]\n    why: test fake\n"
    )
    monkeypatch.chdir(tmp_path)
    assert main(["check", "--manifest", str(OK)]) == 0
    (tmp_path / "fixture.txt").write_text(f"{fake}\nghp_{'z' * 36}\n")
    assert main(["check", "--manifest", str(OK)]) == 1
    assert "github-token" in capsys.readouterr().out
