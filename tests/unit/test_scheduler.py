from datetime import datetime, timedelta

import pytest

from sentinel.scheduler import CronError, CronSchedule, watch_loop

MONDAY = datetime(2026, 11, 2, 10, 17)


@pytest.mark.parametrize(
    ("expression", "after", "expected"),
    [
        ("* * * * *", MONDAY, datetime(2026, 11, 2, 10, 18)),
        ("0 * * * *", MONDAY, datetime(2026, 11, 2, 11, 0)),
        ("*/15 * * * *", MONDAY, datetime(2026, 11, 2, 10, 30)),
        ("0,30 * * * *", MONDAY, datetime(2026, 11, 2, 10, 30)),
        ("30 9 * * *", MONDAY, datetime(2026, 11, 3, 9, 30)),
        ("0 9 * * 1-5", datetime(2026, 11, 6, 10, 0), datetime(2026, 11, 9, 9, 0)),
        ("0 0 1 * *", MONDAY, datetime(2026, 12, 1, 0, 0)),
        ("0 0 29 2 *", MONDAY, datetime(2028, 2, 29, 0, 0)),
        ("0 0 * * 0", MONDAY, datetime(2026, 11, 8, 0, 0)),
        ("0 0 * * 7", MONDAY, datetime(2026, 11, 8, 0, 0)),
        ("0 0 1 * 1", datetime(2026, 11, 2, 1, 0), datetime(2026, 11, 9, 0, 0)),
    ],
)
def test_next_after(expression: str, after: datetime, expected: datetime) -> None:
    assert CronSchedule.parse(expression).next_after(after) == expected


def test_steps_and_ranges() -> None:
    assert CronSchedule.parse("5-10/2 * * * *").minutes == {5, 7, 9}
    assert CronSchedule.parse("5/20 * * * *").minutes == {5, 25, 45}


@pytest.mark.parametrize(
    "expression",
    ["* * * *", "60 * * * *", "*/0 * * * *", "a * * * *", "10-5 * * * *", "* * 0 * *"],
)
def test_invalid_expressions(expression: str) -> None:
    with pytest.raises(CronError):
        CronSchedule.parse(expression)


def test_schedule_that_never_fires() -> None:
    with pytest.raises(CronError):
        CronSchedule.parse("0 0 31 2 *").next_after(MONDAY)


def test_watch_loop_runs_on_schedule() -> None:
    clock = [datetime(2026, 11, 2, 10, 17, 30)]
    runs: list[datetime] = []
    waits: list[datetime] = []

    def advance(seconds: float) -> None:
        clock[0] += timedelta(seconds=seconds)

    done = watch_loop(
        CronSchedule.parse("*/5 * * * *"),
        lambda: runs.append(clock[0]),
        on_wait=waits.append,
        now=lambda: clock[0],
        sleep=advance,
        max_runs=3,
    )
    assert done == 3
    expected = [datetime(2026, 11, 2, 10, minute) for minute in (20, 25, 30)]
    assert runs == expected
    assert waits == expected
