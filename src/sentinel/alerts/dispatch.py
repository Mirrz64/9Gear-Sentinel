"""Format alert events and send them to every configured channel."""

from __future__ import annotations

from collections.abc import Sequence

from sentinel.alerts import emailer, slack
from sentinel.alerts.errors import AlertError
from sentinel.alerts.events import AlertEvent, headline
from sentinel.config.models import Alerts


def channels(settings: Alerts) -> list[str]:
    names = []
    if settings.slack:
        names.append("Slack")
    if settings.email:
        names.append("email")
    return names


def send_alerts(settings: Alerts, events: Sequence[AlertEvent]) -> list[str]:
    """Send one message per channel for this run. Returns a list of failures."""
    if not events:
        return []
    title = headline(events)
    lines = [event.line() for event in events]
    return _send(settings, title, lines)


def send_test_alert(settings: Alerts) -> list[str]:
    return _send(
        settings,
        "9Gear Sentinel: test alert",
        ["If you can read this, alerts are configured correctly."],
    )


def _send(settings: Alerts, title: str, lines: list[str]) -> list[str]:
    failures: list[str] = []
    if settings.slack:
        text = f"*{title}*\n" + "\n".join(f"- {line}" for line in lines)
        try:
            slack.send(settings.slack.webhook_url, text)
        except AlertError as exc:
            failures.append(str(exc))
    if settings.email:
        try:
            emailer.send(settings.email, title, "\n".join(lines) + "\n")
        except AlertError as exc:
            failures.append(str(exc))
    return failures
