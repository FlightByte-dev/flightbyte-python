"""A local fake of the API, fixtures, and a check that JSON fits a TypedDict."""

from __future__ import annotations

import json
import threading
import types
import typing
import unittest
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from flightbyte import FlightByte

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent


def fixture_text(name: str) -> str:
    """A fixture file's text, exactly as stored."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture(name: str) -> Any:
    """A fixture file, decoded."""
    return json.loads(fixture_text(name))


@dataclass
class Recorded:
    """One request the fake API received."""

    method: str
    path: str
    query: dict[str, str]
    raw_query: str
    headers: dict[str, str]
    body: bytes | None

    def json(self) -> Any:
        assert self.body is not None, "the request had no body"
        return json.loads(self.body)


@dataclass
class Reply:
    """What the fake API answers."""

    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


def json_reply(status: int, body: Any, headers: dict[str, str] | None = None) -> Reply:
    """A JSON answer; a str body is sent as it is."""
    raw = body if isinstance(body, str) else json.dumps(body)
    return Reply(
        status,
        b"" if status == 204 else raw.encode("utf-8"),
        {"content-type": "application/json", **(headers or {})},
    )


class MockAPI:
    """A real HTTP server on 127.0.0.1 that records every request and answers with ``reply``.

    ``raw``, when given, answers instead, writing to the request handler
    itself: for answers too broken or too slow for ``reply`` to describe.
    """

    def __init__(
        self,
        reply: Callable[[Recorded], Reply] | None = None,
        raw: Callable[[Recorded, BaseHTTPRequestHandler], None] | None = None,
    ) -> None:
        self.calls: list[Recorded] = []
        self.reply = reply or (lambda request: json_reply(200, {}))
        self.raw = raw
        self._lock = threading.Lock()
        api = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _handle(self) -> None:
                parts = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(length) if length else None
                recorded = Recorded(
                    method=self.command,
                    path=parts.path,
                    query=dict(urllib.parse.parse_qsl(parts.query)),
                    raw_query=parts.query,
                    headers={k.lower(): v for k, v in self.headers.items()},
                    body=body,
                )
                with api._lock:
                    api.calls.append(recorded)
                if api.raw is not None:
                    api.raw(recorded, self)
                    self.close_connection = True
                    return
                try:
                    reply = api.reply(recorded)
                except Exception as error:
                    reply = Reply(599, f"the test's reply function failed: {error!r}".encode())
                self.send_response(reply.status)
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                self.send_header("content-length", str(len(reply.body)))
                self.send_header("connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(reply.body)
                self.close_connection = True

            do_GET = do_POST = do_PATCH = do_DELETE = do_HEAD = do_PUT = _handle

            def log_message(self, format: str, *args: Any) -> None:
                pass

        class _Server(ThreadingHTTPServer):
            daemon_threads = True
            block_on_close = False

            def handle_error(self, request: Any, client_address: Any) -> None:
                pass  # a client that hung up on purpose, in the timeout tests

        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, args=(0.01,), daemon=True
        )
        self._thread.start()

    @property
    def url(self) -> str:
        port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}"

    def client(self, **options: Any) -> FlightByte:
        """A client pointed at this server's ``/v1``."""
        options.setdefault("api_key", "frk_test_key")
        options.setdefault("base_url", f"{self.url}/v1")
        return FlightByte(**options)

    def last(self) -> Recorded:
        with self._lock:
            assert self.calls, "no request was sent"
            return self.calls[-1]

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class APITestCase(unittest.TestCase):
    """A test case that can start fake APIs and stops them afterwards."""

    def start(
        self,
        reply: Callable[[Recorded], Reply] | None = None,
        raw: Callable[[Recorded, BaseHTTPRequestHandler], None] | None = None,
    ) -> MockAPI:
        api = MockAPI(reply, raw)
        self.addCleanup(api.close)
        return api


def check_shape(value: Any, expected: Any, where: str = "$") -> list[str]:
    """Every way ``value``, decoded JSON, does not fit the type ``expected``.

    TypedDicts are checked strictly: a required key that is missing and a key
    the type does not list are both reported, so a fixture shaped like the
    API's JSON keeps the models honest.
    """
    if expected is Any:
        return []
    if typing.is_typeddict(expected):
        if not isinstance(value, dict):
            return [f"{where}: expected an object for {expected.__name__}, got {value!r}"]
        hints = typing.get_type_hints(expected)
        problems = [
            f"{where}: {expected.__name__} lacks the required key {key!r}"
            for key in sorted(expected.__required_keys__)
            if key not in value
        ]
        for key, item in value.items():
            if key not in hints:
                problems.append(f"{where}: {expected.__name__} has no key {key!r}")
            else:
                problems += check_shape(item, hints[key], f"{where}.{key}")
        return problems
    origin = typing.get_origin(expected)
    if origin in (typing.Union, types.UnionType):
        options = typing.get_args(expected)
        if any(not check_shape(value, option, where) for option in options):
            return []
        return [f"{where}: {value!r} fits none of {options}"]
    if origin is list:
        if not isinstance(value, list):
            return [f"{where}: expected a list, got {value!r}"]
        (item_type,) = typing.get_args(expected)
        return [
            p for i, item in enumerate(value) for p in check_shape(item, item_type, f"{where}[{i}]")
        ]
    if origin is dict:
        if not isinstance(value, dict):
            return [f"{where}: expected an object, got {value!r}"]
        _key_type, value_type = typing.get_args(expected)
        return [
            p for k, item in value.items() for p in check_shape(item, value_type, f"{where}.{k}")
        ]
    if expected is type(None):
        return [] if value is None else [f"{where}: expected null, got {value!r}"]
    if expected is bool:
        return [] if isinstance(value, bool) else [f"{where}: expected a boolean, got {value!r}"]
    if expected in (int, float):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected is int:
            ok = ok and isinstance(value, int)
        return [] if ok else [f"{where}: expected {expected.__name__}, got {value!r}"]
    if expected is str:
        return [] if isinstance(value, str) else [f"{where}: expected a string, got {value!r}"]
    return [f"{where}: the check does not know the type {expected!r}"]
