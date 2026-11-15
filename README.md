<p align="center">
  <a href="https://flightbyte.dev">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/FlightByte-dev/flightbyte-python/main/assets/logo-dark.svg">
      <img src="https://raw.githubusercontent.com/FlightByte-dev/flightbyte-python/main/assets/logo-light.svg" alt="FlightByte" width="340">
    </picture>
  </a>
</p>

<h3 align="center">FlightByte for Python</h3>

<p align="center">
  The official Python client for the FlightByte flight status API.<br>
  Look flights up, watch them with signed webhooks and verify every delivery,<br>
  from a web service, a worker or a script.
</p>

<p align="center">
  <a href="https://pypi.org/project/flightbyte/"><img src="https://img.shields.io/pypi/v/flightbyte?style=flat-square&color=EF6A1A&label=pypi" alt="PyPI version"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-121212?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/dependencies-none-EF6A1A?style=flat-square" alt="No dependencies">
  <a href="https://github.com/FlightByte-dev/flightbyte-python/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-121212?style=flat-square" alt="MIT license"></a>
</p>

<p align="center">
  <a href="https://flightbyte.dev/docs"><b>Docs</b></a> ·
  <a href="https://app.flightbyte.dev/signup?utm_source=pypi&utm_medium=readme&utm_campaign=python-sdk"><b>Get a free key</b></a> ·
  <a href="https://flightbyte.dev/docs/reference"><b>API reference</b></a> ·
  <a href="https://flightbyte.dev/docs/webhooks"><b>Webhook docs</b></a> ·
  <a href="https://t.me/flightbyte"><b>Support</b></a>
</p>

---

## Quick start

