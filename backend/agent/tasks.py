"""
Scheduled-task execution for Ash.

Design: beat ticks dispatch_due_tasks() once a minute. That figures out which
ScheduledTasks are due (via their own cron_schedule) and hands each off to
execute_scheduled_task(). The real work lives in plain functions
(run_due_scheduled_tasks / _run_task) so they can be unit-tested and run from a
management command without a broker.

A task's `action` is a small JSON blob:
    {"type": "chat", "prompt": "..."}       -> run the prompt through the agent
    {"type": "briefing"}                    -> generate the morning briefing
"""

from celery import shared_task
from django.db import transaction
from django.utils import timezone


def _is_due(cron_schedule: str, last_run, now) -> bool:
    """True if the most recent cron fire time is newer than last_run.

    Cron fields are interpreted in the project timezone (settings.TIME_ZONE,
    Asia/Karachi) so "0 8 * * *" means 08:00 PKT. last_run is stored in UTC;
    comparing two timezone-aware datetimes compares absolute instants, so the
    mixed zones are fine.
    """
    from croniter import croniter

    if not croniter.is_valid(cron_schedule):
        return False
    local_now = timezone.localtime(now)  # convert to settings.TIME_ZONE
    prev_fire = croniter(cron_schedule, local_now).get_prev(type(local_now))
    return last_run is None or last_run < prev_fire


def _run_task(task) -> str:
    """Execute one ScheduledTask's action and persist the outcome."""
    from .engine import AgentEngine

    action = task.action or {}

    try:
        base = action.get("prompt") or action.get("message") or task.name
        # Scheduled replies go straight to a phone notification, so ask for
        # something short.
        prompt = (base + "\n\n(This is a scheduled reminder — reply in 1-2 "
                  "short lines suitable for a phone notification.)")
        engine = AgentEngine(user=task.user)
        reply = engine.chat(prompt)
        # If Ash already fired a notify() during the run, don't double-push.
        already_notified = getattr(engine, "notified", False)
        notif_title = task.name or "Ash 🤖"

        task.last_run = timezone.now()
        task.last_status = "ok"
        task.last_result = (reply or "")[:2000]
        task.save(update_fields=["last_run", "last_status", "last_result"])

        # Push the result to the user's phone (no-op if they haven't subscribed).
        if not already_notified:
            try:
                from .notifications import send_push
                send_push(task.user, notif_title, reply or "", url="/")
            except Exception:
                pass

        return reply
    except Exception as e:
        task.last_run = timezone.now()
        task.last_status = "error"
        task.last_result = str(e)[:2000]
        task.save(update_fields=["last_run", "last_status", "last_result"])
        raise


def run_due_scheduled_tasks(sync: bool = False) -> dict:
    """Find every enabled ScheduledTask that is due and run it.

    Plain function so it can be called from a Django shell, a management
    command, or tests. In production dispatch_due_tasks() wraps this on beat and
    dispatches each task to a worker; with sync=True the tasks run inline (used
    by the `run_scheduled` management command / cron mode, no broker needed).
    """
    from .models import ScheduledTask

    now = timezone.now()
    fired = []
    # Ash's laptop and server share one database, so a naive query-then-fire
    # would let both instances run the same task. We claim each due task under
    # a row lock (skip_locked so instances don't block each other) and re-check
    # due-ness inside the lock — the first to stamp last_run wins, the second
    # sees the fresh last_run and backs off.
    candidate_ids = list(
        ScheduledTask.objects.filter(enabled=True).values_list("id", flat=True)
    )
    for tid in candidate_ids:
        with transaction.atomic():
            task = (
                ScheduledTask.objects
                .select_for_update(skip_locked=True)
                .filter(id=tid, enabled=True)
                .first()
            )
            if task is None:
                continue  # locked by the other instance, or deleted
            if not _is_due(task.cron_schedule, task.last_run, now):
                continue
            task.last_run = now
            task.save(update_fields=["last_run"])
        # Dispatch outside the lock so a slow LLM run doesn't hold the row.
        if sync:
            _run_task(task)
        else:
            execute_scheduled_task.delay(task.id)
        fired.append(task.id)
    return {"checked_at": now.isoformat(), "fired": fired}


def run_deadline_checks() -> dict:
    """Push a one-time alert for each pending task within 24h of its deadline
    (or already overdue). deadline_notified guards against repeat alerts."""
    from datetime import timedelta
    from .models import Task
    from .notifications import send_push

    now = timezone.now()
    horizon = now + timedelta(hours=24)
    alerted = []
    due_soon = Task.objects.filter(
        status="pending",
        deadline__isnull=False,
        deadline__lte=horizon,
        deadline_notified=False,
    )
    for t in due_soon:
        when = timezone.localtime(t.deadline).strftime("%b %d, %H:%M")
        if t.deadline < now:
            body = f"⏰ Overdue: '{t.title}' was due {when}."
        else:
            secs = (t.deadline - now).total_seconds()
            hours, mins = int(secs // 3600), int((secs % 3600) // 60)
            eta = f"{hours}h {mins}m" if hours else f"{mins}m"
            body = f"⏰ '{t.title}' is due in {eta} ({when})."
        send_push(t.user, "Deadline reminder", body)
        t.deadline_notified = True
        t.save(update_fields=["deadline_notified"])
        alerted.append(t.id)
    return {"checked_at": now.isoformat(), "alerted": alerted}


@shared_task(name="agent.tasks.dispatch_due_tasks")
def dispatch_due_tasks():
    """Beat entrypoint — runs every minute."""
    return run_due_scheduled_tasks()


@shared_task(name="agent.tasks.check_deadlines")
def check_deadlines():
    """Beat entrypoint — runs periodically to alert on upcoming deadlines."""
    return run_deadline_checks()


@shared_task(name="agent.tasks.execute_scheduled_task")
def execute_scheduled_task(task_id: int):
    """Run a single ScheduledTask by id."""
    from .models import ScheduledTask

    try:
        task = ScheduledTask.objects.get(id=task_id, enabled=True)
    except ScheduledTask.DoesNotExist:
        return f"ScheduledTask {task_id} not found or disabled"
    return _run_task(task)
