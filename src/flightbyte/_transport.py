"""Sends authenticated requests: headers, timeouts, redirects and error mapping."""

from __future__ import annotations

import contextlib
import functools
import http.client
import json
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any, Final, TypeAlias, cast

from ._errors import APIConnectionError, APIError, FlightByteError
from ._rate_limit import RateLimit, parse_rate_limit

QueryValue: TypeAlias = str | int | float | bool | None
"""A query string value; ``None`` and ``''`` are left out."""

MAX_REDIRECTS: Final = 5
"""How many same-origin redirects a GET or HEAD follows."""

_DEFAULT_PORTS: Final = {"http": 80, "https": 443}
_FOLLOWABLE_METHODS: Final = frozenset({"GET", "HEAD"})
_UNSAFE_URL_CHARACTERS: Final = re.compile(r"[\x00-\x20\x7f]")
_HEADER_VALUE: Final = re.compile(r"[^\x00-\x08\x0a-\x1f\x7f]*")


class NotGiven:
    """The type of ``NOT_GIVEN``: a per-call option that was left out."""

    _instance: NotGiven | None = None

    def __new__(cls) -> NotGiven:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN: Final = NotGiven()
"""Leaves a per-call ``timeout`` to the client's own."""


def check_timeout(name: str, value: object) -> float | None:
    """Validates a timeout in seconds; ``None`` and ``0`` turn it off."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"flightbyte: {name} must be a number of seconds or None.")
    if value != value or value < 0 or value == float("inf"):
        raise ValueError(f"flightbyte: {name} must be a number of seconds, 0 or more, or None.")
    return float(value) if value > 0 else None


def check_header_value(name: str, value: str) -> str:
    """Rejects line breaks and other control characters, so a value cannot add a header."""
    if not _HEADER_VALUE.fullmatch(value):
        raise ValueError(f"flightbyte: {name} must not contain line breaks or control characters.")
    return value


def required(name: str, value: object) -> str:
    """Rejects an empty path parameter before it turns into a request for the wrong URL."""
    if not isinstance(value, str):
        raise TypeError(f"flightbyte: {name} is required and must be a string.")
    if not value.strip():
        raise ValueError(f"flightbyte: {name} is required.")
    return value


class Transport:
    """Sends authenticated requests and turns error statuses into errors.

    Reach the API through ``FlightByte``. One transport is shared by every
    thread using the client: it keeps no connection between requests, and
    the only state it changes, the latest quota, is guarded by a lock.
    """

    def __init__(
        self, *, api_key: str, base_url: str, timeout: float | None, user_agent: str
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._api_key = api_key
        self._user_agent = user_agent
        self._opener = _build_opener()
        self._lock = threading.Lock()
        self._last_rate_limit: RateLimit | None = None

    @property
    def last_rate_limit(self) -> RateLimit | None:
        """The quota state from the latest response that carried one."""
        with self._lock:
            return self._last_rate_limit

    def url(self, path: Sequence[str], query: Mapping[str, QueryValue] | None = None) -> str:
        """Builds the URL for ``path`` under the base URL, each segment escaped."""
        url = self.base_url + "".join("/" + _escape_segment(segment) for segment in path)
        params = [
            (key, _query_string(value))
            for key, value in (query or {}).items()
            if value is not None and value != ""
        ]
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def send(
        self,
        method: str,
        path: Sequence[str],
        *,
        query: Mapping[str, QueryValue] | None = None,
        body: object = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> Any:
        """Sends a request and returns the decoded JSON, or ``None`` for an empty body."""
        seconds = (
            self.timeout if isinstance(timeout, NotGiven) else check_timeout("timeout", timeout)
        )
        request_headers = {
            "x-api-key": self._api_key,
            "accept": "application/json",
            "user-agent": self._user_agent,
        }
        for name, value in (headers or {}).items():
            request_headers[name.lower()] = check_header_value(name, value)
        data: bytes | None = None
        if body is not None:
            request_headers["content-type"] = "application/json"
            data = json.dumps(body, separators=(",", ":"), allow_nan=False).encode("ascii")

        initial_url = self.url(path, query)
        url = initial_url
        deadline = _Deadline(seconds)
        try:
            hops = 0
            while True:
                follow = hops < MAX_REDIRECTS
                status, reason, response_headers, raw = self._exchange(
                    method, url, request_headers, data, deadline, follow=follow
                )
                target = redirect_target(status, response_headers, url, method)
                if target is None or not follow:
                    break
                url = target
                hops += 1
        except (OSError, http.client.HTTPException) as error:
            if seconds is not None and (deadline.finish() or _is_timeout(error)):
                raise _timed_out(method, initial_url, seconds) from error
            raise APIConnectionError(
                f"{method} {initial_url} failed: {_describe(error)}"
            ) from error
        finally:
            deadline.finish()
        if seconds is not None and deadline.expired:
            # The body was cut off when the time ran out, and a body without a
            # length can look complete. What arrived is not trusted.
            raise _timed_out(method, initial_url, seconds)

        rate_limit = parse_rate_limit(response_headers)
        if rate_limit is not None:
            with self._lock:
                self._last_rate_limit = rate_limit

        text = raw.decode("utf-8", "replace")
        if status < 200 or status > 299:
            raise APIError.from_response(status, reason, text, response_headers)
        if status == 204 or not text.strip():
            return None
        try:
            return json.loads(text)
        except ValueError as error:
            preview = text[:200] + "..." if len(text) > 200 else text
            raise FlightByteError(
                f"Expected JSON from {method} {initial_url}, got: {preview}"
            ) from error

    def _exchange(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        data: bytes | None,
        deadline: _Deadline,
        *,
        follow: bool,
    ) -> tuple[int, str, dict[str, str], bytes]:
        """One request and its whole response; nothing is followed here."""
        request = _Request(url, data=data, headers=dict(headers), method=method, deadline=deadline)
        remaining = deadline.remaining()
        if remaining is None:
            opened = self._opener.open(request)
        else:
            opened = self._opener.open(request, timeout=remaining)
        response = cast(http.client.HTTPResponse, opened)
        with response:
            response_headers = _lower_headers(response.headers)
            if follow and redirect_target(response.status, response_headers, url, method):
                # Followed next; its body is of no use.
                return response.status, response.reason, response_headers, b""
            return response.status, response.reason, response_headers, response.read()


def redirect_target(
    status: int, headers: Mapping[str, str], current: str, method: str
) -> str | None:
    """Where to go next when the response is a redirect this client may follow.

    Only a GET or HEAD is followed, and only to the same origin (scheme, host
    and port). Anything else is handed to the caller as an error, so the API
    key, sent on every request, never reaches another server or travels in
    the clear, and a write is never sent twice.
    """
    if status < 300 or status > 399 or method.upper() not in _FOLLOWABLE_METHODS:
        return None
    location = headers.get("location", "").strip()
    if not location or _UNSAFE_URL_CHARACTERS.search(location):
        return None
    try:
        target, _fragment = urllib.parse.urldefrag(urllib.parse.urljoin(current, location))
        if _origin(target) != _origin(current):
            return None
    except ValueError:
        return None
    return target


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    return scheme, (parts.hostname or "").lower(), parts.port or _DEFAULT_PORTS.get(scheme)


def _escape_segment(segment: str) -> str:
    escaped = urllib.parse.quote(segment, safe="")
    # "." and ".." would be read as "this" and "parent" directory on the way.
    return escaped.replace(".", "%2E") if escaped in (".", "..") else escaped


def _query_string(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _lower_headers(message: http.client.HTTPMessage) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in message.items():
        key = name.lower()
        headers[key] = f"{headers[key]}, {value}" if key in headers else value
    return headers


def _timed_out(method: str, url: str, seconds: float) -> APIConnectionError:
    return APIConnectionError(f"{method} {url} timed out after {seconds:g} s.", timed_out=True)


def _is_timeout(error: BaseException) -> bool:
    if isinstance(error, urllib.error.URLError) and isinstance(error.reason, BaseException):
        return _is_timeout(error.reason)
    return isinstance(error, TimeoutError)


def _describe(error: BaseException) -> str:
    if isinstance(error, urllib.error.URLError):
        return (
            _describe(error.reason)
            if isinstance(error.reason, BaseException)
            else str(error.reason)
        )
    return str(error) or type(error).__name__


class _Deadline:
    """Bounds a whole request, body included, across every redirect hop.

    The socket timeout alone bounds each read, not their sum: a server that
    trickles a byte at a time could hold a request open for ever. So a timer
    shuts the socket down when the time is up, which ends whatever read is
    waiting on it. Name resolution is left to the system resolver's own limits.
    """

    def __init__(self, seconds: float | None) -> None:
        self._lock = threading.Lock()
        self._socket: socket.socket | None = None
        self._expired = False
        self._finished = False
        self._end: float | None = None
        self._timer: threading.Timer | None = None
        if seconds is not None:
            self._end = time.monotonic() + seconds
            self._timer = threading.Timer(seconds, self._expire)
            self._timer.daemon = True
            self._timer.start()

    @property
    def expired(self) -> bool:
        """Whether the time ran out before the request finished."""
        return self._expired

    def remaining(self) -> float | None:
        """Seconds left, or ``None`` without a timeout. Raises ``TimeoutError`` once none are."""
        if self._end is None:
            return None
        left = self._end - time.monotonic()
        if left <= 0 or self._expired:
            raise TimeoutError("the request ran out of time")
        return left

    def attach(self, sock: socket.socket) -> None:
        """Watches the socket of the current hop."""
        with self._lock:
            self._socket = sock
            if self._expired:
                _shut_down(sock)

    def finish(self) -> bool:
        """Stops the timer and says whether the time ran out first."""
        with self._lock:
            self._finished = True
            self._socket = None
            if self._timer is not None:
                self._timer.cancel()
            return self._expired

    def _expire(self) -> None:
        with self._lock:
            if self._finished:
                return
            self._expired = True
            if self._socket is not None:
                _shut_down(self._socket)


def _shut_down(sock: socket.socket) -> None:
    # socket.socket.shutdown, also for a TLS socket: it ends a read waiting in
    # another thread without touching the TLS state that thread is using.
    with contextlib.suppress(OSError):
        socket.socket.shutdown(sock, socket.SHUT_RDWR)


class _Request(urllib.request.Request):
    """A request that carries its deadline to the connection that sends it."""

    def __init__(
        self,
        url: str,
        *,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        deadline: _Deadline,
    ) -> None:
        super().__init__(url, data=data, headers=headers, method=method)
        self.deadline = deadline


def _deadline_of(request: urllib.request.Request) -> _Deadline:
    deadline = getattr(request, "deadline", None)
    return deadline if isinstance(deadline, _Deadline) else _Deadline(None)


class _HTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args: Any, deadline: _Deadline, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._deadline = deadline

    def connect(self) -> None:
        super().connect()
        self._deadline.attach(self.sock)


class _HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args: Any, deadline: _Deadline, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._deadline = deadline

    def connect(self) -> None:
        super().connect()
        self._deadline.attach(self.sock)


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(functools.partial(_HTTPConnection, deadline=_deadline_of(req)), req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self) -> None:
        context = ssl.create_default_context()
        super().__init__(context=context)
        self._tls_context = context

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(
            functools.partial(_HTTPSConnection, deadline=_deadline_of(req)),
            req,
            context=self._tls_context,
        )


def _build_opener() -> urllib.request.OpenerDirector:
    # Built by hand rather than with build_opener(): without a redirect
    # handler nothing is followed behind this module's back, and without an
    # error processor every status comes back as a response. Proxies set in
    # the environment (HTTPS_PROXY, NO_PROXY, ...) are honoured, as by urllib.
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.ProxyHandler(),
        urllib.request.UnknownHandler(),
        _HTTPHandler(),
        _HTTPSHandler(),
    ):
        opener.add_handler(handler)
    return opener
