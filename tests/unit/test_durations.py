from datetime import timedelta

import pytest

from sentinel.utils.durations import format_duration, parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("45s", timedelta(seconds=45)),
        ("30m", timedelta(minutes=30)),
        ("6h", timedelta(hours=6)),
        ("1d", timedelta(days=1)),
        ("2w", timedelta(weeks=2)),
        ("1h30m", timedelta(hours=1, minutes=30)),
        (" 1H 30M ", timedelta(hours=1, minutes=30)),
        (90, timedelta(seconds=90)),
    ],
)
def test_parse_valid(text: object, expected: timedelta) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "6", "h", "6x", "1h-30m", "abc", "0h", 0, -5, True, 1.5])
def test_parse_invalid(text: object) -> None:
    with pytest.raises(ValueError):
        parse_duration(text)


def test_format_round_trip() -> None:
    assert format_duration(timedelta(hours=1, minutes=30)) == "1h30m"
    assert format_duration(parse_duration("2d6h")) == "2d6h"
    assert format_duration(timedelta(0)) == "0s"
