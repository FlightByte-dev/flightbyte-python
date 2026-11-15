"""Country names, emoji and flags."""

from __future__ import annotations

import builtins
from typing import cast

from ._models import Country
from ._transport import NOT_GIVEN, NotGiven, Transport, required
from ._util import data_of

__all__ = ["Countries"]


class Countries:
    """Country names, emoji and flags. Reach it as ``client.countries``."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list(
        self,
        *,
        lang: str | None = None,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> builtins.list[Country]:
        """Every country, sorted by name.

        ``lang`` is the language of the names, for example ``tr``; the API's
        default is ``en``.
        """
        result = self._transport.send("GET", ["countries"], query={"lang": lang}, timeout=timeout)
        return cast("builtins.list[Country]", data_of(result, "GET /countries"))

    def get(
        self,
        code: str,
        *,
        lang: str | None = None,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> Country:
        """One country by its ISO 3166-1 alpha-2 code."""
        result = self._transport.send(
            "GET", ["countries", required("code", code)], query={"lang": lang}, timeout=timeout
        )
        return cast(Country, result)

    def flag_url(self, code: str, *, square: bool = False) -> str:
        """The URL of a country's SVG flag: 4:3, or 1:1 with ``square``.

        Flags need no API key, so the URL can go straight into an ``<img>``.
        Nothing is sent.
        """
        return self._transport.url(
            ["flags", f"{required('code', code).lower()}.svg"],
            {"shape": "1x1" if square else None},
        )
