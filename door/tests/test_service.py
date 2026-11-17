"""Service templates and `uconnector install-service --print`. Nothing is ever installed."""

from __future__ import annotations

import configparser
import plistlib
import shlex
import subprocess
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from universal_connector import cli, portable, service
from universal_connector.cli import main

ROOT = Path(__file__).resolve().parents[1]
POSIX = {
    "install_dir": "/opt/uconnector/bin",
    "machine_file": "/srv/door/machine.yaml",
    "manifest_dir": "/srv/door/manifest",
    "state_dir": "/srv/door/state",
}
WINDOWS = {
    "install_dir": "C:\\Users\\someone\\.local\\bin",
    "machine_file": "C:\\Users\\someone\\door\\machine.yaml",
    "manifest_dir": "C:\\Users\\someone\\door\\manifest",
    "state_dir": "C:\\Users\\someone\\AppData\\Local\\universal-connector\\state",
}
TASK = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"


def test_systemd_unit():
    text = service.render("linux", **POSIX)
    unit = configparser.ConfigParser(interpolation=None)
    unit.read_string(text)
    svc = unit["Service"]
    args = shlex.split(svc["ExecStart"])
    assert args == [
        "/opt/uconnector/bin/uconnector", "serve",
        "--machine-file", "/srv/door/machine.yaml",
        "--manifest", "/srv/door/manifest",
        "--state", "/srv/door/state",
        "--host", "127.0.0.1", "--port", "8765",
    ]  # fmt: skip
    assert svc["UMask"] == "0077" and svc["Restart"] == "on-failure"
    assert svc["ExecReload"] == "/bin/kill -HUP $MAINPID"
    assert svc["WorkingDirectory"] == "/srv/door/manifest"
    assert unit["Install"]["WantedBy"] == "default.target"
    assert "Timer" not in text and "OnCalendar" not in text


def test_launchd_agent():
    plist = plistlib.loads(service.render("macos", **POSIX).encode("utf-8"))
    assert plist["Label"] == "local.uconnector.door"
    assert plist["ProgramArguments"] == [
        "/opt/uconnector/bin/uconnector", "serve",
        "--machine-file", "/srv/door/machine.yaml",
        "--manifest", "/srv/door/manifest",
        "--state", "/srv/door/state",
        "--host", "127.0.0.1", "--port", "8765",
    ]  # fmt: skip
    assert plist["Umask"] == 0o077 and plist["RunAtLoad"] is True
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert "StartCalendarInterval" not in plist and "StartInterval" not in plist


def test_windows_logon_task():
    root = ET.fromstring(service.render("windows", **WINDOWS, user_id="DESK\\someone").encode())
    trigger = root.find(f"{TASK}Triggers/{TASK}LogonTrigger")
    assert trigger is not None and trigger.findtext(f"{TASK}UserId") == "DESK\\someone"
    assert root.findtext(f"{TASK}Principals/{TASK}Principal/{TASK}RunLevel") == "LeastPrivilege"
    exec_ = root.find(f"{TASK}Actions/{TASK}Exec")
    assert exec_.findtext(f"{TASK}Command") == "C:\\Users\\someone\\.local\\bin\\uconnector.exe"
    assert exec_.findtext(f"{TASK}Arguments") == (
        'serve --machine-file "C:\\Users\\someone\\door\\machine.yaml" '
        '--manifest "C:\\Users\\someone\\door\\manifest" '
        '--state "C:\\Users\\someone\\AppData\\Local\\universal-connector\\state" '
        "--host 127.0.0.1 --port 8765"
    )
    assert len(root.findall(f"{TASK}Triggers/*")) == 1  # a logon task, no timer


@pytest.mark.parametrize("kind", ["linux", "macos", "windows"])
def test_every_path_must_be_absolute(kind):
    paths = dict(WINDOWS if kind == "windows" else POSIX)
    for key in paths:
        bad = {**paths, key: "relative/machine.yaml"}
        with pytest.raises(ValueError, match="^every path for a service must be absolute"):
            service.render(kind, **bad, user_id="someone")


@pytest.mark.parametrize("char", ['"', "%", "$", "`", "\n", "\x00"])
def test_characters_a_service_file_cannot_carry_are_refused(char):
    for kind, paths in (("linux", POSIX), ("macos", POSIX), ("windows", WINDOWS)):
        bad = {**paths, "state_dir": paths["state_dir"] + char + "x"}
        with pytest.raises(ValueError, match="^a service path holds a character"):
            service.render(kind, **bad, user_id="someone")


