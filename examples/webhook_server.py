"""A webhook receiver on the standard library's http.server, with no framework.

    FLIGHTBYTE_WEBHOOK_SECRET=whsec_... python examples/webhook_server.py

It listens on port 8080 (or PORT). Expose it with a tunnel, for example
``cloudflared tunnel --url http://localhost:8080``, subscribe a flight with
that URL plus ``/hooks/flightbyte``, and call ``subscriptions.send_test``.

It does what every receiver has to: verify the signature against the raw body,
deduplicate on the event id, answer before doing the work, and branch on the
event type.
"""

import os
import queue
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from flightbyte import FlightByteError, Webhook, WebhookEvent, WebhookSignatureError

MAX_BODY_BYTES = 1024 * 1024

secret = os.environ.get("FLIGHTBYTE_WEBHOOK_SECRET", "")
if not secret.strip():
    # Anyone can sign with an empty key, so refuse to start without one.
    sys.exit("Set FLIGHTBYTE_WEBHOOK_SECRET to the subscription's signing secret.")

jobs: "queue.Queue[WebhookEvent]" = queue.Queue()
handled: set[str] = set()  # use your database in production
handled_lock = threading.Lock()


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/hooks/flightbyte":
            return self.answer(404, "not found")
        length = int(self.headers.get("content-length") or 0)
        if length > MAX_BODY_BYTES:
            return self.answer(413, "body too large")
        payload = self.rfile.read(length)  # the raw body, exactly as signed

        try:
            event = Webhook.construct_event(
                payload, self.headers.get(Webhook.SIGNATURE_HEADER), secret
            )
        except WebhookSignatureError:
            return self.answer(401, "invalid signature")
        except FlightByteError:
            return self.answer(400, "invalid event")

        # A retry carries the same id: answer it, but don't handle it twice.
        with handled_lock:
            first_time = event["id"] not in handled
            handled.add(event["id"])
        if first_time:
            # Answer first: FlightByte treats a delivery as failed after 10 seconds.
            jobs.put(event)
        self.answer(200, "ok")

    def answer(self, status: int, text: str) -> None:
        body = text.encode()
        self.send_response(status)
        self.send_header("content-type", "text/plain")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def work() -> None:
    while True:
        event = jobs.get()
        if event["type"] == "flight.updated":
            for change in event["changes"]:
                print(f"{event['flightKey']} {change['type']}: {change['message']}")
        elif event["type"] == "subscription.completed":
            print(f"{event['flightKey']} finished")
        else:
            print(f"{event['flightKey']} {event['type']}")


if __name__ == "__main__":
    threading.Thread(target=work, daemon=True).start()
    port = int(os.environ.get("PORT", "8080"))
    print(f"Listening on http://localhost:{port}/hooks/flightbyte")
    ThreadingHTTPServer(("", port), Receiver).serve_forever()
