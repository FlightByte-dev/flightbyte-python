import dataclasses
import socket
import threading
import time
import unittest
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from flightbyte import (
    APIConnectionError,
    FlightByte,
    FlightByteError,
    RateLimit,
    RateLimitWindow,
    __version__,
)

from .helpers import APITestCase, Recorded, Reply, json_reply


class ConstructorTest(unittest.TestCase):
    def test_rejects_bad_options(self) -> None:
        cases: list[tuple[str, dict[str, Any], type[Exception]]] = [
            ("no key", {"api_key": None}, TypeError),
            ("an empty key", {"api_key": ""}, ValueError),
            ("a blank key", {"api_key": "   "}, ValueError),
            ("a key with a line break", {"api_key": "k\r\nx-evil: 1"}, ValueError),
            ("a relative base URL", {"api_key": "k", "base_url": "/v1"}, ValueError),
            (
                "an ftp base URL",
                {"api_key": "k", "base_url": "ftp://api.flightbyte.dev/v1"},
                ValueError,
            ),
            ("a base URL without a host", {"api_key": "k", "base_url": "https:///v1"}, ValueError),
            (
                "a base URL with a query",
                {"api_key": "k", "base_url": "https://a.test/v1?x=1"},
                ValueError,
            ),
            (
                "a base URL with a fragment",
                {"api_key": "k", "base_url": "https://a.test/v1#x"},
                ValueError,
            ),
            (
                "a base URL with a bad port",
                {"api_key": "k", "base_url": "https://a.test:99999/v1"},
                ValueError,
            ),
            ("a negative timeout", {"api_key": "k", "timeout": -1}, ValueError),
            (
                "a timeout that is not a number",
                {"api_key": "k", "timeout": float("nan")},
                ValueError,
            ),
            ("an endless timeout", {"api_key": "k", "timeout": float("inf")}, ValueError),
            ("a timeout that is a string", {"api_key": "k", "timeout": "30"}, TypeError),
            ("a user agent with a line break", {"api_key": "k", "user_agent": "a\nb"}, ValueError),
        ]
        for name, options, error in cases:
            with self.subTest(name), self.assertRaises(error):
                FlightByte(**options)

    def test_defaults_to_the_production_api_and_trims_what_it_is_given(self) -> None:
        self.assertEqual(FlightByte("k").base_url, "https://api.flightbyte.dev/v1")
        self.assertEqual(FlightByte("k", base_url=None).base_url, FlightByte.DEFAULT_BASE_URL)
        trimmed = FlightByte("k", base_url=" http://localhost:3000/v1/ ")
        self.assertEqual(trimmed.base_url, "http://localhost:3000/v1")
        self.assertEqual(FlightByte("k").timeout, 30.0)
        self.assertIsNone(FlightByte("k", timeout=None).timeout)
        self.assertIsNone(FlightByte("k", timeout=0).timeout)

    def test_repr_leaves_the_key_out(self) -> None:
        client = FlightByte("frk_live_secret")
        self.assertNotIn("frk_live_secret", repr(client))
        self.assertNotIn("frk_live_secret", str(vars(client)))


