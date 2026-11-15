# Contributing

Thanks for helping. Bug reports, fixes and docs improvements are all welcome. For a change to the public API, open an issue first so we can agree on the shape before you write it.

## Set up

Using and developing the package both need Python 3.10 or later.

```bash
git clone https://github.com/FlightByte-dev/flightbyte-python.git
cd flightbyte-python
python -m venv .venv && source .venv/bin/activate
pip install -e . -r requirements-dev.txt
python -m unittest discover -s tests -t .
```

The tests never touch the real API and need no key.

## Before you open a pull request

```bash
ruff check .
ruff format --check .
mypy --strict src tests
python -m unittest discover -s tests -t .
python -m build && twine check --strict dist/*
```

CI runs the same checks on Python 3.10, 3.11, 3.12, 3.13 and 3.14, then installs the built wheel in a clean environment and runs the tests against it. A pull request needs all of it green.

- **The package uses the standard library only.** No runtime dependencies, not even `typing_extensions`; keep it that way unless an issue agrees otherwise.
- **The code runs on Python 3.10.** `ruff` and `mypy` are set to 3.10, so syntax or a standard library API from a later version fails the checks. `typing.NotRequired` is 3.11, which is why the models split their optional keys into a `total=False` class.
- **Everything public has a docstring.** It shows in editors and with `help()`. `ruff` checks it.
- **Every change has a test.** Requests go to a fake API on `127.0.0.1` (see `tests/helpers.py`), never to the network; a test that tries fails.
- **Add a line to `CHANGELOG.md`** under a `## Unreleased` heading for anything a user would notice.

## How the code maps to the API

The types mirror the API's [OpenAPI document](https://flightbyte.dev/openapi.json), and `tests/test_spec.py` checks them against a copy of it in `spec/openapi.json`. Refresh that copy and see what changed:

```bash
python scripts/sync_openapi.py
python -m unittest discover -s tests -t .
```

- **The API adds a field:** add it to the `TypedDict` in `src/flightbyte/_models.py`. A key the API may leave out goes in the `total=False` class; one it may send as `null` includes `None`. The spec test fails until you do, and fails if a key has no place in the document unless it is listed, with the reason, in `UNDOCUMENTED_FIELDS`.
- **The API adds an enum value** (a phase, status, change type or event type): add it to its tuple in `src/flightbyte/_models.py`. Until then the value is still a valid string, which is why nothing breaks for users in the meantime.
- **The API adds an error code or status:** map it in `src/flightbyte/_errors.py` and add a case to `tests/test_errors.py`.
- **The API adds an endpoint:** add a method to the resource in `src/flightbyte/`, a line to `CALLS` in `tests/test_spec.py`, a test in `tests/test_resources.py`, and a row to the README's API tables.

## Webhook signatures

`tests/fixtures/webhook_vectors.json` holds signatures made with Node's `createHmac`, exactly as the API signs deliveries, so the Python verifier is checked against the server and not only against itself. Do not edit those files by hand. To regenerate them, for example after adding a case to the script:

```bash
node tool/webhook_vectors.mjs
```

## Commit messages

One line that says what changed and why it matters, in plain words, for example `Subscriptions can be listed by origin airport`. Add a body when the reason is not obvious from the diff.

## Releasing

Maintainers only.

1. Set `version` in `pyproject.toml` and `__version__` in `src/flightbyte/_version.py`; a test fails if they differ.
2. Rename `## Unreleased` in `CHANGELOG.md` to the new version.
3. Push a tag `v<version>`, for example `v1.0.1`.

The release workflow checks that the tag, `pyproject.toml` and `_version.py` agree and that the changelog has the section, runs every check, builds the sdist and wheel, publishes them to PyPI with trusted publishing unless that version is already there, and creates the GitHub release from the version's `CHANGELOG.md` section. To rehearse a release without publishing anything, run the workflow by hand from the Actions tab.

A version on PyPI can never be uploaded again, even after it is deleted. Fix a bad release with a new version.

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
