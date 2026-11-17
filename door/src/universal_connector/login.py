"""`uconnector login google`: one Google sign-in, saved by the door.

Installed-app flow with PKCE and a `state` value. A one-shot listener on 127.0.0.1 takes the one
redirect. The code, the tokens and the client secret stay in this process: they are never printed,
logged or put in an error. Every error text here is fixed.

The machine file names the vault entry with your own Desktop OAuth client
(`google_client_entry`) and the scopes to ask for (`google_scopes`). The record is saved to the
same vault the door reads.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import socket
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from universal_connector.machine import (
    DEFAULT_GOOGLE_CLIENT_ENTRY,
    GOOGLE_SCOPE_CHOICES,
    google_client_entry,
    google_scopes,
)
from universal_connector.manifest import ManifestError, load_manifest
from universal_connector.vault import SecretStore, SecretUnavailable

CLIENT_ENTRY = DEFAULT_GOOGLE_CLIENT_ENTRY
TARGET_PREFIX = "connector/oauth/"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
CALENDAR_URL = "https://www.googleapis.com/calendar/v3/calendars/primary"
SCOPES = GOOGLE_SCOPE_CHOICES
GMAIL_READ, GMAIL_DRAFT, CALENDAR_READ = GOOGLE_SCOPE_CHOICES
FRONT_DOOR_PORT = 8765
LOGIN_TIMEOUT_S = 300.0
REQUEST_DEADLINE_S = 5.0  # one request, in total, counted from accept
POLL_S = 0.02  # how often the accepting thread looks at the deadline and the taken redirect
JOIN_S = 1.0  # how long closing waits for cut connections' threads
LABEL = re.compile(r"[a-z][a-z0-9-]{0,31}")


class LoginError(Exception):
    """The sign-in stopped and nothing was saved. The text is fixed and holds no value."""


def entry_name(label: str) -> str:
    return f"{TARGET_PREFIX}google-{label}"


# -- the one-shot listener ---------------------------------------------------------------------


class _DeadlineReader(io.RawIOBase):
    """Reads one connection until a fixed deadline. Each read gets only the time that is left,
    so a client that sends one byte at a time cannot stretch the request."""

    def __init__(self, sock: socket.socket, deadline: float) -> None:
        super().__init__()
        self._sock = sock
        self._deadline = deadline

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("request deadline")  # the handler drops the connection
        self._sock.settimeout(left)
        return self._sock.recv_into(buffer)


class _Handler(BaseHTTPRequestHandler):
    timeout = REQUEST_DEADLINE_S  # also bounds the reply write

    def setup(self) -> None:
        super().setup()
        self.rfile.close()
        deadline = self.server.deadline_of(self.request)  # type: ignore[attr-defined]
        self.rfile = io.BufferedReader(_DeadlineReader(self.connection, deadline))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _reply(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        if parts.path != "/":
            self._reply(404, "not found")
            return
        query = parse_qs(parts.query)
        if not self.server.offer({k: v[0] for k, v in query.items() if v}):  # type: ignore[attr-defined]
            self._reply(404, "not found")  # a redirect was already taken, or the listener closed
            return
        try:
            self._reply(200, "You can close this tab and go back to the terminal.")
        finally:
            self.server.taken.set()  # type: ignore[attr-defined]  # only now, so closing cannot cut the reply


class _Server(ThreadingHTTPServer):
    """One daemon thread per connection, so a slow client cannot hold up another. Each connection
    has a deadline counted from accept. `cut` closes the listener and every open connection."""

    daemon_threads = True
    block_on_close = False  # `cut` joins with a bound instead

    def __init__(self, address: tuple[str, int]) -> None:
        self._lock = threading.Lock()
        self._live: dict[socket.socket, float] = {}
        self._workers: list[threading.Thread] = []
        self._closed = False
        self.params: dict[str, str] | None = None
        self.taken = threading.Event()
        super().__init__(address, _Handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        with self._lock:
            refused = self._closed
            if not refused:
                self._live[request] = time.monotonic() + REQUEST_DEADLINE_S
        if refused:
            self.shutdown_request(request)
            return
        worker = threading.Thread(
            target=self.process_request_thread, args=(request, client_address), daemon=True
        )
        worker.start()  # if this fails, the server's own handler cuts the request
        with self._lock:
            self._workers = [w for w in self._workers if w.is_alive()] + [worker]

    def deadline_of(self, request: Any) -> float:
        with self._lock:
            return self._live.get(request, 0.0)  # unknown: already cut, so no time at all

    def offer(self, params: dict[str, str]) -> bool:
        """Take the first redirect only, and only while the listener is open. The handler sets
        `taken` once its reply is written."""
        with self._lock:
            if self._closed or self.params is not None:
                return False
            self.params = params
        return True

    def shutdown_request(self, request: Any) -> None:
        with self._lock:  # never closed while `cut` holds it, so `cut` cannot hit a reused socket
            self._live.pop(request, None)
            super().shutdown_request(request)

    def handle_error(self, request: Any, client_address: Any) -> None:
        return  # a cut or reset connection; no text is kept

    def cut(self) -> None:
        self.server_close()
        with self._lock:
            self._closed = True
            for sock in self._live:
                try:
                    sock.shutdown(socket.SHUT_RDWR)  # wakes the thread blocked on it
                except OSError:
                    pass
            workers = list(self._workers)
        end = time.monotonic() + JOIN_S
        for worker in workers:
            worker.join(max(0.0, end - time.monotonic()))


class _Listener:
    """Binds 127.0.0.1 on a free port that is never the front door's. Takes one redirect."""

    host = "127.0.0.1"

    def __init__(self) -> None:
        server: _Server | None = None
        for _ in range(10):
            candidate = _Server((self.host, 0))
            if candidate.server_address[1] != FRONT_DOOR_PORT:
                server = candidate
                break
            candidate.server_close()
        if server is None:
            raise LoginError("no free port for the sign-in listener")
        self._server = server
        self.port: int = server.server_address[1]

    @property
    def address(self) -> tuple[str, int]:
        return self._server.server_address[:2]  # type: ignore[return-value]

    def wait(self, timeout_s: float) -> dict[str, str] | None:
        """The query of the one redirect, or None on timeout. Other paths are answered and skipped.
        This thread only accepts; it never reads a connection, so no client can hold it."""
        deadline = time.monotonic() + timeout_s
        while not self._server.taken.is_set():
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            self._server.timeout = min(POLL_S, left)
            self._server.handle_request()
        return self._server.params

    def close(self) -> None:
        self._server.cut()