class RequestTest(APITestCase):
    def test_sends_the_key_accept_and_user_agent(self) -> None:
        api = self.start(lambda request: json_reply(200, {"count": 0, "data": []}))
        api.client(api_key="  frk_test_key  ", user_agent="my-app/1.2").countries.list()
        sent = api.last()
        self.assertEqual(sent.method, "GET")
        self.assertEqual(sent.path, "/v1/countries")
        self.assertEqual(sent.raw_query, "")
        self.assertEqual(sent.headers["x-api-key"], "frk_test_key")
        self.assertEqual(sent.headers["accept"], "application/json")
        self.assertEqual(sent.headers["user-agent"], f"my-app/1.2 flightbyte-python/{__version__}")
        self.assertNotIn("content-type", sent.headers)
        self.assertIsNone(sent.body)

    def test_own_user_agent_alone(self) -> None:
        api = self.start(lambda request: json_reply(200, {"count": 0, "data": []}))
        api.client(user_agent="  ").countries.list()
        self.assertEqual(api.last().headers["user-agent"], "flightbyte-python/1.0.0")

    def test_escapes_every_path_segment(self) -> None:
        api = self.start()
        client = api.client()
        client.subscriptions.get("sub/../../admin?x=1")
        self.assertEqual(api.last().path, "/v1/subscriptions/sub%2F..%2F..%2Fadmin%3Fx%3D1")
        self.assertEqual(api.last().raw_query, "")
        client.subscriptions.get("..")
        self.assertEqual(api.last().path, "/v1/subscriptions/%2E%2E")
        client.flights.get("T K", "18 48", "2026-09-08")
        self.assertEqual(api.last().path, "/v1/flights/T%20K/18%2048/2026-09-08")

    def test_rejects_an_empty_path_parameter_without_sending_anything(self) -> None:
        api = self.start()
        client = api.client()
        calls: list[tuple[str, Callable[[], object]]] = [
            ("carrier", lambda: client.flights.get("", "1", "2026-09-08")),
            ("flight_number", lambda: client.flights.get("TK", " ", "2026-09-08")),
            ("date", lambda: client.flights.timeline("TK", "1", " ")),
            ("webhook_url", lambda: client.subscriptions.create("TK", "1", "2026-09-08", "")),
            ("id", lambda: client.subscriptions.get("")),
            ("id", lambda: client.subscriptions.delete(" ")),
            ("id", lambda: client.subscriptions.deliveries("")),
            ("code", lambda: client.countries.get("")),
            ("code", lambda: client.countries.flag_url("")),
        ]
        for name, call in calls:
            with self.subTest(name), self.assertRaisesRegex(ValueError, f"{name} is required"):
                call()
        with self.assertRaises(TypeError):
            client.subscriptions.get(None)  # type: ignore[arg-type]
        self.assertEqual(api.calls, [])

    def test_rejects_a_line_break_in_the_idempotency_key(self) -> None:
        api = self.start()
        with self.assertRaises(ValueError):
            api.client().subscriptions.create(
                "TK", "1", "2026-09-08", "https://e.test/h", idempotency_key="a\r\nb: c"
            )
        self.assertEqual(api.calls, [])

    def test_treats_an_empty_2xx_body_as_no_value(self) -> None:
        api = self.start(lambda request: Reply(201))
        api.client().subscriptions.delete("sub_1")
        self.assertEqual(api.last().method, "DELETE")
        api.reply = lambda request: Reply(200, b"  \n")
        api.client().subscriptions.delete("sub_1")

    def test_says_so_when_a_2xx_body_is_not_json(self) -> None:
        api = self.start(lambda request: Reply(200, b"<html>maintenance</html>"))
        with self.assertRaises(FlightByteError) as caught:
            api.client().countries.list()
        self.assertRegex(
            str(caught.exception),
            rf"^Expected JSON from GET {api.url}/v1/countries, got: <html>maintenance</html>$",
        )
        api.reply = lambda request: Reply(200, b"x" * 300)
        with self.assertRaisesRegex(FlightByteError, r"got: x{200}\.\.\.$"):
            api.client().countries.list()

    def test_says_so_when_a_list_answer_has_no_data(self) -> None:
        api = self.start(lambda request: json_reply(200, {"count": 0}))
        with self.assertRaisesRegex(FlightByteError, "Expected a data list from GET /countries"):
            api.client().countries.list()


