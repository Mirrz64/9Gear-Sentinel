"""Decide which results deserve an alert.

Alerts fire on a change of state, not on every run: once when a check starts
failing, and once when it recovers. A check that fails hourly for a day sends
one message, not twenty-four.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from typing import Literal

from sentinel.runner import CheckResult

StatusLookup = Callable[[str], str | None]

# Display status -> the notify_on keyword that enables alerts for it.
_PROBLEM_KINDS = {"FAIL": "fail", "ERROR": "error", "WARN": "warn"}


@dataclass(frozen=True)
class AlertEvent:
    kind: Literal["problem", "recovered"]
    result: CheckResult
    previous_status: str | None

    def line(self) -> str:
        r = self.result
        label = "RECOVERED" if self.kind == "recovered" else r.status
        return f"{label}  {r.table}  {r.label}: {r.message}"


def compute_events(
    results: Sequence[CheckResult],
    previous_status: StatusLookup,
    notify_on: Collection[str],
) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    for result in results:
        if result.status == "SKIP":
            continue
        previous = previous_status(result.check_key)
        kind = _PROBLEM_KINDS.get(result.status)

        if kind is not None:
            if kind in notify_on and previous != result.status:
                events.append(AlertEvent("problem", result, previous))
        elif (
            result.status == "PASS"
            and "recovered" in notify_on
            and previous in _PROBLEM_KINDS
            and _PROBLEM_KINDS[previous] in notify_on
        ):
            events.append(AlertEvent("recovered", result, previous))
    return events


def headline(events: Sequence[AlertEvent]) -> str:
    problems = sum(1 for event in events if event.kind == "problem")
    recovered = len(events) - problems
    parts = []
    if problems:
        parts.append(f"{problems} new problem{'s' if problems != 1 else ''}")
    if recovered:
        parts.append(f"{recovered} recovered")
    return "9Gear Sentinel: " + ", ".join(parts)
