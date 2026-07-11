"""
Celery app for Ash.

Broker/result backend come from CELERY_BROKER_URL / CELERY_RESULT_BACKEND
(already in .env, pointing at Redis). The beat schedule below ticks once a
minute and fires any ScheduledTask that is due — see agent/tasks.py.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ash.settings")

app = Celery("ash")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Tick every minute; the dispatcher decides which ScheduledTasks are actually
# due based on each task's own cron_schedule.
app.conf.beat_schedule = {
    "dispatch-scheduled-tasks-every-minute": {
        "task": "agent.tasks.dispatch_due_tasks",
        "schedule": crontab(minute="*"),
    },
}