class RateLimitTest(APITestCase):
    QUOTA = {  # noqa: RUF012
        "x-ratelimit-limit-minute": "60",
        "x-ratelimit-remaining-minute": "59",
        "x-ratelimit-reset-minute": "1788858660",
        "x-ratelimit-limit-month": "120",
        "x-ratelimit-remaining-month": "bad",
        "x-ratelimit-limit-day": "1" + chr(0xB2),  # str.isdigit() says yes; the API means no
        "x-ratelimit-remaining-day": "1",
    }

    def expected_minute(self) -> RateLimitWindow:
        return RateLimitWindow(
            limit=60,
            remaining=59,
            reset_at=datetime.fromtimestamp(1788858660, tz=timezone.utc),
        )

    def test_reads_the_windows_the_headers_report(self) -> None:
        api = self.start(lambda request: json_reply(200, {"data": []}, self.QUOTA))
        client = api.client()
        self.assertIsNone(client.last_rate_limit)
        client.countries.list()
        self.assertEqual(
            client.last_rate_limit, RateLimit(minute=self.expected_minute(), day=None, month=None)
        )

    def test_a_window_without_a_reset(self) -> None:
        headers = {"x-ratelimit-limit-day": "1000", "x-ratelimit-remaining-day": " 10 "}
        api = self.start(lambda request: json_reply(200, {"data": []}, headers))
        client = api.client()
        client.countries.list()
        self.assertEqual(
            client.last_rate_limit,
            RateLimit(minute=None, day=RateLimitWindow(1000, 10, None), month=None),
        )

    def test_keeps_the_last_state_when_a_response_carries_no_headers(self) -> None:
        replies = iter([json_reply(200, {"data": []}, self.QUOTA), json_reply(200, {"data": []})])
        api = self.start(lambda request: next(replies))
        client = api.client()
        client.countries.list()
        client.countries.list()
        assert client.last_rate_limit is not None
        assert client.last_rate_limit.minute is not None
        self.assertEqual(client.last_rate_limit.minute.remaining, 59)

    def test_counts_the_quota_of_an_error_too(self) -> None:
        api = self.start(lambda request: json_reply(429, {"window": "minute"}, self.QUOTA))
        client = api.client()
        with self.assertRaises(FlightByteError):
            client.countries.list()
        self.assertIsNotNone(client.last_rate_limit)

    def test_hands_out_state_that_cannot_change_the_client(self) -> None:
        api = self.start(lambda request: json_reply(200, {"data": []}, self.QUOTA))
        client = api.client()
        client.countries.list()
        state = client.last_rate_limit
        assert state is not None and state.minute is not None
        with self.assertRaises(dataclasses.FrozenInstanceError):
            state.minute.remaining = 0  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            state.minute = None  # type: ignore[misc]
        self.assertEqual(client.last_rate_limit, RateLimit(self.expected_minute(), None, None))

    def test_one_client_shared_by_many_threads(self) -> None:
        def reply(request: Recorded) -> Reply:
            remaining = request.query["lang"]
            headers = {"x-ratelimit-limit-minute": "100", "x-ratelimit-remaining-minute": remaining}
            return json_reply(200, {"data": [{"code": remaining}]}, headers)

        api = self.start(reply)
        client = api.client()
        errors: list[BaseException] = []
        seen: list[str] = []

        def work(worker: int) -> None:
            try:
                for i in range(10):
                    value = str(worker * 10 + i)
                    countries = client.countries.list(lang=value)
                    if countries[0]["code"] != value:
                        raise AssertionError("a thread got another thread's answer")
                    seen.append(value)
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(seen), 80)
        state = client.last_rate_limit
        assert state is not None and state.minute is not None
        self.assertIn(str(state.minute.remaining), seen)


def _hang(request: Recorded, handler: Any) -> None:
    """Never answers, like a stuck server."""
    time.sleep(3)


def _trickle(request: Recorded, handler: Any) -> None:
    """Answers at once, then sends the body a byte every 50 ms, so every read is quick."""
    handler.send_response(200)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", "100")
    handler.end_headers()
    try:
        for _ in range(100):
            handler.wfile.write(b" ")
            handler.wfile.flush()
            time.sleep(0.05)
    except OSError:
        pass


