"""
Web Push notifications.

send_push(user, title, body) fans a notification out to every device the user
has subscribed. Expired subscriptions (HTTP 404/410 from the push service) are
deleted automatically so the table self-heals.

Requires VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY in settings (see
scripts/gen_vapid_keys.py). If they're unset, send_push is a safe no-op so the
rest of the app keeps working.
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def send_push(user, title: str, body: str, url: str = "/") -> int:
    """Send a push notification to all of *user*'s devices.

    Returns the number of devices successfully notified.
    """
    if not (settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY):
        logger.warning("send_push skipped: VAPID keys not configured")
        return 0

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.error("send_push skipped: pywebpush not installed")
        return 0

    from .models import PushSubscription

    payload = json.dumps({
        "title": title,
        "body": (body or "")[:500],
        "url": url,
    })

    sent = 0
    for sub in PushSubscription.objects.filter(user=user):
        try:
            webpush(
                subscription_info=sub.as_subscription_info(),
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                timeout=10,
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                # Subscription is dead — drop it.
                sub.delete()
                logger.info("Pruned expired push subscription %s", sub.id)
            else:
                logger.warning("Push to subscription %s failed: %s", sub.id, e)
        except Exception as e:  # noqa: BLE001 - never let a bad push break a task
            logger.warning("Push to subscription %s errored: %s", sub.id, e)
    return sent
