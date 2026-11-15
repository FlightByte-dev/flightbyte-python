"""Reading the wrappers some endpoints put around their answer."""

from __future__ import annotations

from typing import Any

from ._errors import FlightByteError


def data_of(result: Any, operation: str) -> list[Any]:
    """The ``data`` list of a ``{"count": ..., "data": [...]}`` answer."""
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, list):
        raise FlightByteError(f"Expected a data list from {operation}, got: {_preview(result)}")
    return data


def string_of(result: Any, key: str, operation: str) -> str:
    """The string ``key`` of an object answer, such as ``{"secret": "..."}``."""
    value = result.get(key) if isinstance(result, dict) else None
    if not isinstance(value, str):
        raise FlightByteError(f"Expected {key} from {operation}, got: {_preview(result)}")
    return value


def _preview(value: Any) -> str:
    text = repr(value)
    return text[:200] + "..." if len(text) > 200 else text