class NoResponseTest(APITestCase):
    def test_times_out_with_an_api_connection_error(self) -> None:
        api = self.start(raw=_hang)
        started = time.monotonic()
        with self.assertRaises(APIConnectionError) as caught:
            api.client(timeout=0.2).countries.list()
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertTrue(caught.exception.timed_out)
        self.assertEqual(
            str(caught.exception), f"GET {api.url}/v1/countries timed out after 0.2 s."
        )
        self.assertIsInstance(caught.exception, FlightByteError)

    def test_the_timeout_covers_the_whole_body(self) -> None:
        api = self.start(raw=_trickle)
        started = time.monotonic()
        with self.assertRaises(APIConnectionError) as caught:
            api.client(timeout=0.3).countries.list()
        # Each read takes 50 ms, far under the timeout; only a deadline over
        # the whole request stops it before the 5 s the body would take.
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertTrue(caught.exception.timed_out)

    def test_one_request_can_override_the_timeout(self) -> None:
        api = self.start(raw=_hang)
        client = api.client(timeout=60)
        started = time.monotonic()
        with self.assertRaises(APIConnectionError) as caught:
            client.countries.list(timeout=0.1)
        self.assertTrue(caught.exception.timed_out)
        self.assertLess(time.monotonic() - started, 1.5)
        with self.assertRaises(ValueError):
            client.countries.list(timeout=-1)

    def test_a_request_without_a_timeout(self) -> None:
        api = self.start(lambda request: json_reply(200, {"data": [], "count": 0}))
        self.assertEqual(api.client(timeout=None).countries.list(), [])
        self.assertEqual(api.client().countries.list(timeout=None), [])

    def test_a_refused_port(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        client = FlightByte("k", base_url=f"http://127.0.0.1:{port}/v1")
        with self.assertRaises(APIConnectionError) as caught:
            client.countries.list()
        self.assertFalse(caught.exception.timed_out)
        self.assertRegex(
            str(caught.exception), rf"^GET http://127.0.0.1:{port}/v1/countries failed: "
        )
        self.assertIsNotNone(caught.exception.__cause__)

    def test_a_tls_failure(self) -> None:
        api = self.start()
        client = FlightByte("k", base_url=api.url.replace("http://", "https://") + "/v1", timeout=5)
        with self.assertRaises(APIConnectionError) as caught:
            client.countries.list()
        self.assertFalse(caught.exception.timed_out)

    def test_a_connection_closed_without_an_answer(self) -> None:
        def hang_up(request: Recorded, handler: Any) -> None:
            handler.connection.shutdown(socket.SHUT_RDWR)

        api = self.start(raw=hang_up)
        with self.assertRaises(APIConnectionError) as caught:
            api.client().countries.list()
        self.assertFalse(caught.exception.timed_out)

    def test_a_body_cut_short(self) -> None:
        def cut(request: Recorded, handler: Any) -> None:
            handler.send_response(200)
            handler.send_header("content-length", "100")
            handler.end_headers()
            handler.wfile.write(b'{"data": [')
            handler.wfile.flush()
            handler.connection.shutdown(socket.SHUT_RDWR)

        api = self.start(raw=cut)
        with self.assertRaises(APIConnectionError):
            api.client().countries.list()


class FormatDateTest(unittest.TestCase):
    def test_formats_the_calendar_date_in_the_given_time_zone(self) -> None:
        instant = datetime(2026, 9, 7, 22, 30, tzinfo=timezone.utc)
        self.assertEqual(FlightByte.format_date(instant, "Europe/Istanbul"), "2026-09-08")
        self.assertEqual(FlightByte.format_date(instant, "America/New_York"), "2026-09-07")
        self.assertEqual(FlightByte.format_date(instant, "UTC"), "2026-09-07")
        self.assertEqual(
            FlightByte.format_date(instant, timezone(timedelta(hours=3))), "2026-09-08"
        )

    def test_keeps_a_datetime_or_date_as_it_is_without_a_zone(self) -> None:
        istanbul = datetime(2026, 9, 8, 1, 30, tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(FlightByte.format_date(istanbul), "2026-09-08")
        self.assertEqual(FlightByte.format_date(datetime(2026, 9, 8, 23, 59)), "2026-09-08")
        self.assertEqual(FlightByte.format_date(date(2026, 1, 2)), "2026-01-02")
        self.assertEqual(FlightByte.format_date(date(999, 1, 2)), "0999-01-02")

    def test_rejects_what_it_cannot_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown time zone"):
            FlightByte.format_date(datetime(2026, 9, 8, tzinfo=timezone.utc), "Mars/Olympus")
        with self.assertRaises(TypeError):
            FlightByte.format_date("2026-09-08")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