# -- steps -------------------------------------------------------------------------------------


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _read_client(store: SecretStore, entry: str = CLIENT_ENTRY) -> tuple[str, str]:
    failed = False
    client: Any = None
    try:
        parsed = json.loads(store.get(entry))
        client = parsed.get("installed") if isinstance(parsed, dict) else None
    except (SecretUnavailable, ValueError):
        failed = True
    if failed or not isinstance(client, dict):
        raise LoginError("the oauth client entry could not be read")
    client_id, client_secret = client.get("client_id"), client.get("client_secret")
    if not (isinstance(client_id, str) and client_id and isinstance(client_secret, str) and client_secret):
        raise LoginError("the oauth client entry has no installed client")
    return client_id, client_secret


def _check_manifest(manifest_dir: Path, label: str, scopes: tuple[str, ...] = SCOPES) -> None:
    """The manifest has a google connection for this label and entry, and `scopes` cover every
    one of them: Gmail tools need both Gmail scopes, calendar tools the calendar scope."""
    failed = False
    try:
        manifest = load_manifest(manifest_dir)
    except ManifestError:
        failed = True
    if failed:
        raise LoginError("the manifest did not load")
    target = entry_name(label)
    mine = [
        c for c in manifest.connections
        if c.kind == "google" and c.auth.account == label and c.auth.secret == target
    ]  # fmt: skip
    if not mine:
        raise LoginError("no google connection in the manifest uses this label and entry")
    needed: set[str] = set()
    for conn in mine:
        for tool in conn.tools:
            if tool.name.startswith("gmail_"):
                needed |= {GMAIL_READ, GMAIL_DRAFT}
            elif tool.name.startswith("calendar_"):
                needed.add(CALENDAR_READ)
    if not needed <= set(scopes):
        raise LoginError("google_scopes in the machine file do not cover this label's connections")


def _expected_mailbox(machine: dict, label: str) -> str:
    accounts = machine.get("google_accounts")
    value = accounts.get(label) if isinstance(accounts, dict) else None
    if not isinstance(value, str) or "@" not in value:
        raise LoginError("the machine file has no google_accounts entry for this label")
    return value


