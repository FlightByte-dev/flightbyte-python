import json
import random
import time
import unittest
from datetime import datetime, timezone

from flightbyte import FlightByteError, Webhook, WebhookSignatureError
from flightbyte._webhook import _parse_signature

from .helpers import fixture, fixture_text

# Signatures made by tool/webhook_vectors.mjs with Node's createHmac, exactly as the API signs.
VECTORS = fixture("webhook_vectors.json")
SECRET: str = VECTORS["secret"]
AT: int = VECTORS["timestamp"]
UPDATED = VECTORS["cases"][1]
PAYLOAD = fixture_text(UPDATED["file"])
SIGNATURE: str = UPDATED["signature"]
SIG = SIGNATURE.split(",v1=")[1]


class VerifyAgainstTheAPISignerTest(unittest.TestCase):
    def test_every_vector(self) -> None:
        for case in VECTORS["cases"]:
            with self.subTest(case["file"]):
                body = fixture_text(case["file"])
                raw = (fixture_text(case["file"])).encode("utf-8")
                for payload in (body, raw, bytearray(raw), memoryview(raw)):
                    self.assertIsNone(Webhook.verify(payload, case["signature"], SECRET, now=AT))
                self.assertEqual(Webhook.sign(body, SECRET, AT), case["signature"])
                self.assertEqual(Webhook.sign(raw, SECRET, timestamp=AT), case["signature"])
                at = datetime.fromtimestamp(AT, tz=timezone.utc)
                self.assertEqual(Webhook.sign(raw, SECRET, at), case["signature"])
                event = Webhook.construct_event(raw, case["signature"], SECRET, now=at)
                self.assertEqual(event["subscriptionId"], "sub_1")

    def test_the_body_is_bytes_the_whole_way(self) -> None:
        # The vector body has non-ASCII text; the bytes on disk are what was signed.
        raw = (fixture_text(UPDATED["file"])).encode("utf-8")
        self.assertIn("İstanbul".encode(), raw)
        self.assertTrue(Webhook.is_valid(raw, SIGNATURE, SECRET, now=AT))
        self.assertFalse(
            Webhook.is_valid(raw.decode("utf-8").encode("utf-16"), SIGNATURE, SECRET, now=AT)
        )


class VerifyRejectsTest(unittest.TestCase):
    def test_each_case(self) -> None:
        cases: list[tuple[str, str, str | None, str, float, str]] = [
            ("the wrong secret", PAYLOAD, SIGNATURE, f"{SECRET}x", AT, "does not match"),
            (
                "a changed body",
                PAYLOAD.replace("A22", "A23"),
                SIGNATURE,
                SECRET,
                AT,
                "does not match",
            ),
            (
                "a re-encoded body",
                json.dumps(json.loads(PAYLOAD), indent=2),
                SIGNATURE,
                SECRET,
                AT,
                "does not match",
            ),
            ("a missing header", PAYLOAD, None, SECRET, AT, "missing"),
            ("an empty header", PAYLOAD, "  ", SECRET, AT, "missing"),
            ("no timestamp", PAYLOAD, f"v1={SIG}", SECRET, AT, "no valid timestamp"),
            (
                "a timestamp that is not a number",
                PAYLOAD,
                f"t=soon,v1={SIG}",
                SECRET,
                AT,
                "no valid timestamp",
            ),
            ("a negative timestamp", PAYLOAD, f"t=-1,v1={SIG}", SECRET, AT, "no valid timestamp"),
            (
                "a huge timestamp",
                PAYLOAD,
                f"t=9223372036854775807,v1={SIG}",
                SECRET,
                AT,
                "no valid timestamp",
            ),
            # Arabic-Indic digits: Python's \d would take them, the API never sends them.
            (
                "digits from another script",
                PAYLOAD,
                f"t=\u0661\u0662,v1={SIG}",
                SECRET,
                AT,
                "no valid timestamp",
            ),
            ("no signature", PAYLOAD, f"t={AT}", SECRET, AT, "no v1 signature"),
            ("another scheme only", PAYLOAD, f"t={AT},v0={SIG}", SECRET, AT, "no v1 signature"),
            (
                "a signature that is not hex",
                PAYLOAD,
                f"t={AT},v1={'z' * 64}",
                SECRET,
                AT,
                "does not match",
            ),
            ("a short signature", PAYLOAD, f"t={AT},v1={SIG[:10]}", SECRET, AT, "does not match"),
            (
                "a signature that is not ASCII",
                PAYLOAD,
                f"t={AT},v1={'é' * 64}",
                SECRET,
                AT,
                "does not match",
            ),
            ("an old signature", PAYLOAD, SIGNATURE, SECRET, AT + 301, "tolerance"),
            ("a signature from the future", PAYLOAD, SIGNATURE, SECRET, AT - 301, "tolerance"),
        ]
        for name, body, signature, secret, now, reason in cases:
            with self.subTest(name):
                with self.assertRaisesRegex(WebhookSignatureError, reason):
                    Webhook.verify(body, signature, secret, now=now)
                self.assertFalse(Webhook.is_valid(body, signature, secret, now=now))
                with self.assertRaises(WebhookSignatureError):
                    Webhook.construct_event(body, signature, secret, now=now)

    def test_a_tighter_tolerance(self) -> None:
        with self.assertRaisesRegex(WebhookSignatureError, "tolerance"):
            Webhook.verify(PAYLOAD, SIGNATURE, SECRET, now=AT + 60, tolerance=30)

    def test_a_payload_that_is_not_the_raw_body(self) -> None:
        with self.assertRaisesRegex(TypeError, "raw body"):
            Webhook.verify(json.loads(PAYLOAD), SIGNATURE, SECRET, now=AT)


