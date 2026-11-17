"""The Google sign-in and the vault writer. Offline: fake Google, fake vault, fake writer."""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from universal_connector import cli, login, vault_write
from universal_connector.vault import MemorySecretStore

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "examples" / "manifest"
ADDR = "owner@example.invalid"
OTHER = "someone-else@example.invalid"
ENTRY = "connector/oauth/google-work"

CLIENT_ID = "fake-client-id.example.invalid"
CLIENT_SECRET = "fake-cs-Q7x"
REFRESH = "fake-rt-Q7x"
ACCESS = "fake-at-Q7x"
CODE = "fake-code-Q7x"
SENTINELS = (CLIENT_SECRET, REFRESH, ACCESS, CODE)


def make_store() -> MemorySecretStore:
    return MemorySecretStore(
        {login.CLIENT_ENTRY: json.dumps({"installed": {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}})}
    )


class FakeGoogle:
    def __init__(self, *, mailbox=ADDR, token_status=200, refresh=REFRESH, scope=None,
                 no_scope=False):
        self.no_scope = no_scope
        self.mailbox = mailbox
        self.token_status = token_status
        self.refresh = refresh
        self.scope = " ".join(login.SCOPES) if scope is None else scope
        self.token_requests: list[dict[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == login.TOKEN_URI:
            self.token_requests.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
            if self.token_status != 200:
                # A hostile body that echoes secrets: none of it may reach any output.
                return httpx.Response(self.token_status, json={"error": f"{CLIENT_SECRET} {CODE}"})
            body = {"access_token": ACCESS, "expires_in": 3600}
            if not self.no_scope:
                body["scope"] = self.scope
            if self.refresh:
                body["refresh_token"] = self.refresh
            return httpx.Response(200, json=body)
        if url == login.PROFILE_URL:
            assert request.headers["authorization"] == f"Bearer {ACCESS}"
            return httpx.Response(200, json={"emailAddress": self.mailbox})
        if url == login.CALENDAR_URL:  # the mailbox check when no Gmail scope was asked for
            assert request.headers["authorization"] == f"Bearer {ACCESS}"
            return httpx.Response(200, json={"id": self.mailbox})
        return httpx.Response(500)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


class Browser:
    """Plays the owner's browser: reads the printed address, then hits the loopback redirect."""

    def __init__(self, *, state=None, code=CODE, extra="", act=True):
        self.state, self.code, self.extra, self.act = state, code, extra, act
        self.urls: list[str] = []
        self.threads: list[threading.Thread] = []

    def __call__(self, url: str) -> None:
        self.urls.append(url)
        if not self.act:
            return
        query = parse_qs(urlparse(url).query)
        target = (
            f"{query['redirect_uri'][0]}?code={self.code}&state={self.state or query['state'][0]}{self.extra}"
        )

        def hit() -> None:
            try:
                urllib.request.urlopen(target, timeout=5).read()
            except (urllib.error.URLError, OSError):
                pass

        thread = threading.Thread(target=hit)
        thread.start()
        self.threads.append(thread)

    def done(self) -> None:
        for thread in self.threads:
            thread.join(5)

    def query(self) -> dict[str, list[str]]:
        return parse_qs(urlparse(self.urls[0]).query)


class Writer:
    def __init__(self, fail=False):
        self.calls: list[tuple[str, str]] = []
        self.fail = fail

    def __call__(self, name: str, value: str) -> None:
        if self.fail:
            raise RuntimeError(f"vault said no about {REFRESH}")
        self.calls.append((name, value))


def go(google, browser, writer, *, label="work", machine=None, timeout_s=5.0, store=None):
    machine = {"google_accounts": {"work": ADDR}} if machine is None else machine
    try:
        login.run_login(
            label, MANIFEST_DIR, machine, store or make_store(), google.client(), writer, browser,
            timeout_s=timeout_s,
        )
    finally:
        getattr(browser, "done", lambda: None)()


def refused(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", port)) != 0


def port_of(browser: Browser) -> int:
    return urlparse(browser.query()["redirect_uri"][0]).port


def port_in(url: str) -> int:
    return urlparse(parse_qs(urlparse(url).query)["redirect_uri"][0]).port


def handler_threads() -> list[str]:
    return [t.name for t in threading.enumerate() if "process_request_thread" in t.name]


@pytest.fixture(autouse=True)
def no_thread_left():
    """Every thread a test starts has ended by the end of the test."""
    before = set(threading.enumerate())
    yield
    end = time.monotonic() + 2.0
    started = [t for t in threading.enumerate() if t not in before]
    for thread in started:
        thread.join(max(0.0, end - time.monotonic()))
    assert [t.name for t in started if t.is_alive()] == []


class Pest:
    """Another local process. It connects, sends `head`, then one byte every `every` seconds (or
    nothing), and never finishes a request. When the listener cuts it, it notes the time and
    connects again, until the connection is refused."""

    def __init__(self, port: int, head: bytes, every: float | None) -> None:
        self.port, self.head, self.every = port, head, every
        self.sessions: list[tuple[float, float]] = []  # (connected, cut)
        self.stop = threading.Event()
        first = self._connect()  # made here, so it is queued before the browser's redirect
        self.thread = threading.Thread(target=self._run, args=(first,), daemon=True)
        self.thread.start()

    def _connect(self) -> tuple[socket.socket | None, float]:
        try:
            sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        except OSError:
            return None, 0.0
        opened = time.monotonic()
        sock.settimeout(self.every or 0.25)
        try:
            sock.sendall(self.head)
        except OSError:
            pass
        return sock, opened

    def _held(self, sock: socket.socket) -> bool:
        """Trickle until the listener cuts the connection (True) or the test stops (False)."""
        while not self.stop.is_set():
            try:
                if sock.recv(1024) == b"":
                    return True
            except TimeoutError:
                if self.every is not None:
                    try:
                        sock.sendall(b"a")
                    except OSError:
                        return True
            except OSError:
                return True
        return False

    def _run(self, first: tuple[socket.socket | None, float]) -> None:
        sock, opened = first
        while sock is not None:
            cut = self._held(sock)
            sock.close()
            if not cut:
                return
            self.sessions.append((opened, time.monotonic()))
            sock, opened = self._connect()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(3)


# An idle connection, one that sent "G", and one that sent a whole request line with a wrong
# state. If the listener ever took a cut request as the redirect, the outcome would change.
PESTS = ((b"", None), (b"G", 0.5), (b"GET /?code=x&state=wrong HTTP/1.1\r\nX-Pad: ", 0.5))


# -- the sign-in -------------------------------------------------------------------------------


def test_login_saves_record_under_prefix() -> None:
    google, browser, writer = FakeGoogle(), Browser(), Writer()
    go(google, browser, writer)
    assert len(writer.calls) == 1
    name, value = writer.calls[0]
    assert name == ENTRY
    assert json.loads(value) == {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH,
        "scopes": list(login.SCOPES),
        "account": ADDR,
    }
    query = browser.query()
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == [" ".join(login.SCOPES)]
    redirect = urlparse(query["redirect_uri"][0])
    assert redirect.hostname == "127.0.0.1" and redirect.port != 8765
    (sent,) = google.token_requests
    assert sent["code"] == CODE and sent["redirect_uri"] == query["redirect_uri"][0]
    digest = hashlib.sha256(sent["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == query["code_challenge"][0]
    assert refused(port_of(browser))  # the listener stopped itself


def test_login_refuses_wrong_mailbox() -> None:
    google, browser, writer = FakeGoogle(mailbox=OTHER), Browser(), Writer()
    with pytest.raises(login.LoginError) as err:
        go(google, browser, writer)
    assert writer.calls == []
    assert OTHER not in str(err.value) and ADDR not in str(err.value)


def test_login_checks_state() -> None:
    google, browser, writer = FakeGoogle(), Browser(state="not-the-state"), Writer()
    with pytest.raises(login.LoginError, match="state"):
        go(google, browser, writer)
    assert writer.calls == [] and google.token_requests == []
    assert refused(port_of(browser))


def test_login_prints_no_secret(monkeypatch, capsys, caplog) -> None:
    real = login.run_login  # captured once: never wrap a wrapper
    current: dict = {}

    def wrapped(*a, **kw):
        printer, browser = kw["announce"], current["browser"]

        def announce(url: str) -> None:
            printer(url)
            browser(url)

        return real(*a, **{**kw, "announce": announce})

    monkeypatch.setattr(login, "run_login", wrapped)
    monkeypatch.setattr(
        cli, "_machine_or_none", lambda path=None: {"google_accounts": {"work": ADDR}}
    )
    monkeypatch.setattr(
        login, "default_deps",
        lambda machine: {"store": make_store(), "http": current["google"].client(),
                         "writer": current["writer"]},
    )

    def run(google, browser, writer) -> int:
        current.update(google=google, browser=browser, writer=writer)
        return cli.main(["login", "google", "--account", "work", "--manifest", str(MANIFEST_DIR)])

    cases = [
        (FakeGoogle(), Browser(), Writer(), 0),
        (FakeGoogle(token_status=400), Browser(), Writer(), 1),
        (FakeGoogle(mailbox=OTHER), Browser(), Writer(), 1),
        (FakeGoogle(), Browser(), Writer(fail=True), 1),
        (FakeGoogle(), Browser(state="bad"), Writer(), 1),
    ]
    for google, browser, writer, code in cases:
        assert run(google, browser, writer) == code
        browser.done()
    captured = capsys.readouterr()
    shown = captured.out + captured.err + caplog.text
    for secret in SENTINELS:
        assert secret not in shown
    assert OTHER not in shown
    assert shown.count("accounts.google.com") == len(cases)  # the address is printed once per run
    assert "saved the sign-in for work" in captured.out


def test_login_refuses_a_missing_refresh_token_or_scope() -> None:
    for google in (
        FakeGoogle(refresh=""), FakeGoogle(scope=login.SCOPES[0]), FakeGoogle(no_scope=True),
    ):
        writer = Writer()
        with pytest.raises(login.LoginError):
            go(google, Browser(), writer)
        assert writer.calls == []


def test_login_refuses_an_address_a_missing_account_and_an_unlisted_label() -> None:
    for label, machine in (
        (ADDR, None),
        ("work", {}),
        ("work", {"google_accounts": {"work": "no-at-sign"}}),
        ("other", {"google_accounts": {"other": ADDR}}),  # no manifest connection uses it
    ):
        browser, writer = Browser(act=False), Writer()
        with pytest.raises(login.LoginError):
            go(FakeGoogle(), browser, writer, label=label, machine=machine)
        assert browser.urls == [] and writer.calls == []  # refused before any listener opened


def test_login_refuses_a_google_denial_without_exchange() -> None:
    google, writer = FakeGoogle(), Writer()
    browser = Browser(code="", extra="&error=access_denied")
    with pytest.raises(login.LoginError):
        go(google, browser, writer)
    assert google.token_requests == [] and writer.calls == []


def test_idle_connection_does_not_block_redirect() -> None:
    google, writer, browser = FakeGoogle(), Writer(), Browser()
    idle: list[socket.socket] = []
    timers: list[threading.Timer] = []

    def announce(url: str) -> None:
        sock = socket.create_connection(("127.0.0.1", port_in(url)), timeout=5)  # accepted first, sends nothing
        idle.append(sock)
        timers.append(threading.Timer(2.5, sock.close))  # a one-thread listener is stuck until here
        timers[-1].start()
        browser(url)

    try:
        go(google, announce, writer, timeout_s=1.5)  # shorter than the real 5 s request deadline
    finally:
        browser.done()
        for timer in timers:
            timer.cancel()
            timer.join()
        for sock in idle:
            sock.close()
    assert len(writer.calls) == 1


def test_trickle_client_does_not_block_redirect() -> None:
    """Real 5 s request deadline. Slow clients connect first; the redirect is served at once,
    and closing the listener cuts them."""
    google, writer, browser = FakeGoogle(), Writer(), Browser()
    pests: list[Pest] = []

    def announce(url: str) -> None:
        pests.extend(Pest(port_in(url), head, every) for head, every in PESTS)
        browser(url)

    start = time.monotonic()
    try:
        go(google, announce, writer, timeout_s=20.0)
        took = time.monotonic() - start
        left = handler_threads()  # read at once: closing must not leave them running
        for pest in pests:
            pest.thread.join(2.0)  # ends by itself: its reconnect is refused
        ended = [not pest.thread.is_alive() for pest in pests]
    finally:
        browser.done()
        for pest in pests:
            pest.close()
    assert len(writer.calls) == 1
    assert took < 2.0  # far less than one request deadline
    assert left == [] and ended == [True] * len(PESTS)
    for pest in pests:
        ((opened, cut),) = pest.sessions  # cut once, by the close, never by its own deadline
        assert cut - opened < 2.5
    assert refused(port_of(browser))


def test_overall_deadline_holds_under_trickle() -> None:
    """Real 5 s request deadline, 5.2 s overall limit, no redirect. Each slow client is cut 5 s
    after accept while the listener still waits. It connects again, and the overall limit then
    closes the listener and cuts it mid-request. Nothing outlives the limit. Takes about 5.2 s."""
    limit = 5.2
    google, writer, browser = FakeGoogle(), Writer(), Browser(act=False)
    pests: list[Pest] = []

    def announce(url: str) -> None:
        browser(url)
        pests.extend(Pest(port_in(url), head, every) for head, every in PESTS)

    start = time.monotonic()
    try:
        with pytest.raises(login.LoginError, match="timed out"):
            go(google, announce, writer, timeout_s=limit)
        took = time.monotonic() - start
        left = handler_threads()
        for pest in pests:
            pest.thread.join(2.0)
        ended = [not pest.thread.is_alive() for pest in pests]
    finally:
        for pest in pests:
            pest.close()
    assert limit <= took < limit + 0.5
    assert left == [] and ended == [True] * len(PESTS)
    for pest in pests:
        (opened, cut), *later = pest.sessions
        assert 4.9 <= cut - opened < 5.15, pest.head  # its own deadline, counted from accept
        assert later and all(c - o < 1.0 for o, c in later), pest.head  # cut mid-request at the limit
        assert all(c - start < limit + 0.5 for _, c in pest.sessions), pest.head
    assert google.token_requests == [] and writer.calls == []
    assert refused(port_of(browser))


def test_wrong_path_is_ignored() -> None:
    google, writer, browser = FakeGoogle(), Writer(), Browser()

    def announce(url: str) -> None:
        query = parse_qs(urlparse(url).query)
        base = query["redirect_uri"][0]
        codes: list[int] = []

        def probe() -> None:  # from a thread, so the listener starts waiting at once
            for path in (f"{base}favicon.ico?code={CODE}&state={query['state'][0]}", f"{base}x/?error=1"):
                try:
                    urllib.request.urlopen(path, timeout=5)
                except urllib.error.HTTPError as exc:
                    codes.append(exc.code)  # answered 404, never taken as the redirect
            probes.append(codes)
            browser(url)

        thread = threading.Thread(target=probe)
        thread.start()
        browser.threads.append(thread)

    probes: list[list[int]] = []
    try:
        go(google, announce, writer)
    finally:
        browser.done()
    assert probes == [[404, 404]]
    assert len(writer.calls) == 1


def test_error_with_code_is_refused() -> None:
    google, writer = FakeGoogle(), Writer()
    with pytest.raises(login.LoginError):
        go(google, Browser(extra="&error=access_denied"), writer)
    assert google.token_requests == [] and writer.calls == []


def test_mailbox_compare_is_exact() -> None:
    for mailbox in ("owner@other.invalid", f"x{ADDR}", f"{ADDR}x", "owner", f"x.{ADDR}"):
        writer = Writer()
        with pytest.raises(login.LoginError):
            go(FakeGoogle(mailbox=mailbox), Browser(), writer)
        assert writer.calls == [], mailbox
    writer = Writer()
    go(FakeGoogle(mailbox=f" {ADDR.upper()} "), Browser(), writer)  # case and spaces do not matter
    assert len(writer.calls) == 1


def test_state_and_verifier_are_random() -> None:
    runs = []
    for _ in range(2):
        google, browser = FakeGoogle(), Browser()
        go(google, browser, Writer())
        runs.append((browser.query(), google.token_requests[0]["code_verifier"]))
    (q1, v1), (q2, v2) = runs
    assert q1["state"] != q2["state"] and len(q1["state"][0]) >= 32
    assert v1 != v2 and q1["code_challenge"] != q2["code_challenge"]
    assert all(43 <= len(v) <= 128 for v in (v1, v2))


def test_refusal_chains_no_value(monkeypatch) -> None:
    for broken in (FakeSecrets(fail_create=True), FakeSecrets(exists=True, fail_put=True)):
        monkeypatch.setattr(vault_write, "_client", lambda profile, region, b=broken: b)
        with pytest.raises(vault_write.SaveRefused) as err:
            vault_write.save_login_aws("p", "eu-west-1", ENTRY, "value-xyz")
        assert err.value.__cause__ is None and err.value.__context__ is None
        assert "xyz" not in str(err.value)
    with pytest.raises(login.LoginError) as lerr:
        go(FakeGoogle(), Browser(), Writer(fail=True))
    assert lerr.value.__cause__ is None and lerr.value.__context__ is None
    assert REFRESH not in str(lerr.value)


def test_listener_binds_loopback_only() -> None:
    listener = login._Listener()
    try:
        host, port = listener.address
        assert host == "127.0.0.1" and port != 8765 and port > 0
    finally:
        listener.close()
    assert refused(port)


def test_listener_times_out() -> None:
    google, browser, writer = FakeGoogle(), Browser(act=False), Writer()
    with pytest.raises(login.LoginError, match="timed out"):
        go(google, browser, writer, timeout_s=0.2)
    assert google.token_requests == [] and writer.calls == []
    assert refused(port_of(browser))


# -- the writer --------------------------------------------------------------------------------


class FakeSecrets:
    """Has only the two calls the writer may use. Any other call is an AttributeError."""

    def __init__(self, exists=False, fail_create=False, fail_put=False):
        self.exists, self.fail_create, self.fail_put = exists, fail_create, fail_put
        self.calls: list[tuple[str, str]] = []

    def create_secret(self, Name, SecretString):
        self.calls.append(("create", Name))
        if self.fail_create:
            raise RuntimeError(f"boom {SecretString}")
        if self.exists:
            err = Exception(f"exists {SecretString}")
            err.response = {"Error": {"Code": "ResourceExistsException"}}  # type: ignore[attr-defined]
            raise err

    def put_secret_value(self, SecretId, SecretString):
        self.calls.append(("put", SecretId))
        if self.fail_put:
            raise RuntimeError(f"boom {SecretString}")


OUTSIDE_PREFIX = (
    "skills/other/api-token", "google/tokens/gmail", "connector/oauthx/a", "connector/oauth/",
    "connector/oauth/../x", "connector/oauth/a/b", "/connector/oauth/a", "",
)


def test_save_login_refuses_outside_prefix(monkeypatch) -> None:
    monkeypatch.setattr(
        vault_write, "_client", lambda profile, region: pytest.fail("client must not open")
    )
    for name in OUTSIDE_PREFIX:
        with pytest.raises(vault_write.SaveRefused):
            vault_write.save_login_aws("p", "eu-west-1", name, "value")


def test_save_login_creates_then_puts(monkeypatch) -> None:
    fresh = FakeSecrets()
    regions: list[str] = []

    def client(profile, region, which=None):
        regions.append(region)
        return which

    monkeypatch.setattr(vault_write, "_client", lambda profile, region: client(profile, region, fresh))
    vault_write.save_login_aws("p", "eu-west-1", ENTRY, "value")
    assert fresh.calls == [("create", ENTRY)]
    assert regions == ["eu-west-1"]  # the machine file's Region, never a built-in one
    present = FakeSecrets(exists=True)
    monkeypatch.setattr(vault_write, "_client", lambda profile, region: present)
    vault_write.save_login_aws("p", "eu-west-1", ENTRY, "value")
    assert present.calls == [("create", ENTRY), ("put", ENTRY)]
    broken = FakeSecrets(fail_create=True)
    monkeypatch.setattr(vault_write, "_client", lambda profile, region: broken)
    with pytest.raises(vault_write.SaveRefused) as err:
        vault_write.save_login_aws("p", "eu-west-1", ENTRY, "value-xyz")
    assert broken.calls == [("create", ENTRY)]  # no put after a failed create
    assert "xyz" not in str(err.value) and err.value.__cause__ is None


# -- the client entry and the scopes come from the machine file ---------------------------------

CALENDAR = "https://www.googleapis.com/auth/calendar.readonly"
CALENDAR_ONLY = (
    "version: 1\nconnections:\n"
    "  - name: cal_home\n    kind: google\n"
    "    auth: {type: google-oauth, account: home, secret: connector/oauth/google-home}\n"
    "    scopes: [personal]\n    reach: starter\n"
    "    tools:\n      - {name: calendar_list_events, tier: green}\n"
)


def _calendar_manifest(tmp_path: Path) -> Path:
    folder = tmp_path / "cal-manifest"
    folder.mkdir()
    (folder / "connector.yaml").write_text(CALENDAR_ONLY)
    (folder / "agents.yaml").write_text("version: 1\nagents: []\n")
    return folder


def test_login_uses_the_configured_client_entry_and_scopes(tmp_path) -> None:
    client = json.dumps({"installed": {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}})
    store = MemorySecretStore({"my/google/desktop-client": client})  # not the default entry
    machine = {
        "google_client_entry": "my/google/desktop-client",
        "google_scopes": [CALENDAR],
        "google_accounts": {"home": ADDR},
    }
    google, browser, writer = FakeGoogle(scope=CALENDAR), Browser(), Writer()
    try:
        login.run_login("home", _calendar_manifest(tmp_path), machine, store, google.client(),
                        writer, browser, timeout_s=5.0)  # fmt: skip
    finally:
        browser.done()
    assert browser.query()["scope"] == [CALENDAR]  # only what the machine file names
    (name, value), = writer.calls
    assert name == "connector/oauth/google-home"
    assert json.loads(value)["scopes"] == [CALENDAR]


def test_login_refuses_scopes_that_do_not_cover_the_connections() -> None:
    machine = {"google_scopes": [CALENDAR], "google_accounts": {"work": ADDR}}
    browser, writer = Browser(act=False), Writer()
    with pytest.raises(login.LoginError, match="do not cover this label's connections"):
        go(FakeGoogle(), browser, writer, machine=machine)  # the example has Gmail tools
    assert browser.urls == [] and writer.calls == []


def test_login_refuses_a_bad_scope_setting_with_fixed_text() -> None:
    machine = {"google_scopes": ["https://mail.google.com/"], "google_accounts": {"work": ADDR}}
    browser, writer = Browser(act=False), Writer()
    with pytest.raises(login.LoginError, match="^bad google_scopes setting"):
        go(FakeGoogle(), browser, writer, machine=machine)
    assert browser.urls == [] and writer.calls == []


def test_login_with_the_memory_vault_is_refused_before_any_sign_in(tmp_path, capsys) -> None:
    machine = tmp_path / "m.yaml"
    machine.write_text("vault: memory\ngoogle_accounts:\n  work: owner@example.invalid\n")
    code = cli.main(["login", "google", "--account", "work", "--manifest", str(MANIFEST_DIR),
                     "--machine-file", str(machine)])  # fmt: skip
    assert code == 2
    captured = capsys.readouterr()
    assert captured.err == vault_write.MEMORY_KEEPS_NOTHING + "\n"
    assert "accounts.google.com" not in captured.out
