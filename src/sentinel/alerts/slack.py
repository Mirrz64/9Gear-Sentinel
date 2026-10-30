"""Post a message to a Slack incoming webhook (standard library only)."""

from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from sentinel.alerts.errors import AlertError


def send(webhook_url: str, text: str, timeout: float = 10) -> None:
    try:
        request = Request(
            webhook_url,
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=timeout) as response:
            status = int(response.status)
    except (URLError, OSError, ValueError) as exc:
        raise AlertError(f"Slack webhook failed: {getattr(exc, 'reason', exc)}") from None
    if status >= 300:
        raise AlertError(f"Slack webhook returned HTTP {status}")
