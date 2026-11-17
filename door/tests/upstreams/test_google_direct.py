from __future__ import annotations

import ast
import asyncio
import base64
import inspect
import json
import time

import pytest

import universal_connector.upstreams.google_direct as google_module
from helpers.reach import reaches_text
from universal_connector.models import Auth, Connection, Reach, Scope, Tier, ToolSpec
from universal_connector.scan import find_secrets
from universal_connector.upstreams.base import UpstreamAuthError, UpstreamError
from universal_connector.upstreams.google_direct import GoogleUpstream
from universal_connector.vault import MemorySecretStore, SecretUnavailable

MAILBOX = "box@example.invalid"
OTHER = "other@example.invalid"
REFRESH = "fake-refresh-0001"
KEY_NON_ASCII = "fake-key-é-0002"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class HttpErr(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.resp = type("Resp", (), {"status": status})()


class _Exec:
    def __init__(self, value, svc, fail: Exception | None = None, data: bool = True):
        self.value, self.svc, self.fail, self.data = value, svc, fail, data

    def execute(self):
        self.svc.enter()
        try:
            if self.data:
                self.svc.data_calls += 1
            if self.fail is not None:
                raise self.fail
            return self.value
        finally:
            self.svc.leave()


class FakeService:
    def __init__(self, address: str = MAILBOX) -> None:
        self.address = address
        self.list_args: dict = {}
        self.draft_body: dict = {}
        self.body_text = "x" * 30_000
        self.list_result: dict = {"items": [], "messages": []}
        self.data_calls = 0
        self.fail: Exception | None = None
        self.in_flight = 0
        self.max_in_flight = 0

    def enter(self):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        time.sleep(0.005)

    def leave(self):
        self.in_flight -= 1

    def __getattr__(self, name):
        if "send" in name.lower():
            pytest.fail(f"a send call was made: {name}")
        raise AttributeError(name)

    # calendar
    def calendars(self):
        return self

    def events(self):
        return self

    def list(self, **kw):
        self.list_args = kw
        return _Exec(self.list_result, self, self.fail)

    def get(self, **kw):
        if "calendarId" in kw and "eventId" not in kw:
            return _Exec({"id": self.address}, self, data=False)
        if kw.get("format") == "metadata":
            return _Exec(
                {
                    "id": kw["id"],
                    "threadId": "t1",
                    "snippet": "snip",
                    "payload": {"headers": [{"name": "Subject", "value": "s"}]},
                },
                self,
                self.fail,
            )
        if kw.get("format") == "full":
            raw = base64.urlsafe_b64encode(self.body_text.encode()).decode()
            return _Exec(
                {"id": kw["id"], "payload": {"mimeType": "text/plain", "body": {"data": raw}}},
                self,
                self.fail,
            )
        return _Exec({"id": kw.get("eventId")}, self, self.fail)

    # gmail
    def users(self):
        return self

    def getProfile(self, userId):
        return _Exec({"emailAddress": self.address}, self, data=False)

    def messages(self):
        return self

    def drafts(self):
        return self

    def create(self, userId, body):
        self.draft_body = body
        return _Exec({"id": "draft-1"}, self, self.fail)


class CountingStore(MemorySecretStore):
    def __init__(self, values):
        super().__init__(values)
        self.reads = 0

    def get(self, name):
        self.reads += 1
        return super().get(name)


GOOD_VALUES = {
    "g/client": '{"client_id": "fake-cid", "client_secret": "fake-csecret"}',
    "g/token": '{"refresh_token": "' + REFRESH + '", "email": "' + MAILBOX + '"}',
}
NO_EMAIL_VALUES = {
    "g/client": '{"client_id": "fake-cid", "client_secret": "fake-csecret"}',
    "g/token": '{"refresh_token": "' + REFRESH + '"}',
}


def make(
    fake=None, calls=None, fields=None, store_values=None, expected=None, clock=None, factory=None
):
    fake = fake or FakeService()

    def default_factory(api, version, creds):
        if calls is not None:
            calls.append(api)
        return fake

    conn = Connection(
        name="g",
        kind="google",
        auth=Auth(
            type="google-oauth",
            account="work",
            secret="g/client",
            token_secret="g/token",
            fields=fields if fields is not None else {"email": "email"},
        ),
        scopes={Scope.work},
        reach=Reach.full_read,
        tools=[ToolSpec(name="gmail_search", tier=Tier.green)],
    )
    store = CountingStore(store_values if store_values is not None else GOOD_VALUES)
    kwargs = {"clock": clock} if clock else {}
    up = GoogleUpstream(
        conn,
        store,
        service_factory=factory or default_factory,
        expected_address=expected,
        **kwargs,
    )
    up.test_store = store
    return up, fake


async def test_calendar_list_caps_at_50():
    up, fake = make()
    await up.call_tool(
        "calendar_list_events", {"time_min": "a", "time_max": "b", "max_results": 500}
    )
    assert fake.list_args["maxResults"] == 50


# Opaque and cursor-shaped, built here so no such literal sits in the repo.
CURSOR = "Cig" + "KGjdxNGcwbGhn" * 5


@pytest.mark.parametrize("cursor_key", ["nextPageToken", "nextSyncToken"])
async def test_calendar_list_drops_paging_and_sync_cursors(cursor_key):
    """No tool takes a cursor, and the scanner reads a cursor as an assigned secret: the live
    canary of 2026-11-16 failed `scan_clean` on this. Only the events and the time zone pass."""
    fake = FakeService()
    events = [{"id": "e1"}, {"id": "e2"}]
    fake.list_result = {"kind": "calendar#events", "timeZone": "UTC", "items": events}
    fake.list_result[cursor_key] = CURSOR
    up, _ = make(fake=fake)
    out = await up.call_tool("calendar_list_events", {"time_min": "a", "time_max": "b"})
    assert cursor_key not in out and CURSOR not in out
    assert find_secrets(out) == []
    assert json.loads(out) == {"timeZone": "UTC", "items": events}


async def test_gmail_search_caps_at_25():
    up, fake = make()
    await up.call_tool("gmail_search", {"query": "q", "max_results": 99})
    assert fake.list_args["maxResults"] == 25


async def test_wrong_account_raises():
    up, _ = make(fake=FakeService(address=OTHER))
    with pytest.raises(UpstreamAuthError) as err:
        await up.call_tool("gmail_search", {"query": "q"})
    assert str(err.value) == "wrong-account"
    assert OTHER not in str(err.value) and MAILBOX not in str(err.value)


async def test_wrong_account_blocks_before_data_call():
    fake = FakeService(address=OTHER)
    up, _ = make(fake=fake)
    calls = [
        ("calendar_list_events", {"time_min": "a", "time_max": "b"}),
        ("calendar_get_event", {"event_id": "e"}),
        ("gmail_search", {"query": "q"}),
        ("gmail_get_message", {"message_id": "m"}),
        ("gmail_create_draft", {"to": OTHER, "subject": "s", "body": "b"}),
    ]
    for name, args in calls:
        with pytest.raises(UpstreamAuthError, match="wrong-account"):
            await up.call_tool(name, args)
    assert fake.data_calls == 0 and fake.draft_body == {} and fake.list_args == {}


async def test_wrong_account_rechecked_after_ttl():
    clock = Clock()
    up, fake = make(clock=clock)
    await up.call_tool("gmail_search", {"query": "q"})
    fake.address = OTHER
    await up.call_tool("gmail_search", {"query": "q"})  # still held, no recheck
    clock.now += 900
    with pytest.raises(UpstreamAuthError, match="wrong-account"):
        await up.call_tool("gmail_search", {"query": "q"})


async def test_missing_field_is_needs_login():
    up, _ = make(store_values={"g/client": '{"client_id": "fake-cid"}', "g/token": "{}"})
    with pytest.raises(UpstreamAuthError) as err:
        await up.call_tool("gmail_search", {"query": "q"})
    assert str(err.value) == "needs-login"


async def test_draft_returns_id():
    up, fake = make()
    out = await up.call_tool("gmail_create_draft", {"to": OTHER, "subject": "s", "body": "b"})
    assert "draft-1" in out
    assert "raw" in fake.draft_body["message"]


def test_no_send_function():
    assert not [n for n in dir(GoogleUpstream) if "send" in n.lower()]


def test_no_send_anywhere_in_source():
    tree = ast.parse(inspect.getsource(google_module))
    found: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.append(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.arg) or isinstance(node, ast.keyword) and node.arg:
            names.append(node.arg)
        elif isinstance(node, ast.alias):
            names.append(node.name)
        found += [n for n in names if "send" in n.lower()]
    assert found == []


PLAN_FIVE = {
    "calendar_list_events",
    "calendar_get_event",
    "gmail_search",
    "gmail_get_message",
    "gmail_create_draft",
}
TOOL_ARGS = {
    "calendar_list_events": {"time_min": "a", "time_max": "b"},
    "calendar_get_event": {"event_id": "e"},
    "gmail_search": {"query": "q"},
    "gmail_get_message": {"message_id": "m"},
    "gmail_create_draft": {"to": OTHER, "subject": "s", "body": "b"},
}


def test_tools_are_exactly_the_plan_five():
    assert set(google_module._TOOLS) == PLAN_FIVE
    assert {t.name for t in google_module._TOOLS.values()} == PLAN_FIVE
    handlers = {n.removeprefix("_tool_") for n in dir(GoogleUpstream) if n.startswith("_tool_")}
    assert handlers == PLAN_FIVE


async def test_send_is_never_called():
    """Run every entry in _TOOLS. The fake fails the test on any attribute holding `send`."""
    assert set(TOOL_ARGS) == set(google_module._TOOLS), "every tool needs arguments here"
    up, fake = make()
    for name in google_module._TOOLS:
        await up.call_tool(name, TOOL_ARGS[name])
    with pytest.raises(pytest.fail.Exception):
        getattr(fake.users(), "se" + "nd")


async def test_probe_runs_under_the_lock():
    calls: list[str] = []
    up, _ = make(calls=calls)
    await up._lock.acquire()
    task = asyncio.create_task(up.probe())
    done, _ = await asyncio.wait({task}, timeout=0.3)
    touched = (list(calls), up.test_store.reads)
    up._lock.release()
    result = await task
    assert not done and touched == ([], 0), "probe touched the store or client without the lock"
    assert result.ok is True and calls == ["gmail"]


async def test_key_scrubbed_when_hold_drops_mid_call():
    """The Task 11 purge loop drops the hold while the call runs. The key must not come back."""
    clock, late, holder = Clock(), {"on": False}, {}

    class LateFake(FakeService):
        def get(self, **kw):
            if late["on"] and kw.get("format") == "full":
                clock.now += 900
                holder["up"].purge()
            return super().get(**kw)

    fake = LateFake()
    fake.body_text = f"refresh {REFRESH} secret fake-csecret"
    up, _ = make(fake=fake, clock=clock)
    holder["up"] = up
    await up.call_tool("gmail_get_message", {"message_id": "m"})  # hold exists for the next call
    late["on"] = True
    for _ in range(2):  # first from the hold, then from a fresh store read
        out = await up.call_tool("gmail_get_message", {"message_id": "m"})
        assert REFRESH not in out and "fake-csecret" not in out and "[redacted]" in out
        assert up.secret_values() == []


async def test_concurrent_calls_refresh_once():
    calls: list[str] = []
    up, _ = make(calls=calls)
    await asyncio.gather(*(up.call_tool("gmail_search", {"query": "q"}) for _ in range(5)))
    assert calls == ["gmail"]


async def test_calls_never_overlap():
    up, fake = make()
    await asyncio.gather(
        *(up.call_tool("gmail_search", {"query": "q"}) for _ in range(4)),
        *(up.call_tool("calendar_get_event", {"event_id": "e"}) for _ in range(4)),
    )
    assert fake.max_in_flight == 1


async def test_body_cut_at_20000():
    up, _ = make()
    out = await up.call_tool("gmail_get_message", {"message_id": "m1"})
    assert out.count("x") == 20_000


async def test_account_not_set_raises():
    up, _ = make(fields={}, store_values=NO_EMAIL_VALUES)
    with pytest.raises(UpstreamAuthError) as err:
        await up.call_tool("gmail_search", {"query": "q"})
    assert str(err.value) == "account-not-set"


async def test_email_field_set_but_missing_fails_closed():
    up, _ = make(fields={"email": "email"}, store_values=NO_EMAIL_VALUES, expected=MAILBOX)
    with pytest.raises(UpstreamAuthError) as err:
        await up.call_tool("gmail_search", {"query": "q"})
    assert str(err.value) == "account-not-set"


async def test_expected_address_is_used_when_no_vault_field():
    up, _ = make(fields={}, store_values=NO_EMAIL_VALUES, expected=MAILBOX)
    await up.call_tool("gmail_search", {"query": "q"})
    wrong, _ = make(
        fake=FakeService(address=OTHER),
        fields={},
        store_values=NO_EMAIL_VALUES,
        expected=MAILBOX,
    )
    with pytest.raises(UpstreamAuthError, match="wrong-account"):
        await wrong.call_tool("gmail_search", {"query": "q"})


async def test_values_dropped_after_ttl():
    clock = Clock()
    up, _ = make(clock=clock)
    await up.call_tool("gmail_search", {"query": "q"})
    assert REFRESH in up.secret_values()
    reads = up.test_store.reads
    clock.now += 899
    assert REFRESH in up.secret_values()
    clock.now += 1
    assert up.secret_values() == []
    await up.call_tool("gmail_search", {"query": "q"})
    assert up.test_store.reads > reads
    assert len(up.secret_values()) == len(set(up.secret_values()))


async def test_purge_counts_drops():
    clock = Clock()
    up, _ = make(clock=clock)
    await up.call_tool("gmail_search", {"query": "q"})
    assert up.purge() == 0
    clock.now += 900
    assert up.purge() >= 1
    assert up.purge() == 0


async def test_unexpected_error_holds_no_secret():
    def boom_factory(api, version, creds):
        raise RuntimeError(f"cannot build with {KEY_NON_ASCII}")

    up, _ = make(factory=boom_factory)
    with pytest.raises(UpstreamError) as err:
        await up.call_tool("gmail_search", {"query": "q"})
    _assert_clean(err.value)
    fake = FakeService()
    fake.fail = ValueError(f"data call with {KEY_NON_ASCII}")
    up2, _ = make(fake=fake)
    with pytest.raises(UpstreamError) as err2:
        await up2.call_tool("gmail_search", {"query": "q"})
    _assert_clean(err2.value)


def _assert_clean(exc: BaseException) -> None:
    for text in (str(exc), repr(exc), repr(exc.args)):
        assert KEY_NON_ASCII not in text and "fake-cid" not in text and REFRESH not in text
    assert exc.__context__ is None and exc.__cause__ is None


async def test_failing_call_maps_401_and_500():
    fake = FakeService()
    fake.fail = HttpErr(401, f"nope {REFRESH}")
    up, _ = make(fake=fake)
    with pytest.raises(UpstreamAuthError) as err:
        await up.call_tool("gmail_search", {"query": "q"})
    _assert_clean(err.value)
    fake.fail = HttpErr(500, f"broken {REFRESH}")
    with pytest.raises(UpstreamError) as err2:
        await up.call_tool("gmail_search", {"query": "q"})
    assert not isinstance(err2.value, UpstreamAuthError)
    _assert_clean(err2.value)


async def test_missing_entry_probe_is_not_in_vault():
    up, _ = make(store_values={})
    result = await up.probe()
    assert result.ok is False and result.status == "not-in-vault"


async def test_missing_entry_call_raises_secret_unavailable():
    up, _ = make(store_values={})
    with pytest.raises(SecretUnavailable):
        await up.call_tool("gmail_search", {"query": "q"})


async def test_result_is_scrubbed():
    fake = FakeService()
    fake.body_text = f"your token is {REFRESH}"
    up, _ = make(fake=fake)
    out = await up.call_tool("gmail_get_message", {"message_id": "m1"})
    assert REFRESH not in out and "[redacted]" in out


async def test_probe_never_ok_on_failure():
    ok, _ = make()
    assert (await ok.probe()).ok is True
    wrong, _ = make(fake=FakeService(address=OTHER))
    assert (await wrong.probe()).ok is False

    def boom(api, version, creds):
        raise RuntimeError("down")

    dead, _ = make(factory=boom)
    result = await dead.probe()
    assert result.ok is False and result.status == "dead"
    unset, _ = make(fields={}, store_values=NO_EMAIL_VALUES)
    assert (await unset.probe()).ok is False


def test_default_factory_builds_without_network():
    from universal_connector.upstreams.google_direct import _default_factory

    fields = {"client_id": "fake-cid", "client_secret": "fake-csecret", "refresh_token": "fake-r"}
    assert _default_factory("gmail", "v1", fields).users() is not None
    assert _default_factory("calendar", "v3", fields).events() is not None


async def test_nothing_reachable_after_expiry():
    clock = Clock()
    up, _ = make(clock=clock)
    await up.call_tool("gmail_search", {"query": "q"})
    assert reaches_text(up, REFRESH, skip=[up.test_store])  # the walk can see a live hold
    clock.now += 900
    assert up.purge() >= 1
    assert not reaches_text(up, REFRESH, skip=[up.test_store])


async def test_cancel_passes_through():
    def slow_factory(api, version, creds):
        time.sleep(0.5)
        return FakeService()

    up, _ = make(factory=slow_factory)
    task = asyncio.ensure_future(up.call_tool("gmail_search", {"query": "q"}))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancel_during_data_call_passes_through():
    up, fake = make()
    await up.call_tool("gmail_search", {"query": "warm"})  # login done, service held
    fake.enter = lambda: time.sleep(0.4)  # the next data call blocks in its worker thread
    task = asyncio.ensure_future(up.call_tool("gmail_search", {"query": "q"}))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


UPSTREAM_TEXT = "MARKER-not-a-key from ghost@example.invalid"


def _assert_no_upstream_text(exc: BaseException) -> None:
    for text in (str(exc), repr(exc), repr(exc.args)):
        assert "MARKER-not-a-key" not in text and "ghost@example.invalid" not in text


async def test_error_text_keeps_no_upstream_text():
    def broken_factory(api, version, creds):
        raise RuntimeError(UPSTREAM_TEXT)

    up, _ = make(factory=broken_factory)
    with pytest.raises(UpstreamError) as err:
        await up.call_tool("gmail_search", {"query": "q"})
    _assert_no_upstream_text(err.value)
    result = await up.probe()
    assert result.ok is False
    assert "MARKER-not-a-key" not in result.detail and "ghost@example.invalid" not in result.detail
    # A failure inside a data call, after login, with and without an HTTP status.
    for failure, expected in (
        (RuntimeError(UPSTREAM_TEXT), UpstreamError),
        (HttpErr(500, UPSTREAM_TEXT), UpstreamError),
        (HttpErr(401, UPSTREAM_TEXT), UpstreamAuthError),
    ):
        fake = FakeService()
        fake.fail = failure
        up, _ = make(fake=fake)
        with pytest.raises(expected) as err:
            await up.call_tool("gmail_search", {"query": "q"})
        _assert_no_upstream_text(err.value)
