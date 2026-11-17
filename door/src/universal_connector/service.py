"""Service templates: render the right one for this system. Nothing here installs anything.

`uconnector install-service --print` writes the rendered text to standard output. Saving it and
turning the service on stays with you (`INSTALL_STEPS`). Foreground `uconnector serve` is the
fallback on every system.

Templates live in `deploy/` and ship inside the package as `universal_connector/deploy/`.
Placeholders: `{{INSTALL_DIR}}` (the folder that holds `uconnector`), `{{MACHINE_FILE}}`,
`{{MANIFEST_DIR}}`, `{{STATE_DIR}}`, and on Windows `{{USER_ID}}`. Every path must be absolute.
"""

from __future__ import annotations

import importlib.resources
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from xml.sax.saxutils import escape

from universal_connector import portable

TEMPLATES = {
    "linux": ("systemd", "uconnector.service"),
    "macos": ("launchd", "local.uconnector.door.plist"),
    "windows": ("windows", "uconnector-logon-task.xml"),
}
INSTALL_STEPS = {
    "linux": (
        "Save it as ~/.config/systemd/user/uconnector.service, then run yourself: "
        "systemctl --user daemon-reload && systemctl --user enable --now uconnector.service"
    ),
    "macos": (
        "Save it as ~/Library/LaunchAgents/local.uconnector.door.plist, then run yourself: "
        "launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.uconnector.door.plist"
    ),
    "windows": (
        "Save it as uconnector-logon-task.xml, then run yourself: "
        "schtasks /Create /TN uconnector /XML uconnector-logon-task.xml"
    ),
}
PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")
NOT_ABSOLUTE = "every path for a service must be absolute: {name}"
BAD_PATH = "a service path holds a character the service file cannot carry safely: {name}"
BAD_USER = "the Windows user name is not known or not plain; set USERDOMAIN and USERNAME"
MISSING = "the service templates are missing from this install"
_USER = re.compile(r"[A-Za-z0-9._ -]{1,64}(\\[A-Za-z0-9._ -]{1,64})?")
# Characters no template may carry: quotes break the argument lists, `%` and `$` are expanded
# by systemd and Task Scheduler, a backtick by shells that read the file.
_NEVER = set('"%$`')


def kind_for_platform() -> str:
    return portable.PLATFORM if portable.PLATFORM in TEMPLATES else "linux"


def template_text(kind: str) -> str:
    """The template, from the installed package, else from the source tree's `deploy/`."""
    folder, name = TEMPLATES[kind]
    packaged = importlib.resources.files("universal_connector").joinpath("deploy", folder, name)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    source = Path(__file__).resolve().parents[2] / "deploy" / folder / name
    if source.is_file():
        return source.read_text(encoding="utf-8")
    raise ValueError(MISSING)


def _clean_path(kind: str, name: str, value: str) -> str:
    pure = PureWindowsPath(value) if kind == "windows" else PurePosixPath(value)
    if not pure.is_absolute():
        raise ValueError(NOT_ABSOLUTE.format(name=name))
    if any(ord(ch) < 32 or ord(ch) == 127 or ch in _NEVER for ch in value):
        raise ValueError(BAD_PATH.format(name=name))
    if kind != "windows" and "\\" in value:  # systemd and launchd read a backslash as an escape
        raise ValueError(BAD_PATH.format(name=name))
    text = str(pure)
    # A trailing separator before a closing quote would escape it in a Windows argument list.
    # A pure path keeps one only for a drive root, which is no place for these files anyway.
    if kind == "windows" and text.endswith("\\"):
        raise ValueError(BAD_PATH.format(name=name))
    return text


def windows_user() -> str:
    domain, user = os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")
    value = f"{domain}\\{user}" if domain else user
    if not user or not _USER.fullmatch(value):
        raise ValueError(BAD_USER)
    return value


def render(
    kind: str,
    *,
    install_dir: str,
    machine_file: str,
    manifest_dir: str,
    state_dir: str,
    user_id: str | None = None,
) -> str:
    """The template for `kind` with every placeholder filled. Raise ValueError with fixed text."""
    values = {
        "INSTALL_DIR": _clean_path(kind, "install folder", install_dir),
        "MACHINE_FILE": _clean_path(kind, "machine file", machine_file),
        "MANIFEST_DIR": _clean_path(kind, "manifest folder", manifest_dir),
        "STATE_DIR": _clean_path(kind, "state folder", state_dir),
    }
    if kind == "windows":
        values["USER_ID"] = user_id if user_id is not None else windows_user()
        if not _USER.fullmatch(values["USER_ID"]):
            raise ValueError(BAD_USER)
    text = template_text(kind)
    xml = kind in ("macos", "windows")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", escape(value, {"'": "&apos;"}) if xml else value)
    if PLACEHOLDER.search(text):
        raise ValueError(MISSING)
    return text
