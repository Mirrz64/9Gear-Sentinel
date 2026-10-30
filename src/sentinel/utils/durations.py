"""Parse and format human-friendly durations such as "30m", "6h", "1d" or "1h30m"."""

from __future__ import annotations

import re
from datetime import timedelta

_UNIT_SECONDS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
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


def _counts(delta: timedelta) -> list[tuple[int, str]]:
    remaining = int(delta.total_seconds())
    counts = []
    for unit, size in _UNIT_SECONDS.items():
        count, remaining = divmod(remaining, size)
        counts.append((count, unit))
    return counts


def format_duration(delta: timedelta) -> str:
    """Exact and compact, e.g. 5400 seconds -> '1h30m'. Used for configured limits."""
    return "".join(f"{count}{unit}" for count, unit in _counts(delta) if count) or "0s"


def format_age(delta: timedelta) -> str:
    """The largest unit plus the next one down, e.g. '3d 1h', '19h', '2h 5m'.

    Used for measured ages, where seconds rarely matter once hours do.
    """
    counts = _counts(delta)
    for index, (count, unit) in enumerate(counts):
        if count:
            text = f"{count}{unit}"
            if index + 1 < len(counts) and counts[index + 1][0]:
                following, following_unit = counts[index + 1]
                text += f" {following}{following_unit}"
            return text
    return "0s"