def test_backslash_refused_in_posix_files_and_a_bare_root_on_windows():
    with pytest.raises(ValueError):
        service.render("linux", **{**POSIX, "state_dir": "/srv/door\\state"})
    with pytest.raises(ValueError):
        service.render("windows", **{**WINDOWS, "state_dir": "C:\\"}, user_id="someone")


def test_xml_values_are_escaped():
    paths = {**POSIX, "manifest_dir": "/srv/R&D <door>"}
    plist = plistlib.loads(service.render("macos", **paths).encode("utf-8"))
    assert plist["WorkingDirectory"] == "/srv/R&D <door>"


def test_windows_user_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("USERDOMAIN", "DESK")
    monkeypatch.setenv("USERNAME", "someone")
    assert service.windows_user() == "DESK\\someone"
    monkeypatch.setenv("USERNAME", "bad<name>")
    with pytest.raises(ValueError, match="^the Windows user name"):
        service.windows_user()
    monkeypatch.delenv("USERNAME")
    with pytest.raises(ValueError):
        service.windows_user()


def test_templates_ship_inside_the_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    shipped = data["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    for kind, (folder, name) in service.TEMPLATES.items():
        source = f"deploy/{folder}/{name}"
        assert shipped[source] == f"universal_connector/deploy/{folder}/{name}", kind
        assert (ROOT / source).is_file()
        assert service.template_text(kind) == (ROOT / source).read_text(encoding="utf-8")


# -- the command ---------------------------------------------------------------------------------


@pytest.fixture
def nothing_runs(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("install-service must not run anything")

    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, refuse)
    monkeypatch.setattr("os.system", refuse)


def test_install_service_needs_print_and_prints_nothing_else(nothing_runs, capsys, tmp_path):
    code = main(["install-service", "--machine-file", POSIX["machine_file"], "--manifest",
                 POSIX["manifest_dir"], "--state", POSIX["state_dir"]])  # fmt: skip
    assert code == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == "install-service only prints a template; add --print. It installs nothing.\n"


@pytest.mark.parametrize(("platform", "marker"), [
    ("linux", "[Service]"), ("macos", "<key>ProgramArguments</key>"), ("windows", "<LogonTrigger>"),
])  # fmt: skip
def test_install_service_prints_the_template_for_this_system(
    platform, marker, nothing_runs, monkeypatch, capsys
):
    monkeypatch.setattr(portable, "PLATFORM", platform)
    monkeypatch.setenv("USERNAME", "someone")
    monkeypatch.setattr(cli, "_machine_file_exists", lambda path: True)  # the paths are examples
    paths = WINDOWS if platform == "windows" else POSIX
    code = main(["install-service", "--print", "--machine-file", paths["machine_file"],
                 "--manifest", paths["manifest_dir"], "--state", paths["state_dir"],
                 "--install-dir", paths["install_dir"]])  # fmt: skip
    assert code == 0
    out = capsys.readouterr()
    assert marker in out.out and "{{" not in out.out
    assert out.err == service.INSTALL_STEPS[platform] + "\n"


def test_install_service_refuses_a_relative_machine_file(nothing_runs, capsys):
    code = main(["install-service", "--print", "--machine-file", "machine.yaml", "--manifest",
                 POSIX["manifest_dir"], "--state", POSIX["state_dir"], "--install-dir",
                 POSIX["install_dir"]])  # fmt: skip
    assert code == 2
    out = capsys.readouterr()
    assert out.out == "" and out.err == "every path for a service must be absolute: machine file\n"


def test_install_service_refuses_a_machine_file_that_does_not_exist(nothing_runs, tmp_path, capsys):
    from universal_connector.machine import MISSING_MACHINE_FILE

    code = main(["install-service", "--print", "--machine-file", str(tmp_path / "nope.yaml"),
                 "--manifest", str(tmp_path), "--state", str(tmp_path / "state"),
                 "--install-dir", str(tmp_path)])  # fmt: skip
    assert code == 2
    out = capsys.readouterr()
    assert out.out == "" and out.err == MISSING_MACHINE_FILE + "\n"
    (tmp_path / "machine.yaml").write_text("vault: keyring\n")
    code = main(["install-service", "--print", "--machine-file", str(tmp_path / "machine.yaml"),
                 "--manifest", str(tmp_path), "--state", str(tmp_path / "state"),
                 "--install-dir", str(tmp_path)])  # fmt: skip
    assert code == 0 and "[Service]" in capsys.readouterr().out