class VerifyAcceptsTest(unittest.TestCase):
    def test_each_case(self) -> None:
        t, v1 = f"t={AT}", f"v1={SIG}"
        cases: list[tuple[str, str, float, float | None]] = [
            ("at the edge of the window", SIGNATURE, AT + 300, None),
            ("at the other edge", SIGNATURE, AT - 300, None),
            ("a fraction of a second later", SIGNATURE, AT + 300.9, None),
            ("any time with the check off", SIGNATURE, AT + 86_400, 0),
            ("two v1, the second right", f"{t},v1={'0' * 64},{v1}", AT, None),
            ("upper-case hex", f"{t},v1={SIG.upper()}", AT, None),
            ("spaces around parts", f" {t} , {v1} ", AT, None),
            ("an unknown scheme as well", f"{t},v0=abc,{v1}", AT, None),
            ("a part without an equal sign", f"{t},junk,{v1}", AT, None),
        ]
        for name, signature, now, tolerance in cases:
            with self.subTest(name):
                if tolerance is None:
                    Webhook.verify(PAYLOAD, signature, SECRET, now=now)
                    self.assertTrue(Webhook.is_valid(PAYLOAD, signature, SECRET, now=now))
                else:
                    Webhook.verify(PAYLOAD, signature, SECRET, now=now, tolerance=tolerance)
                    self.assertTrue(
                        Webhook.is_valid(PAYLOAD, signature, SECRET, now=now, tolerance=tolerance)
                    )

    def test_a_fresh_signature_with_the_real_clock(self) -> None:
        body = b'{"id":"evt_9","type":"subscription.test"}'
        signature = Webhook.sign(body, "whsec_roundtrip")
        Webhook.verify(body, signature, "whsec_roundtrip")
        self.assertLessEqual(abs(int(signature[2:].split(",")[0]) - time.time()), 2)


