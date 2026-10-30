"""A small cron parser and the loop behind `sentinel watch` (standard library only).

Supports the usual five fields (minute hour day-of-month month day-of-week) with
`*`, numbers, ranges `a-b`, lists `a,b` and steps `*/n` or `a-b/n`. Day of week
is 0-6 with 0 (or 7) for Sunday. As in classic cron, when both day-of-month and
day-of-week are restricted, a day matching either one fires.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day of month", 1, 31),
    ("month", 1, 12),
    ("day of week", 0, 7),
)
_MAX_SEARCH = timedelta(days=4 * 366)


class CronError(ValueError):
    """The cron expression is malformed."""


@dataclass(frozen=True)
class CronSchedule:
    expression: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]  # 0 = Sunday
    day_restricted: bool
    weekday_restricted: bool

    @classmethod
    def parse(cls, expression: str) -> CronSchedule:
        parts = expression.split()
        if len(parts) != 5:
            raise CronError(f"cron needs 5 fields, got {len(parts)}: '{expression}'")
        values = [
            _parse_field(part, name, low, high)
            for part, (name, low, high) in zip(parts, _FIELDS, strict=True)
        ]
        weekdays = frozenset(0 if day == 7 else day for day in values[4])
        return cls(
            expression=expression,
            minutes=values[0],
            hours=values[1],
            days=values[2],
            months=values[3],
            weekdays=weekdays,
            day_restricted=parts[2] != "*",
            weekday_restricted=parts[4] != "*",
        )

    def _day_matches(self, moment: datetime) -> bool:
        cron_weekday = (moment.weekday() + 1) % 7  # Python: Monday=0; cron: Sunday=0
        in_days = moment.day in self.days
        in_weekdays = cron_weekday in self.weekdays
        if self.day_restricted and self.weekday_restricted:
            return in_days or in_weekdays
        return in_days and in_weekdays

    def matches(self, moment: datetime) -> bool:
        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and moment.month in self.months
            and self._day_matches(moment)
        )

    def next_after(self, moment: datetime) -> datetime:
        """The first matching minute strictly after ``moment``."""
        candidate = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = moment + _MAX_SEARCH
        while candidate <= limit:
            if candidate.month not in self.months or not self._day_matches(candidate):
                candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if candidate.hour not in self.hours:
                candidate = (candidate + timedelta(hours=1)).replace(minute=0)
                continue
            if candidate.minute in self.minutes:
                return candidate
            candidate += timedelta(minutes=1)
        raise CronError(f"'{self.expression}' never fires")


def _parse_field(text: str, name: str, low: int, high: int) -> frozenset[int]:
    values: set[int] = set()
    for item in text.split(","):
        base, _, step_text = item.partition("/")
        step = 1
        if step_text:
            if not step_text.isdigit() or int(step_text) == 0:
                raise CronError(f"invalid step '{step_text}' in {name} field")
            step = int(step_text)

        if base == "*":
            start, end = low, high
        elif "-" in base:
            start_text, _, end_text = base.partition("-")
            start, end = _number(start_text, name, low, high), _number(end_text, name, low, high)
            if start > end:
                raise CronError(f"range {base} is backwards in {name} field")
        else:
            start = _number(base, name, low, high)
            end = high if step_text else start
        values.update(range(start, end + 1, step))
    return frozenset(values)


def _number(text: str, name: str, low: int, high: int) -> int:
    if not text.isdigit():
        raise CronError(f"'{text}' is not a number in {name} field")
    value = int(text)
    if not low <= value <= high:
        raise CronError(f"{value} is out of range {low}-{high} in {name} field")
    return value


def watch_loop(
    schedule: CronSchedule,
    run_once: Callable[[], None],
    on_wait: Callable[[datetime], None] = lambda when: None,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    sleep: Callable[[float], None] = time.sleep,
    max_runs: int | None = None,
) -> int:
    """Run ``run_once`` at every scheduled time until interrupted. Returns runs done.

    Sleeps in short steps so a changed system clock or Ctrl+C is noticed quickly.
    """
    runs = 0
    while max_runs is None or runs < max_runs:
        due = schedule.next_after(now())
        on_wait(due)
        while (remaining := (due - now()).total_seconds()) > 0:
            sleep(min(remaining, 30))
        run_once()
        runs += 1
    return runs
