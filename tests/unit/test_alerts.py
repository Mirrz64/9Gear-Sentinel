import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from sentinel.alerts import compute_events, send_alerts, send_test_alert
from sentinel.alerts.errors import AlertError
from sentinel.cli import app
from sentinel.config.models import Alerts, EmailAlert, SlackAlert
from sentinel.runner import CheckResult

runner = CliRunner()


def result(status: str, key: str = "k1") -> CheckResult:
    outcome, severity = {
        "PASS": ("pass", "error"),
        "FAIL": ("fail", "error"),
        "WARN": ("fail", "warn"),
        "ERROR": ("error", "error"),
        "SKIP": ("skipped", "error"),
    }[status]
    return CheckResult(
        source="src",
        table="orders",
        check_type="unique",
        check_key=key,
        label="unique(order_id)",
        severity=severity,
        outcome=outcome,  # type: ignore[arg-type]
        observed=None,
        message="3 duplicate keys",
        duration_ms=1,
    )


def lookup(previous: str | None) -> Any:
    return lambda key: previous


DEFAULT = ["fail", "error"]
WITH_RECOVERY = ["fail", "error", "recovered"]


class TestComputeEvents:
    def test_new_failure_alerts(self) -> None:
        (event,) = compute_events([result("FAIL")], lookup(None), DEFAULT)
        assert event.kind == "problem"
        assert event.line().startswith("FAIL  orders  unique(order_id)")

    def test_still_failing_is_quiet(self) -> None:
        assert compute_events([result("FAIL")], lookup("FAIL"), DEFAULT) == []

    def test_pass_to_fail_alerts(self) -> None:
        assert len(compute_events([result("FAIL")], lookup("PASS"), DEFAULT)) == 1

    def test_warnings_only_when_asked(self) -> None:
        assert compute_events([result("WARN")], lookup(None), DEFAULT) == []
        assert len(compute_events([result("WARN")], lookup(None), ["warn"])) == 1

    def test_recovery_only_when_asked(self) -> None:
        assert compute_events([result("PASS")], lookup("FAIL"), DEFAULT) == []
        (event,) = compute_events([result("PASS")], lookup("FAIL"), WITH_RECOVERY)
        assert event.kind == "recovered"
        assert event.line().startswith("RECOVERED")

    def test_recovery_from_unnotified_status_is_quiet(self) -> None:
        assert compute_events([result("PASS")], lookup("WARN"), WITH_RECOVERY) == []

    def test_passing_and_skipped_are_quiet(self) -> None:
        assert compute_events([result("PASS"), result("SKIP")], lookup(None), DEFAULT) == []


class FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


@pytest.fixture
def slack_messages(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
        sent.append(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr("sentinel.alerts.slack.urlopen", fake_urlopen)
    return sent


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port = host, port
        self.tls = False
        self.login_args: tuple[str, str] | None = None
        self.messages: list[Any] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def starttls(self) -> None:
        self.tls = True

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def send_message(self, message: Any) -> None:
        self.messages.append(message)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.instances = []
    monkeypatch.setattr("sentinel.alerts.emailer.smtplib.SMTP", FakeSMTP)
    return FakeSMTP


def test_slack_message_content(slack_messages: list[dict[str, Any]]) -> None:
    settings = Alerts(slack=SlackAlert(webhook_url="https://hooks.example.com/x"))
    events = compute_events([result("FAIL")], lookup(None), DEFAULT)
    assert send_alerts(settings, events) == []
    (message,) = slack_messages
    assert message["text"].startswith("*9Gear Sentinel: 1 new problem*")
    assert "unique(order_id)" in message["text"]


def test_slack_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sentinel.alerts.slack.urlopen", lambda request, timeout: FakeResponse(status=500)
    )
    settings = Alerts(slack=SlackAlert(webhook_url="https://hooks.example.com/x"))
    (failure,) = send_test_alert(settings)
    assert "HTTP 500" in failure


def test_slack_bad_url_raises_alert_error() -> None:
    from sentinel.alerts import slack

    with pytest.raises(AlertError):
        slack.send("not-a-url", "hi")


def test_email_is_sent_with_tls_and_login(smtp: type[FakeSMTP]) -> None:
    settings = Alerts(
        email=EmailAlert(
            smtp_host="smtp.example.com",
            username="bot@example.com",
            password="secret",
            to=["team@example.com"],
        )
    )
    assert send_test_alert(settings) == []
    (server,) = smtp.instances
    assert server.tls
    assert server.login_args == ("bot@example.com", "secret")
    (message,) = server.messages
    assert message["Subject"] == "9Gear Sentinel: test alert"
    assert message["To"] == "team@example.com"


def write_config(
    tmp_path: Path, demo_db: Path, notify_on: str = "[fail, error, recovered]"
) -> Path:
    path = tmp_path / "sentinel.yml"
    path.write_text(
        "version: 1\n"
        "sources:\n"
        "  local:\n"
        "    type: sqlite\n"
        f"    url: sqlite:///{demo_db.as_posix()}\n"
        "store:\n"
        f"  url: sqlite:///{(tmp_path / 'results.db').as_posix()}\n"
        "alerts:\n"
        f"  notify_on: {notify_on}\n"
        "  slack:\n"
        "    webhook_url: https://hooks.example.com/x\n"
        "tables:\n"
        "  - source: local\n"
        "    table: orders\n"
        "    checks:\n"
        "      - unique: { columns: [order_id] }\n",
        encoding="utf-8",
    )
    return path


def test_alerts_fire_once_then_on_recovery(
    tmp_path: Path, demo_db: Path, slack_messages: list[dict[str, Any]]
) -> None:
    config = str(write_config(tmp_path, demo_db))

    runner.invoke(app, ["run", "-c", config])
    assert len(slack_messages) == 1
    assert "1 new problem" in slack_messages[0]["text"]

    runner.invoke(app, ["run", "-c", config])
    assert len(slack_messages) == 1  # still failing: no repeat

    conn = sqlite3.connect(demo_db)
    conn.execute(
        "DELETE FROM orders WHERE rowid NOT IN (SELECT min(rowid) FROM orders GROUP BY order_id)"
    )
    conn.commit()
    conn.close()

    recovered = runner.invoke(app, ["run", "-c", config])
    assert recovered.exit_code == 0, recovered.output
    assert len(slack_messages) == 2
    assert "1 recovered" in slack_messages[1]["text"]


def test_no_alerts_flag(
    tmp_path: Path, demo_db: Path, slack_messages: list[dict[str, Any]]
) -> None:
    runner.invoke(app, ["run", "-c", str(write_config(tmp_path, demo_db)), "--no-alerts"])
    assert slack_messages == []


def test_test_alert_command(
    tmp_path: Path, demo_db: Path, slack_messages: list[dict[str, Any]]
) -> None:
    result = runner.invoke(app, ["test-alert", "-c", str(write_config(tmp_path, demo_db))])
    assert result.exit_code == 0, result.output
    assert "test alert sent via Slack" in result.output
    assert "test alert" in slack_messages[0]["text"]
