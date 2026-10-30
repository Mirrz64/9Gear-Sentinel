# Alerts

Sentinel alerts on a **change of state**:

- once when a check starts failing,
- once when it recovers (if you include `recovered`),
- and nothing in between, however many runs it stays broken.

A table that's stale all weekend produces one message on Saturday and one when it's fixed, not 48.

## Choose what to hear about

```yaml
alerts:
  notify_on: [fail, error, recovered]
```

| Value | Alerts when |
| --- | --- |
| `fail` | An error-severity check fails |
| `error` | A check can't run (bad SQL, missing table, unreachable database) |
| `warn` | A warn-severity check fails |
| `recovered` | A check that had alerted passes again |

The default is `[fail, error]`.

## Slack

Create an app at api.slack.com, turn on **Incoming Webhooks**, add one to a channel and copy its URL.

```yaml
alerts:
  slack:
    webhook_url: ${SLACK_WEBHOOK_URL}
```

## Email

```yaml
alerts:
  email:
    smtp_host: smtp.gmail.com
    smtp_port: 587
    username: ${SMTP_USER}
    password: ${SMTP_PASSWORD}
    to: [data-team@example.com]
```

Port 465 connects with SSL. Other ports use STARTTLS unless `use_tls: false`.

## Test it

```bash
sentinel test-alert
```

This sends a test message to every configured channel and reports any failure. Use `sentinel run --no-alerts` when you want a quiet run.

!!! note
    Alert state comes from the results store. With `--no-store`, Sentinel can't see the previous run, so every problem alerts every time.