1. Get a free API key at [app.flightbyte.dev/signup](https://app.flightbyte.dev/signup?utm_source=pypi&utm_medium=readme&utm_campaign=python-sdk).
2. Add the package:

   | | Command |
   | --- | --- |
   | **pip** | `pip install flightbyte` |
   | **uv** | `uv add flightbyte` |
   | **Poetry** | `poetry add flightbyte` |
   | **pipenv** | `pipenv install flightbyte` |

3. Look a flight up:

   ```python
   import os

   from flightbyte import FlightByte

   client = FlightByte(api_key=os.environ["FLIGHTBYTE_API_KEY"])

   flight = client.flights.get(
       carrier="TK",
       flight_number="1848",
       date="2026-09-08",  # local departure date at the origin
   )

   print(flight["status"]["label"])                # Scheduled
   print(flight["departure"].get("gate"))          # A11
   print(flight["departure"].get("delayMinutes"))  # 15
   ```

Responses are plain dicts typed with `TypedDict`, so mypy, Pyright and your editor know every key. `FlightByte.format_date(datetime.now(timezone.utc), "Europe/Istanbul")` gives the `YYYY-MM-DD` the API expects, in the origin airport's time zone. To try it from a terminal, run the example in this repository:

```bash
pip install -e .
FLIGHTBYTE_API_KEY=frk_live_... python examples/lookup.py TK 1 2026-11-15
```

```text
TK1:2026-11-15@IST-JFK  IST → JFK
Status     Scheduled (scheduled)
Departure  2026-11-15T15:20:00.000 +03, gate D15
Arrival    2026-11-15T18:20:00.000 EST, baggage -
Quota      23 of 30 left this minute
```

## What you can do

| You want to | You call |
| --- | --- |
| *Show a passenger their gate and delay* | `client.flights.get(...)` returns the live snapshot: phase, gate, terminal, baggage belt, scheduled, estimated and actual times, delay, aircraft and codeshares. |
| *Look up TK1 tomorrow, which flies two legs* | Pass `origin="IST"`. Without it the snapshot lists every leg in `alternates`, and a subscription refuses to guess: the `BadRequestError` carries the `legs` to choose from. |
| *Be told when anything changes* | `client.subscriptions.create(...)` starts the watch and returns the signing secret, shown once. |
| *Find out why webhooks stopped arriving* | `client.subscriptions.get(id)` and `deliveries(id)` show the status and the HTTP code and error of every recent attempt. |
| *Trust a webhook on your server* | `Webhook.construct_event(body, signature, secret)` verifies the signature against the raw body and decodes the event. |

## API

**Flights**: read-only.

| Method | What it does |
| --- | --- |
| `flights.get` | Live status of one flight leg, and every leg the number flies that day.<br><sub>`GET /v1/flights/{carrier}/{flightNumber}/{date}`</sub> |
| `flights.timeline` | The airline's own change history for a leg, newest first.<br><sub>`GET /v1/flights/{carrier}/{flightNumber}/{date}/timeline`</sub> |

**Subscriptions**

| Method | What it does | Access |
| --- | --- | --- |
| `subscriptions.create` | Watch a flight and get a signed webhook for every change. Counts as a watched flight on your plan; pass `idempotency_key` so a retry never counts twice.<br><sub>`POST /v1/subscriptions`</sub> | writes |
| `subscriptions.list` | One page of your subscriptions, filtered by status, carrier, number or date.<br><sub>`GET /v1/subscriptions`</sub> | read-only |
| `subscriptions.list_all` | Every matching subscription, fetched page by page as you iterate over it with `for`.<br><sub>`GET /v1/subscriptions`</sub> | read-only |
| `subscriptions.get` | One subscription with its status and delivery counters.<br><sub>`GET /v1/subscriptions/{id}`</sub> | read-only |
| `subscriptions.update` | Change the webhook URL, event filter, delay threshold, headers or metadata.<br><sub>`PATCH /v1/subscriptions/{id}`</sub> | writes |
| `subscriptions.pause` | Stop polling and deliveries without losing anything.<br><sub>`POST /v1/subscriptions/{id}/pause`</sub> | writes |
| `subscriptions.resume` | Resume a paused or auto-suspended subscription.<br><sub>`POST /v1/subscriptions/{id}/resume`</sub> | writes |
| `subscriptions.delete` | Delete a subscription for good.<br><sub>`DELETE /v1/subscriptions/{id}`</sub> | **destructive** |
| `subscriptions.send_test` | Send a signed `subscription.test` webhook to the subscription's URL.<br><sub>`POST /v1/subscriptions/{id}/test`</sub> | writes |
| `subscriptions.deliveries` | Recent delivery attempts with HTTP status and errors.<br><sub>`GET /v1/subscriptions/{id}/deliveries`</sub> | read-only |
| `subscriptions.events` | Recent events with the exact payloads that were sent.<br><sub>`GET /v1/subscriptions/{id}/events`</sub> | read-only |
| `subscriptions.secret` | Reveal the signing secret again.<br><sub>`GET /v1/subscriptions/{id}/secret`</sub> | read-only |
| `subscriptions.rotate_secret` | Generate a new signing secret. Previous signatures stop validating.<br><sub>`POST /v1/subscriptions/{id}/secret/rotate`</sub> | writes |

**Countries**: read-only.

| Method | What it does |
| --- | --- |
| `countries.list` | Every country with its name in any language, emoji and flag URLs.<br><sub>`GET /v1/countries`</sub> |
| `countries.get` | One country by its ISO 3166-1 alpha-2 code.<br><sub>`GET /v1/countries/{code}`</sub> |
| `countries.flag_url` | The URL of a country's SVG flag, 4:3 or square. Needs no key, so it can go straight into an `<img>`.<br><sub>`GET /v1/flags/{code}.svg`</sub> |

Every method takes a keyword-only `timeout` of its own, in seconds. Arguments carry the API's own names in Python form (`carrier`, `flight_number`, `date`, `origin`, `webhook_url`, `idempotency_key`, …), and responses come back exactly as the API sent them: dicts with the API's own keys, timestamps as ISO 8601 strings, and no field renamed or dropped. The full snapshot is documented under [Flights](https://flightbyte.dev/docs/flights).

## Watch a flight

```python
created = client.subscriptions.create(
    carrier="TK",
    flight_number="1848",
    date="2026-09-08",
    webhook_url="https://api.example.com/hooks/flights",
    events=["departure.gate.changed", "delay.increased", "flight.departed"],
    metadata={"bookingId": "BK-1042"},
    idempotency_key="BK-1042",  # safe to retry
)

# Shown in full only now: store it where your webhook receiver can read it.
signing_secret = created["secret"]
```

FlightByte only delivers to public HTTPS addresses. To receive on your machine, expose the port with a tunnel (`cloudflared tunnel --url http://localhost:8080` or `ngrok http 8080`) and use that URL. `subscriptions.send_test(id)` sends a signed `subscription.test` whenever you want to see the path work.

## Receive webhooks

A receiver has to do four things, in this order: verify the signature against the **raw** body, deduplicate on the event id, answer `2xx` before doing the work, and branch on the event type.

`Webhook.construct_event` does the first: it checks the signature against the body and decodes the event. It raises `WebhookSignatureError` for a bad signature (answer `401`) and `FlightByteError` for a signed body that is not an event (answer `400`). An empty secret raises a `ValueError` right away, because anyone can sign with an empty key: an unset environment variable fails loudly instead of accepting forged events. Give it the body as bytes, before any JSON parsing. With Flask, that is `request.get_data()`, not `request.json`:

```python
import os

from flask import Flask, request
from flightbyte import FlightByteError, Webhook, WebhookSignatureError

app = Flask(__name__)
signing_secret = os.environ["FLIGHTBYTE_WEBHOOK_SECRET"]


@app.post("/hooks/flightbyte")
def flightbyte_hook():
    try:
        event = Webhook.construct_event(
            request.get_data(),  # the raw body
            request.headers.get(Webhook.SIGNATURE_HEADER),
            signing_secret,
        )
    except WebhookSignatureError:
        return "invalid signature", 401
    except FlightByteError:
        return "invalid event", 400

    # A retry carries the same id: answer it, but don't handle it twice.
    if mark_handled(event["id"]):
        # Answer first: FlightByte treats a delivery as failed after 10 seconds.
        jobs.put(event)
    return "ok", 200
```

<details>
<summary><b>Django and FastAPI</b></summary>

<br>

```python
# Django: the raw body is request.body. The signature is the check, so no CSRF token.
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


@csrf_exempt
@require_POST
def flightbyte_hook(request):
    try:
        event = Webhook.construct_event(
            request.body, request.headers.get(Webhook.SIGNATURE_HEADER), signing_secret
        )
    except WebhookSignatureError:
        return HttpResponse("invalid signature", status=401)
    except FlightByteError:
        return HttpResponse("invalid event", status=400)
    jobs.put(event)
    return HttpResponse("ok")


# FastAPI and Starlette: read the body yourself, not through a Pydantic model.
from fastapi import FastAPI, Request, Response

app = FastAPI()


@app.post("/hooks/flightbyte")
async def flightbyte_hook(request: Request) -> Response:
    try:
        event = Webhook.construct_event(
            await request.body(), request.headers.get(Webhook.SIGNATURE_HEADER), signing_secret
        )
    except WebhookSignatureError:
        return Response("invalid signature", status_code=401)
    except FlightByteError:
        return Response("invalid event", status_code=400)
    jobs.put_nowait(event)
    return Response("ok")
```

</details>

Then, off the request path:

```python
match event["type"]:
    case "flight.updated":
        for change in event["changes"]:
            print(f"{event['flightKey']} {change['type']}: {change['message']}")
    case "subscription.completed":
        print(f"{event['flightKey']} finished")
```

A receiver on the standard library's `http.server`, with no framework, is in [examples/webhook_server.py](https://github.com/FlightByte-dev/flightbyte-python/blob/main/examples/webhook_server.py).

<details>
<summary><b>How the signature works</b></summary>

<br>

```text
x-flightbyte-signature: t=1789305971,v1=5f1c9a...e3b2
v1 = HMAC-SHA256(secret, "<t>." + <raw body>)
```

`Webhook.verify` computes the HMAC over the bytes you received, not over JSON you parsed and serialised again, compares it in constant time with `hmac.compare_digest`, accepts any of several `v1` values, and rejects a `t` more than five minutes from now. `Webhook.sign` produces the same header, for testing your receiver. The test suite checks both against signatures made by the API's own signer, and throws thousands of random headers at the parser.

The reasons behind each step are in [Verifying webhook signatures](https://flightbyte.dev/guides/verifying-webhook-signatures), and reference receivers in Node.js, Python and Go are in [flightbyte-webhook-examples](https://github.com/FlightByte-dev/flightbyte-webhook-examples).

</details>

## Errors

Every failed request raises a subclass of `FlightByteError`, so you catch the ones you handle with `except`.

| Error | Status | When, and what to do |
| --- | --- | --- |
| `BadRequestError` | `400` | Invalid input; `messages` has one line per field. For a number that flies twice, `legs` lists them: pass one's `origin`. |
| `AuthenticationError` | `401` | Missing, invalid, revoked or expired API key. |
| `PaymentRequiredError` | `402` | No watched flights left. `code` says why: `watched_flight_limit`, `overage_cap_reached` (see `resets_at`) or `credits_exhausted` (see `balance` and `expires_at`). |
| `PermissionDeniedError` | `403` | The account is suspended, or a token lacks the scope (`code`). |
| `NotFoundError` | `404` | The flight did not operate that day, or no such subscription. |
| `RateLimitError` | `429` | A minute, day or month quota is used up. Wait `retry_after` seconds. |
| `UpstreamError` | `502` | The flight data provider failed. Retry shortly. It is also a `ServerError`. |
| `ServerError`, `UnexpectedStatusError` | other | Anything else. `request_id` is what support asks for. |
| `APIConnectionError` | none | No response at all: network or TLS error, or `timed_out` when the timeout ran out. |

```python
import time

from flightbyte import BadRequestError, PaymentRequiredError, RateLimitError

try:
    client.subscriptions.create(**params)
except BadRequestError as err:
    if not err.legs:
        raise
    print("Pick a leg:", ", ".join(leg["origin"] for leg in err.legs))
except PaymentRequiredError as err:
    print(f"No watched flights left ({err.code}) until {err.resets_at}")
except RateLimitError as err:
    time.sleep(err.retry_after or 5)
```

An `APIError` keeps the whole answer in `status`, `messages`, `body`, `raw_body` and `headers`, and every error pickles cleanly, so it crosses a process pool or a task queue intact. Every status is explained in the [errors docs](https://flightbyte.dev/docs/errors).

## Built for Python services

- **Web services, workers and scripts.** Flask, Django, FastAPI, Celery, cron jobs and notebooks, on Python 3.10 to 3.14, and CI runs it on every one of them. One client is safe to share across threads and keeps no connection open, so there is nothing to close. The client is synchronous: in an async app, call it from a plain `def` endpoint or through `asyncio.to_thread`. Proxies set in `HTTPS_PROXY` and `NO_PROXY` are honoured.
- **No dependencies.** Only the standard library: `urllib.request`, `json`, `hmac` and `hashlib`. Nothing to audit but this package.
- **Your key stays on your server.** An API key or a signing secret shipped inside a browser or mobile app can be pulled out of it by anyone who has the app. Flag images are the exception: `countries.flag_url` needs no key.
- **Your key stays with the API.** The client follows a redirect only for a read, and only on the API's own origin, so a misdirected answer cannot carry the key elsewhere and a write is never sent twice.
- **New API values don't break old code.** A phase, status or change type added after this release is still a valid `str`; `FLIGHT_PHASES`, `FLIGHT_CHANGE_TYPES` and the other tuples list the ones this version knows. The tests check every method and every type against the API's OpenAPI document, so a field the API adds shows up as a failing test here first, not as a missing key in your code.
- **Zero stays apart from unknown.** Keys the API may leave out are not required by the types, and values it may send as `null` include `None`, so a delay of `0` and no delay reading are different things.
- **Errors say what to do next.** A number that flies twice comes back with its legs, a `429` with how long to wait, a `402` with the reason and when the allowance resets.
- **Quotas are visible.** `client.last_rate_limit` holds the minute, day and month windows from the latest response's `X-RateLimit-*` headers.

## Configuration

```python
client = FlightByte(
    api_key=os.environ["FLIGHTBYTE_API_KEY"],
    base_url="http://localhost:3000/v1",
    timeout=10.0,
    user_agent="my-app/1.2",
)
```

| Option | Default | Meaning |
| --- | --- | --- |
| `api_key` | required | Your API key, sent as `x-api-key`. |
| `base_url` | `https://api.flightbyte.dev/v1` | API base URL, e.g. `http://localhost:3000/v1` for a local API. |
| `timeout` | `30.0` | Bounds each request, response body included, in seconds. `None` turns it off. Every method takes a `timeout` of its own too. |
| `user_agent` | none | Put in front of `flightbyte-python/<version>` in the `user-agent` header. |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e . -r requirements-dev.txt
python -m unittest discover -s tests -t .   # every test, against local servers
ruff check . && ruff format --check .
mypy --strict src tests
python -m build && twine check --strict dist/*
python scripts/sync_openapi.py               # refresh spec/openapi.json, then run the tests against it
node tool/webhook_vectors.mjs
```

The tests never touch the real API and need no key: they connect only to servers they start on `127.0.0.1`, and fail if anything tries to go elsewhere. They cover every method's request mapping, the error class for each status, redirects and timeouts against real local servers, the types against fixtures shaped like the API's JSON and against the API's OpenAPI document, and webhook verification against signatures made with Node's `createHmac` exactly as the API signs them. CI runs them on Python 3.10, 3.11, 3.12, 3.13 and 3.14, and again against the built wheel installed in a clean environment.

How to add a field, an enum value or an endpoint is in [CONTRIBUTING.md](https://github.com/FlightByte-dev/flightbyte-python/blob/main/CONTRIBUTING.md). Report security issues by email, as [SECURITY.md](https://github.com/FlightByte-dev/flightbyte-python/blob/main/SECURITY.md) explains, never in a public issue.

<details>
<summary><b>Project layout</b></summary>

```text
src/flightbyte/
  __init__.py              public exports
  _client.py               FlightByte and its options
  _transport.py            requests, headers, timeouts, redirects, error mapping
  _flights.py              flights
  _subscriptions.py        subscriptions, list_all and mask_secret
  _countries.py            countries and flag URLs
  _models.py               the API's TypedDicts and value lists
  _errors.py               FlightByteError and its subclasses
  _webhook.py              Webhook.verify, is_valid, construct_event and sign
  _rate_limit.py           X-RateLimit-* headers
  _util.py                 unwrapping {"data": [...]} answers
  py.typed                 marks the package as typed
spec/openapi.json          the API document the tests check against
tests/fixtures/            API-shaped JSON and signed webhook vectors
examples/                  a lookup from the terminal and a receiver on http.server
scripts/sync_openapi.py    refreshes spec/openapi.json
tool/webhook_vectors.mjs   regenerates the signed vectors with Node, as the API signs
tool/release_notes.sh      a version's CHANGELOG.md section, for the GitHub release
```

</details>

<details>
<summary><b>Releasing</b></summary>

1. Set `version` in `pyproject.toml` and `__version__` in `src/flightbyte/_version.py`; a test fails if they differ.
2. Give the version its own `## <version>` section in `CHANGELOG.md`.
3. Push a tag such as `v1.0.1`.

The release workflow checks that the tag, `pyproject.toml` and `_version.py` agree and that the changelog has the section, runs every check, builds the sdist and wheel once, publishes them to PyPI with trusted publishing unless that version is already there, and creates the GitHub release from the changelog section with the files attached. Run it by hand from the Actions tab to rehearse: it builds and checks everything but publishes nothing.

</details>

## License

[MIT](https://github.com/FlightByte-dev/flightbyte-python/blob/main/LICENSE)

<br>

<p align="center">
  <a href="https://flightbyte.dev"><img src="https://raw.githubusercontent.com/FlightByte-dev/flightbyte-python/main/assets/icon.svg" alt="FlightByte" width="36"></a>
  <br>
  <sub><b>FlightByte</b> · Flight intelligence, byte by byte · <a href="https://flightbyte.dev">flightbyte.dev</a></sub>
</p>