def _exchange(http: Any, client_id: str, client_secret: str, code: str, verifier: str,
              redirect_uri: str) -> dict:
    failed = False
    status = 0
    body: Any = None
    try:
        response = http.post(
            TOKEN_URI,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        status = response.status_code
        body = response.json() if status == 200 else None
    except Exception:  # noqa: BLE001 - mapped; the original text can quote the request
        failed = True
    if failed:
        raise LoginError("the token exchange failed to reach google")
    if status != 200 or not isinstance(body, dict):
        raise LoginError(f"google refused the token exchange (status {status})")
    return body


def _mailbox(http: Any, access_token: str, scopes: tuple[str, ...] = SCOPES) -> str:
    """The signed-in address: the Gmail profile, or with no Gmail scope, the primary calendar."""
    url, key = (PROFILE_URL, "emailAddress") if GMAIL_READ in scopes else (CALENDAR_URL, "id")
    failed = False
    value: Any = None
    try:
        response = http.get(url, headers={"Authorization": f"Bearer {access_token}"})
        value = response.json().get(key) if response.status_code == 200 else None
    except Exception:  # noqa: BLE001 - mapped; the original text can quote the request
        failed = True
    if failed or not isinstance(value, str) or not value.strip():
        raise LoginError("the signed-in mailbox could not be read")
    return value.strip()


def run_login(
    label: str,
    manifest_dir: Path,
    machine: dict,
    store: SecretStore,
    http: Any,
    writer: Callable[[str, str], None],
    announce: Callable[[str], None],
    timeout_s: float = LOGIN_TIMEOUT_S,
) -> None:
    """Sign in once and save the record. Raise `LoginError` with a fixed text on any refusal.

    `writer(entry name, record)` saves to the vault the machine file names.
    """
    if not LABEL.fullmatch(label):
        raise LoginError("the label must be a short name such as work, never an address")
    try:
        client_entry, scopes = google_client_entry(machine), google_scopes(machine)
    except ValueError as err:  # fixed text from the machine file reader
        raise LoginError(str(err)) from None
    expected = _expected_mailbox(machine, label)
    _check_manifest(manifest_dir, label, scopes)
    client_id, client_secret = _read_client(store, client_entry)

    state = secrets.token_urlsafe(32)
    verifier, challenge = _pkce()
    listener = _Listener()
    try:
        redirect_uri = f"http://{listener.host}:{listener.port}/"
        announce(
            AUTH_URI
            + "?"
            + urlencode(
                {
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": " ".join(scopes),
                    "access_type": "offline",
                    "prompt": "consent",
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )
        params = listener.wait(timeout_s)
    finally:
        listener.close()
    if params is None:
        raise LoginError("timed out waiting for the sign-in")
    if not hmac.compare_digest(params.get("state", "").encode(), state.encode()):
        raise LoginError("the redirect did not carry the expected state")
    code = params.get("code", "")
    if "error" in params or not code:
        raise LoginError("google did not return a code")

    tokens = _exchange(http, client_id, client_secret, code, verifier, redirect_uri)
    refresh, access = tokens.get("refresh_token"), tokens.get("access_token")
    if not (isinstance(refresh, str) and refresh and isinstance(access, str) and access):
        raise LoginError("google returned no refresh token")
    granted = tokens.get("scope")
    if not isinstance(granted, str) or not set(scopes) <= set(granted.split()):
        raise LoginError("google did not grant every scope")

    actual = _mailbox(http, access, scopes)
    if actual.lower() != expected.strip().lower():
        raise LoginError("the signed-in mailbox is not the one the machine file names")

    record = json.dumps(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
            "scopes": list(scopes),
            "account": actual,
        }
    )
    failed = False
    try:
        writer(entry_name(label), record)
    except Exception:  # noqa: BLE001 - mapped; the original text is never kept
        failed = True
    if failed:
        raise LoginError("the vault did not take the sign-in; nothing was saved")


def default_deps(machine: dict) -> dict[str, Any]:
    """The real store, HTTP client and writer, all for the machine file's vault. Tests replace
    this. A bad vault setting, or the memory vault, raises ValueError with a fixed text."""
    import httpx

    from universal_connector.vault import store_for
    from universal_connector.vault_write import writer_for

    store, writer = store_for(machine), writer_for(machine)
    return {"store": store, "http": httpx.Client(timeout=30.0), "writer": writer}