class ConstructEventTest(unittest.TestCase):
    def test_decodes_the_event(self) -> None:
        event = Webhook.construct_event(PAYLOAD, SIGNATURE, SECRET, now=AT)
        self.assertEqual(event["type"], "flight.updated")
        change = event["changes"][0]
        self.assertEqual(
            (change["type"], change["from"], change["to"]), ("departure.gate.changed", "A11", "A22")
        )
        self.assertIn("İstanbul", change["message"])
        self.assertEqual(event.get("metadata"), {"booking": "42"})

    def test_rejects_a_signed_body_that_is_not_an_event(self) -> None:
        cases = [
            ("not JSON", b"not json", "not JSON"),
            ("not UTF-8", b"\xff\xfe", "not JSON"),
            ("an array", b"[1,2]", "not a FlightByte event"),
            ("an object without an id", b'{"type":"x"}', "not a FlightByte event"),
            ("an object without a type", b'{"id":"evt_1"}', "not a FlightByte event"),
            ("an id that is not a string", b'{"id":1,"type":"x"}', "not a FlightByte event"),
        ]
        for name, body, message in cases:
            with self.subTest(name):
                signature = Webhook.sign(body, "s")
                with self.assertRaisesRegex(FlightByteError, message) as caught:
                    Webhook.construct_event(body, signature, "s")
                self.assertNotIsInstance(caught.exception, WebhookSignatureError)


class EmptySecretTest(unittest.TestCase):
    def test_is_refused_by_every_method(self) -> None:
        forged = f"t={AT},v1={'0' * 64}"
        for empty in ("", "   ", "\t\n"):
            with self.subTest(repr(empty)):
                with self.assertRaisesRegex(ValueError, "secret is empty"):
                    Webhook.verify(PAYLOAD, forged, empty, now=AT)
                with self.assertRaisesRegex(ValueError, "secret is empty"):
                    Webhook.is_valid(PAYLOAD, forged, empty, now=AT)
                with self.assertRaises(ValueError):
                    Webhook.construct_event(PAYLOAD, forged, empty, now=AT)
                with self.assertRaises(ValueError):
                    Webhook.sign(PAYLOAD, empty)
        with self.assertRaises(TypeError):
            Webhook.verify(PAYLOAD, forged, None, now=AT)  # type: ignore[arg-type]

    def test_an_empty_secret_is_refused_before_the_signature_is_looked_at(self) -> None:
        with self.assertRaises(ValueError):
            Webhook.verify(PAYLOAD, None, "")


class WebhookClassTest(unittest.TestCase):
    def test_header_names_and_defaults(self) -> None:
        self.assertEqual(Webhook.SIGNATURE_HEADER, "x-flightbyte-signature")
        self.assertEqual(Webhook.TIMESTAMP_HEADER, "x-flightbyte-timestamp")
        self.assertEqual(Webhook.EVENT_ID_HEADER, "x-flightbyte-event-id")
        self.assertEqual(Webhook.EVENT_TYPE_HEADER, "x-flightbyte-event-type")
        self.assertEqual(Webhook.SUBSCRIPTION_ID_HEADER, "x-flightbyte-subscription-id")
        self.assertEqual(Webhook.DELIVERY_ATTEMPT_HEADER, "x-flightbyte-delivery-attempt")
        self.assertEqual(Webhook.DEFAULT_TOLERANCE, 300)

    def test_is_not_instantiated(self) -> None:
        with self.assertRaises(TypeError):
            Webhook()


class ParseSignatureTest(unittest.TestCase):
    def test_never_raises_anything_but_a_webhook_signature_error(self) -> None:
        rng = random.Random(20260908)
        inputs = [
            "",
            ",,,=,t=,v1=",
            "t=1",
            "=1",
            "t==1,v1==",
            "t=1,v1=a,v1=b",
            "\x00",
            "t=1" * 1000,
        ]
        alphabet = "t=v1,0123456789abcdef \x00\u00e9\u0661"
        for _ in range(2000):
            inputs.append("".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40))))
        for _ in range(500):
            inputs.append("".join(chr(rng.randint(32, 126)) for _ in range(20)))
        for value in inputs:
            try:
                timestamp, signatures = _parse_signature(value)
            except WebhookSignatureError:
                continue
            self.assertTrue(signatures)
            self.assertRegex(timestamp, r"^[0-9]{1,15}$")
            # And a parsed header never makes verify raise anything else either.
            self.assertFalse(Webhook.is_valid(PAYLOAD, value, SECRET, tolerance=0))


if __name__ == "__main__":
    unittest.main()
