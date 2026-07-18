"""
Notifications — delivered to a private Discord channel via webhook.

Everything routes through send_notification(user, title, body). A webhook is a
single HTTPS POST to a URL Discord gives you (Channel → Integrations →
Webhooks), so there's nothing to subscribe to, install, or keep alive — far more
reliable than the previous Web Push path.

Set DISCORD_WEBHOOK_URL in .env. If it's unset, notifications are a safe no-op.
`user` is accepted for signature compatibility but unused (single channel,
single user). `send_push` is kept as an alias so existing callers keep working.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Ash's maroon, used for the Discord embed accent.
_ASH_COLOR = 0x8B1E2D


def send_notification(user, title: str, body: str, url: str = "/") -> int:
    """Post a notification to the configured Discord webhook.

    Returns 1 if Discord accepted it, 0 otherwise (missing URL or error).
    """
    webhook = getattr(settings, "DISCORD_WEBHOOK_URL", "")
    if not webhook:
        logger.warning("notification skipped: DISCORD_WEBHOOK_URL not set")
        return 0

    payload = {
        "username": "Ash",
        "embeds": [{
            "title": (title or "Ash")[:256],
            "description": (body or "")[:4000],
            "color": _ASH_COLOR,
        }],
    }
    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            return 1
        logger.warning("Discord webhook failed: %s %s",
                       resp.status_code, resp.text[:200])
        return 0
    except Exception as e:  # noqa: BLE001 - never let a failed notify break a task
        logger.warning("Discord webhook error: %s", e)
        return 0


# Backwards-compatible alias — scheduler, deadline-watcher and the notify tool
# all call send_push().
send_push = send_notification
