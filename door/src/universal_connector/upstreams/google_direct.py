"""Google Calendar and Gmail, read plus draft only. This module has no function that delivers mail."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Callable
from typing import Any

from universal_connector.models import Connection
from universal_connector.upstreams.base import (
    DEFAULT_TTL_S,
    HoldBook,
    ProbeResult,
    ToolInfo,
    UpstreamAuthError,
    UpstreamError,
    clean_error,
    scrub,
)
from universal_connector.vault import SecretStore, SecretUnavailable

CALENDAR_CAP = 50
SEARCH_CAP = 25
BODY_CAP = 20_000
_KIND = "google"
_DEFAULT_FIELDS = ("client_id", "client_secret", "refresh_token")
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SCOPES = {
    "calendar": ["https://www.googleapis.com/auth/calendar.readonly"],
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
    ],
}
_API_VERSION = {"calendar": "v3", "gmail": "v1"}
# What a calendar list result keeps. Google's paging and sync cursors stay out: no tool takes one,
# and the scanner reads a cursor as an assigned secret.
_EVENT_LIST_KEYS = ("timeZone", "items")


def _schema(props: dict[str, dict], required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


_TOOLS: dict[str, ToolInfo] = {
    "calendar_list_events": ToolInfo(
        "calendar_list_events",
        "List calendar events between two times (ISO 8601). At most 50.",
        _schema(
            {
                "time_min": {"type": "string"},
                "time_max": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            ["time_min", "time_max"],
        ),
    ),
    "calendar_get_event": ToolInfo(
        "calendar_get_event",
        "Get one calendar event.",
        _schema({"event_id": {"type": "string"}}, ["event_id"]),
    ),
    "gmail_search": ToolInfo(
        "gmail_search",
        "Search mail. Returns id, thread id, from, subject, date and snippet. At most 25.",
        _schema({"query": {"type": "string"}, "max_results": {"type": "integer"}}, ["query"]),
    ),
    "gmail_get_message": ToolInfo(
        "gmail_get_message",
        "Get one message: headers and a plain-text body.",
        _schema({"message_id": {"type": "string"}}, ["message_id"]),
    ),
    "gmail_create_draft": ToolInfo(
        "gmail_create_draft",
        "Create a draft. Returns the draft id.",
        _schema(
            {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
            ["to", "subject", "body"],
        ),
    ),
}


def _status(exc: BaseException) -> int | None:
    resp = getattr(exc, "resp", None)
    code = getattr(resp, "status", None)
    return code if isinstance(code, int) else None


def _default_factory(api: str, version: str, fields: dict[str, str]) -> Any:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        None,
        refresh_token=fields["refresh_token"],
        client_id=fields["client_id"],
        client_secret=fields["client_secret"],
        token_uri=_TOKEN_URI,
        scopes=_SCOPES[api],
    )
    return build(api, version, credentials=creds, cache_discovery=False, static_discovery=True)


def _headers(payload: dict) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def _plain_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        raw = payload["body"]["data"]
        return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _plain_body(part)
        if text:
            return text
    return ""


def _map_error(exc: BaseException, conn_name: str) -> Exception:
    """Return the error to raise. Never carries the original text or arguments."""
    status = _status(exc)
    if status in (401, 403):
        return UpstreamAuthError(f"google refused the login: {conn_name}")
    if status is not None:
        return UpstreamError(f"google call failed (status {status})")
    return UpstreamError(f"{_KIND}: {type(exc).__name__}")


class GoogleUpstream:
    def __init__(
        self,
        conn: Connection,
        store: SecretStore,
        service_factory: Callable[[str, str, dict[str, str]], Any] | None = None,
        expected_address: str | None = None,
        clock: Callable[[], float] = time.monotonic,
        ttl_s: int = DEFAULT_TTL_S,
    ) -> None:
        self._expected_address = expected_address
        self.conn = conn
        self.store = store
        self._factory = service_factory or _default_factory
        self._lock = asyncio.Lock()
        self._holds = HoldBook(clock, ttl_s)

    def secret_values(self) -> list[str]:
        self._holds.drop_expired()
        return self._holds.values()

    def purge(self) -> int:
        return self._holds.drop_expired()

    # -- login -------------------------------------------------------------------------------

    def _read_fields(self, used: list[str]) -> tuple[dict[str, str], str]:
        auth = self.conn.auth
        mapping = {k: auth.fields.get(k, k) for k in _DEFAULT_FIELDS}
        entries = {
            "client_id": auth.secret,
            "client_secret": auth.secret,
            "refresh_token": auth.token_secret or auth.secret,
        }
        values: dict[str, str] = {}
        missing = False
        for key in _DEFAULT_FIELDS:
            entry = entries[key]
            if not entry:
                missing = True
                break
            # A missing entry raises SecretUnavailable and passes up.
            used.append(self.store.get(entry))
            try:
                values[key] = self.store.field(entry, mapping[key])
            except SecretUnavailable:
                missing = True
            if missing:
                break
            used.append(values[key])
        self._holds.put("login", None, list(values.values()))
        if missing:
            raise UpstreamAuthError("needs-login")
        return values, self._expected_email(used)

    def _expected_email(self, used: list[str]) -> str:
        auth = self.conn.auth
        if "email" in auth.fields:
            entry = auth.token_secret or auth.secret
            value = ""
            if entry:
                used.append(self.store.get(entry))
                try:
                    value = self.store.field(entry, auth.fields["email"])
                except SecretUnavailable:
                    value = ""
            if not value:
                raise UpstreamAuthError("account-not-set")
            return value
        if self._expected_address:
            return self._expected_address
        raise UpstreamAuthError("account-not-set")

    def _signed_in(self, api: str, service: Any) -> str:
        if api == "gmail":
            return service.users().getProfile(userId="me").execute()["emailAddress"]
        return service.calendars().get(calendarId="primary").execute()["id"]

    async def _build(self, api: str, used: list[str]) -> Any:
        """Return the held service, or log in and check the mailbox. The lock is held.

        `used` collects every value this call reads or uses, for the scrub at the end.
        """
        held = self._holds.held(f"service:{api}")
        if held is not None:
            service, values = held
            used.extend(values)
            return service
        fields, expected = await asyncio.to_thread(self._read_fields, used)
        error: Exception | None = None
        service: Any = None
        actual = ""
        try:
            service = await asyncio.to_thread(self._factory, api, _API_VERSION[api], fields)
            actual = str(await asyncio.to_thread(self._signed_in, api, service))
        except Exception as exc:  # noqa: BLE001 - mapped, no original text kept
            error = _map_error(exc, self.conn.name)
        if error is not None:
            raise error
        if actual.strip().lower() != expected.strip().lower():
            raise UpstreamAuthError("wrong-account")
        self._holds.put(f"service:{api}", service, list(fields.values()))
        return service

    async def _call(self, api: str, fn: Callable[[Any], Any], used: list[str]) -> Any:
        async with self._lock:
            self._holds.drop_expired()
            service = await self._build(api, used)
            error: Exception | None = None
            result: Any = None
            try:
                result = await asyncio.to_thread(fn, service)
            except Exception as exc:  # noqa: BLE001 - mapped, no original text kept
                error = _map_error(exc, self.conn.name)
            if error is not None:
                raise error
            return result

    # -- Upstream protocol --------------------------------------------------------------------

    async def list_tools(self) -> list[ToolInfo]:
        self._holds.drop_expired()
        return list(_TOOLS.values())

    async def probe(self) -> ProbeResult:
        api = "gmail" if any(t.name.startswith("gmail_") for t in self.conn.tools) else "calendar"
        used: list[str] = []
        status: str | None = None
        detail = ""
        try:
            async with self._lock:
                self._holds.drop_expired()
                await self._build(api, used)
        except SecretUnavailable:
            status, detail = "not-in-vault", "vault entry not available"
        except UpstreamAuthError as exc:
            status, detail = "needs-login", str(exc)
        except UpstreamError as exc:
            status, detail = "dead", str(exc)
        except Exception as exc:  # noqa: BLE001
            status, detail = "dead", f"{_KIND}: {type(exc).__name__}"
        if status is not None:
            return ProbeResult(False, status, scrub(detail, used + self._holds.values()))
        return ProbeResult(True, "ok", "signed in")

    async def call_tool(self, name: str, arguments: dict) -> str:
        self._holds.drop_expired()
        handler = getattr(self, f"_tool_{name}", None)
        used: list[str] = []
        error: Exception | None = None
        text = ""
        try:
            if name not in _TOOLS or handler is None:
                raise UpstreamError(f"unknown tool: {name}")
            text = json.dumps(await handler(used, **arguments), ensure_ascii=False)
        except SecretUnavailable:
            raise
        except (UpstreamAuthError, UpstreamError) as exc:
            error = clean_error(exc, used + self._holds.values())
        except Exception as exc:  # noqa: BLE001 - mapped, no original text kept
            error = _map_error(exc, self.conn.name)
        if error is not None:
            raise error
        # Scrub with the values this call used, not only the holds left now: a hold can drop
        # (purge, ttl) while the call is in flight, and its value must still be scrubbed.
        return scrub(text, used + self._holds.values())

    # -- tools --------------------------------------------------------------------------------

    # Each tool takes `used` first and hands it to `_call`, so call_tool can scrub with it.

    async def _tool_calendar_list_events(
        self, used: list[str], time_min: str, time_max: str, max_results: int = 20
    ) -> Any:
        limit = max(1, min(int(max_results), CALENDAR_CAP))
        listed = await self._call(
            "calendar",
            lambda s: s.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=limit,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute(),
            used,
        )
        return {k: listed[k] for k in _EVENT_LIST_KEYS if k in listed}

    async def _tool_calendar_get_event(self, used: list[str], event_id: str) -> Any:
        return await self._call(
            "calendar",
            lambda s: s.events().get(calendarId="primary", eventId=event_id).execute(),
            used,
        )

    async def _tool_gmail_search(self, used: list[str], query: str, max_results: int = 10) -> Any:
        limit = max(1, min(int(max_results), SEARCH_CAP))

        def run(s: Any) -> list[dict]:
            listed = s.users().messages().list(userId="me", q=query, maxResults=limit).execute()
            out = []
            for ref in listed.get("messages", [])[:limit]:
                msg = (
                    s.users()
                    .messages()
                    .get(
                        userId="me",
                        id=ref["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    )
                    .execute()
                )
                h = _headers(msg.get("payload", {}))
                out.append(
                    {
                        "id": msg["id"],
                        "thread_id": msg.get("threadId"),
                        "from": h.get("from", ""),
                        "subject": h.get("subject", ""),
                        "date": h.get("date", ""),
                        "snippet": msg.get("snippet", ""),
                    }
                )
            return out

        return await self._call("gmail", run, used)

    async def _tool_gmail_get_message(self, used: list[str], message_id: str) -> Any:
        def run(s: Any) -> dict:
            msg = s.users().messages().get(userId="me", id=message_id, format="full").execute()
            payload = msg.get("payload", {})
            h = _headers(payload)
            return {
                "id": msg.get("id"),
                "thread_id": msg.get("threadId"),
                "headers": {k: h.get(k, "") for k in ("from", "to", "cc", "subject", "date")},
                "body": _plain_body(payload)[:BODY_CAP],
            }

        return await self._call("gmail", run, used)

    async def _tool_gmail_create_draft(
        self, used: list[str], to: str, subject: str, body: str
    ) -> Any:
        from email.message import EmailMessage

        def run(s: Any) -> dict:
            mime = EmailMessage()
            mime["To"] = to
            mime["Subject"] = subject
            mime.set_content(body)
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
            made = s.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
            return {"draft_id": made["id"]}

        return await self._call("gmail", run, used)
