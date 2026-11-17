"""Running programs: listening TCP ports with the owning program's name, and browser profiles.

No port is probed or connected to. A program's command line is read in this process
only to answer "does it mention mcp?"; the command line itself is never kept.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from kit.core import FOUND, MISSING, UNAVAILABLE, Collector, Ctx, Finding, bounded_glob, read_bytes, read_text
from kit.plugins import Plugin

MAX_FDS = 50_000
PORT_HOW = "A local program is listening. Ask what it is; if it is an MCP server, add it as a remote upstream on the loopback address."


def _ip4(hexaddr: str) -> str:
    b = bytes.fromhex(hexaddr)
    return ".".join(str(x) for x in reversed(b))


def _ip6(hexaddr: str) -> str:
    words = [hexaddr[i:i + 8] for i in range(0, 32, 8)]
    raw = b"".join(bytes.fromhex(w)[::-1] for w in words)
    groups = [f"{int.from_bytes(raw[i:i + 2], 'big'):x}" for i in range(0, 16, 2)]
    text = ":".join(groups)
    if text == "0:0:0:0:0:0:0:1":
        return "::1"
    if text == "0:0:0:0:0:0:0:0":
        return "::"
    return text


def _listening(proc: Path, col: Collector) -> list[tuple[str, int, str]]:
    out = []
    for name, conv in (("tcp", _ip4), ("tcp6", _ip6)):
        status, text = read_text(proc / "net" / name)
        col.look(proc / "net" / name, status)
        for line in (text or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 10 or parts[3] != "0A":
                continue
            try:
                addr, port = parts[1].split(":")
                out.append((conv(addr), int(port, 16), parts[9]))
            except ValueError:
                continue
    return out


def _owners(proc: Path) -> dict[str, str]:
    """socket inode -> pid, for processes this user can see."""
    owners: dict[str, str] = {}
    seen = 0
    for piddir in bounded_glob(proc, "[0-9]*", 5000):
        try:
            fds = list((piddir / "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            seen += 1
            if seen > MAX_FDS:
                return owners
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            m = re.match(r"socket:\[(\d+)\]", target)
            if m:
                owners.setdefault(m.group(1), piddir.name)
    return owners


def _proc_info(proc: Path, pid: str) -> tuple[str, bool]:
    _, comm = read_text(proc / pid / "comm", 4096)
    _, raw = read_bytes(proc / pid / "cmdline", 65536, truncate=True)
    cmdline = (raw or b"").lower()
    del raw
    mentions = b"mcp" in cmdline
    del cmdline
    return (comm or "unknown").strip() or "unknown", mentions


def _add_port(ctx: Ctx, col: Collector, where: str, addr: str, port: int, program: str, mentions: bool) -> None:
    scope = "loopback only" if addr in ("127.0.0.1", "::1") or addr.startswith("127.") else (
        "all interfaces" if addr in ("0.0.0.0", "::") else "one interface")
    host_addr = f"[{addr}]" if ":" in addr else addr
    col.add(Finding(col.source, where, "listening-port", f"port {port}", transport="tcp",
                    host=f"tcp://{host_addr}:{port}", command=ctx.redactor.command(program),
                    key_where=["none"], auth_kind="not-applicable", how_to_add=PORT_HOW,
                    detail=f"{scope}; command line mentions mcp: {'yes' if mentions else 'no'}"))


def scan_ports(ctx: Ctx, col: Collector) -> None:
    if ctx.platform == "linux":
        proc = ctx.sys_path("/proc")
        rows = _listening(proc, col)
        owners = _owners(proc) if rows else {}
        hidden = 0
        for addr, port, inode in sorted(set(rows), key=lambda r: (r[1], r[0])):
            pid = owners.get(inode)
            if pid is None:
                hidden += 1
                continue
            program, mentions = _proc_info(proc, pid)
            _add_port(ctx, col, "/proc/net/tcp", addr, port, program, mentions)
        if hidden:
            col.notes.append(f"{hidden} listening port(s) belong to other users or the system; not listed.")
        return
    if ctx.platform == "darwin":
        out = ctx.runner(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-F", "pcn"], ctx.env, 15.0)
        if out is None:
            col.look("lsof -iTCP -sTCP:LISTEN", UNAVAILABLE)
            return
        col.look("lsof -iTCP -sTCP:LISTEN", FOUND)
        program = "unknown"
        for line in out.splitlines():
            if line.startswith("c"):
                program = line[1:]
            elif line.startswith("n") and ":" in line:
                addr, _, port = line[1:].rpartition(":")
                if port.isdigit():
                    _add_port(ctx, col, "lsof", addr.strip("[]").replace("*", "0.0.0.0"), int(port), program, False)
        return
    out = ctx.runner(["netstat", "-ano", "-p", "tcp"], ctx.env, 15.0)
    if out is None:
        col.look("netstat -ano", UNAVAILABLE)
        return
    col.look("netstat -ano", FOUND)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].upper() == "LISTENING":
            addr, _, port = parts[1].rpartition(":")
            if port.isdigit():
                _add_port(ctx, col, "netstat", addr.strip("[]"), int(port), f"pid {parts[4]}", False)


BROWSERS = {
    "linux": [("Chrome", ".config/google-chrome"), ("Chromium", ".config/chromium"),
              ("Brave", ".config/BraveSoftware/Brave-Browser"), ("Edge", ".config/microsoft-edge"), ("Firefox", ".mozilla/firefox")],
    "darwin": [("Chrome", "Library/Application Support/Google/Chrome"), ("Brave", "Library/Application Support/BraveSoftware/Brave-Browser"),
               ("Edge", "Library/Application Support/Microsoft Edge"), ("Firefox", "Library/Application Support/Firefox/Profiles")],
    "windows": [("Chrome", "AppData/Local/Google/Chrome/User Data"), ("Brave", "AppData/Local/BraveSoftware/Brave-Browser/User Data"),
                ("Edge", "AppData/Local/Microsoft/Edge/User Data"), ("Firefox", "AppData/Roaming/Mozilla/Firefox/Profiles")],
}


def scan_browsers(ctx: Ctx, col: Collector) -> None:
    for label, rel in BROWSERS.get(ctx.platform, []):
        base = ctx.home / rel
        if not base.is_dir():
            col.look(base, MISSING)
            continue
        col.look(base, FOUND)
        if label == "Firefox":
            count = len([p for p in bounded_glob(base, "*", 200) if p.is_dir() and "." in p.name])
        else:
            count = len([p for p in bounded_glob(base, "*", 200) if p.is_dir() and (p.name == "Default" or p.name.startswith("Profile "))])
        if count:
            col.add(Finding(col.source, col.ctx.show(base), "browser-profile", f"{label}: {count} profile(s)",
                            key_where=["browser-session"], auth_kind="browser-session",
                            how_to_add=("For a website with no API, give the door's browser lane its own profile and sign in "
                                        "yourself. Passwords stay in your password manager; the kit never moves them.")))


PLUGINS = [
    Plugin("ports", "Listening local ports (program names only, nothing probed)", "runtime",
           lambda ctx: ["/proc/net/tcp and /proc/net/tcp6 (Linux)", "lsof -iTCP -sTCP:LISTEN (macOS)", "netstat -ano (Windows)"], scan_ports),
    Plugin("browsers", "Browser profiles (count only)", "runtime",
           lambda ctx: [ctx.show(ctx.home / rel) for _, rel in BROWSERS.get(ctx.platform, [])], scan_browsers),
]
