## 1.0.0

- First release.
- `FlightByte` with `flights` (`get`, `timeline`), `subscriptions` (`create`, `list`, `list_all`, `get`, `update`, `delete`, `pause`, `resume`, `send_test`, `deliveries`, `events`, `secret`, `rotate_secret`) and `countries` (`list`, `get`, `flag_url`). Every method takes a `timeout` of its own.
- `TypedDict` types for every response, checked against the API's OpenAPI document. Responses come back exactly as the API sent them, as plain dicts.
- `FlightByteError` and a subclass for each error status, including the `credits_exhausted` reason of a 402 with its `balance` and `expires_at`, and `APIConnectionError` for requests that got no response. Every error survives pickling.
- `Webhook.verify`, `Webhook.is_valid`, `Webhook.construct_event` and `Webhook.sign` for `x-flightbyte-signature` webhook signatures, on the standard library's `hmac`.
- An empty webhook signing secret is refused with a `ValueError`, since anyone can sign with an empty key.
- `client.last_rate_limit` from the `X-RateLimit-*` headers, as an immutable `RateLimit`.
- Redirects to another origin, or from https to http, are never followed, so the API key stays with the API; a write is never sent twice.
- The timeout bounds the whole request, response body included.
- One client is safe to share across threads.
- No dependencies. Runs on Python 3.10 and later.
