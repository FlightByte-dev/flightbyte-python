"""Redirects, against real local servers and the real HTTP stack.

The API key is sent with every request, so a redirect this client followed to
another origin would hand the key to that origin.
"""

import unittest
from collections.abc import Callable

from flightbyte import FlightByte, UnexpectedStatusError
from flightbyte._transport import redirect_target

from .helpers import APITestCase, Recorded, Reply, json_reply

COUNTRIES = {"count": 1, "data": [{"code": "TR"}]}


def redirect(location: str, status: int = 302) -> Reply:
    return Reply(status, b"", {"location": location})


class RedirectTest(APITestCase):
    def test_does_not_follow_one_to_another_origin_so_the_key_stays_home(self) -> None:
        other = self.start(lambda request: json_reply(200, COUNTRIES))
        api = self.start(lambda request: redirect(f"{other.url}/steal"))
        client = FlightByte("frk_secret", base_url=f"{api.url}/v1")

        with self.assertRaises(UnexpectedStatusError) as caught:
            client.countries.list()
        self.assertEqual(other.calls, [])
        self.assertEqual(caught.exception.status, 302)
        self.assertEqual(caught.exception.location, f"{other.url}/steal")

    def test_does_not_follow_one_to_another_port_on_the_same_host(self) -> None:
        other = self.start(lambda request: json_reply(200, COUNTRIES))
        api = self.start(lambda request: redirect(f"{other.url}/v1/countries", 301))
        with self.assertRaises(UnexpectedStatusError):
            api.client().countries.list()
        self.assertEqual(other.calls, [])

    def test_follows_one_within_the_origin_key_and_all(self) -> None:
        def reply(request: Recorded) -> Reply:
            if request.path == "/v1/countries":
                return redirect("/v1/moved", 301)
            return json_reply(200, COUNTRIES)

        api = self.start(reply)
        client = FlightByte("frk_secret", base_url=f"{api.url}/v1")

        self.assertEqual(client.countries.list(), [{"code": "TR"}])
        self.assertEqual(
            [(call.method, call.path, call.headers.get("x-api-key")) for call in api.calls],
            [("GET", "/v1/countries", "frk_secret"), ("GET", "/v1/moved", "frk_secret")],
        )

    def test_follows_an_absolute_location_on_the_same_origin(self) -> None:
        def reply(request: Recorded) -> Reply:
            if request.path == "/v1/countries":
                return redirect(f"{api.url}/v1/elsewhere?lang=tr#top", 308)
            return json_reply(200, COUNTRIES)

        api = self.start(reply)
        api.client().countries.list()
        self.assertEqual(api.last().path, "/v1/elsewhere")
        self.assertEqual(api.last().raw_query, "lang=tr")

    def test_does_not_follow_one_for_a_request_other_than_get_or_head(self) -> None:
        api = self.start(lambda request: redirect("/v1/elsewhere", 307))
        client = api.client()
        calls: list[tuple[str, Callable[[], object]]] = [
            ("POST", lambda: client.subscriptions.pause("sub_1")),
            ("PATCH", lambda: client.subscriptions.update("sub_1", delay_threshold_minutes=5)),
            ("DELETE", lambda: client.subscriptions.delete("sub_1")),
            (
                "POST with a body",
                lambda: client.subscriptions.create("TK", "1", "2026-09-08", "https://e.test/h"),
            ),
        ]
        for name, call in calls:
            with self.subTest(name), self.assertRaises(UnexpectedStatusError) as caught:
                call()
            self.assertEqual(caught.exception.location, "/v1/elsewhere")
        self.assertEqual(len(api.calls), 4)
        self.assertNotIn("/v1/elsewhere", [call.path for call in api.calls])

    def test_gives_up_on_a_loop_after_five_hops(self) -> None:
        api = self.start(
            lambda request: Reply(302, b'{"message": "moved"}', {"location": request.path})
        )
        with self.assertRaises(UnexpectedStatusError) as caught:
            api.client().countries.list()
        self.assertEqual(caught.exception.status, 302)
        self.assertEqual(caught.exception.messages, ["moved"])
        self.assertEqual(len(api.calls), 6)

    def test_a_redirect_without_a_location_is_an_error(self) -> None:
        api = self.start(lambda request: Reply(302))
        with self.assertRaises(UnexpectedStatusError) as caught:
            api.client().countries.list()
        self.assertIsNone(caught.exception.location)
        self.assertEqual(len(api.calls), 1)


class RedirectTargetTest(unittest.TestCase):
    """The rule itself, for cases a local http server cannot stage."""

    def target(
        self, current: str, location: str, method: str = "GET", status: int = 302
    ) -> str | None:
        return redirect_target(status, {"location": location}, current, method)

    def test_does_not_follow_https_to_http_on_the_same_host(self) -> None:
        self.assertIsNone(
            self.target("https://api.test/v1/countries", "http://api.test/v1/countries")
        )

    def test_treats_the_default_port_as_the_same_origin(self) -> None:
        self.assertEqual(
            self.target("https://api.test/v1/a", "https://API.test:443/v1/b"),
            "https://API.test:443/v1/b",
        )
        self.assertEqual(self.target("http://api.test:80/v1/a", "/v1/b"), "http://api.test:80/v1/b")

    def test_refuses_a_lookalike_host(self) -> None:
        for location in [
            "https://api.test.evil.example/v1",
            "https://api.test@evil.example/v1",
            "//evil.example/v1",
            "https:\\\\evil.example/v1",
        ]:
            with self.subTest(location):
                target = self.target("https://api.test/v1/a", location)
                if target is not None:
                    self.assertTrue(target.startswith("https://api.test/"), target)

    def test_refuses_what_is_not_a_redirect_or_not_a_read(self) -> None:
        self.assertIsNone(self.target("https://api.test/a", "/b", status=200))
        self.assertIsNone(self.target("https://api.test/a", "/b", status=400))
        self.assertIsNone(self.target("https://api.test/a", "/b", method="PUT"))
        self.assertEqual(
            self.target("https://api.test/a", "/b", method="HEAD"), "https://api.test/b"
        )

    def test_refuses_a_location_with_control_characters(self) -> None:
        self.assertIsNone(self.target("https://api.test/a", "/b\r\nx-evil: 1"))
        self.assertIsNone(self.target("https://api.test/a", "/b c"))
        self.assertIsNone(self.target("https://api.test/a", "https://api.test:99999/b"))


if __name__ == "__main__":
    unittest.main()
