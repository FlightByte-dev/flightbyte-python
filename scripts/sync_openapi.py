"""Refreshes the vendored OpenAPI document that tests/test_spec.py checks the
client and its types against.

    python scripts/sync_openapi.py [<url>]   (default https://flightbyte.dev/openapi.json)
"""

import json
import sys
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://flightbyte.dev/openapi.json"
TARGET = Path(__file__).resolve().parent.parent / "spec" / "openapi.json"


def main(argv: list[str]) -> int:
    url = argv[0] if argv else DEFAULT_URL
    request = urllib.request.Request(url, headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            spec = json.load(response)
    except OSError as error:
        print(f"GET {url} failed: {error}", file=sys.stderr)
        return 1
    except ValueError:
        print(f"{url} did not answer with JSON", file=sys.stderr)
        return 1
    if (
        not isinstance(spec, dict)
        or not isinstance(spec.get("openapi"), str)
        or not isinstance(spec.get("paths"), dict)
    ):
        print(f"{url} is not an OpenAPI document", file=sys.stderr)
        return 1
    TARGET.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    operations = [
        op
        for ops in spec["paths"].values()
        for op in ops.values()
        if isinstance(op, dict) and "operationId" in op
    ]
    version = spec.get("info", {}).get("version")
    print(
        f"Wrote spec/openapi.json: {len(operations)} operations, version {version}. "
        "Run the tests to check the client against it.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
