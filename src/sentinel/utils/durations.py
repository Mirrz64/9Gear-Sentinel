"""Parse human-friendly durations such as "30m", "6h", "1d" or "1h30m"."""

from __future__ import annotations

import re
from datetime import timedelta

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_PART = re.compile(r"(\d+)([smhdw])")


def parse_duration(value: object) -> timedelta:
    """Return a timedelta for a duration string, or an int number of seconds.

    Raises ValueError with a message suitable for showing to the user.
    """
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
    elif isinstance(value, bool):
        raise ValueError("duration must be text like 6h or 30m, not true/false")
    elif isinstance(value, int):
        seconds = value
    elif isinstance(value, str):
        text = value.strip().lower().replace(" ", "")
        if not text:
            raise ValueError("duration is empty; use forms like 30m, 6h, 1d or 1h30m")
        seconds = 0
        position = 0
        for match in _PART.finditer(text):
            if match.start() != position:
                break
            seconds += int(match.group(1)) * _UNIT_SECONDS[match.group(2)]
            position = match.end()
        if position != len(text):
            raise ValueError(f"invalid duration '{value}'; use forms like 30m, 6h, 1d or 1h30m")
    else:
        raise ValueError("duration must be text like 6h or 30m")

    if seconds <= 0:
        raise ValueError("duration must be greater than zero")
    return timedelta(seconds=seconds)


def format_duration(delta: timedelta) -> str:
    """Render a timedelta compactly, e.g. 5400 seconds -> '1h30m'."""
    remaining = int(delta.total_seconds())
    if remaining <= 0:
        return "0s"
    parts = []
    for unit in ("w", "d", "h", "m", "s"):
        size = _UNIT_SECONDS[unit]
        count, remaining = divmod(remaining, size)
        if count:
            parts.append(f"{count}{unit}")
    return "".join(parts)
