"""Ash's live self-inspection.

Her documentation tells her how she is *supposed* to work; this tells her how
she is actually running right now. Together they let her diagnose herself:
the docs say "check whether the task is enabled and when it last ran", this
reports that it is enabled and last ran three days ago.

Read-only by construction. It runs no shell command that can change anything,
and it never returns a secret — only whether one is configured.
"""

import os
import socket
import subprocess
from datetime import timedelta

LOG_TAIL_LINES = 12
MAX_LOG_CHARS = 700


def _ports() -> str:
    live = []
    for name, port in (("backend", 8000), ("frontend", 5173)):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                live.append(f"{name}:{port} up")
        except OSError:
            live.append(f"{name}:{port} DOWN")
    return ", ".join(live)


def _cron() -> list:
    """Ash's own crontab entries. `crontab -l` cannot modify anything."""
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception as e:  # noqa: BLE001
        return [f"could not read crontab: {e}"]
    lines = [l.strip() for l in out.splitlines()
             if l.strip() and not l.strip().startswith("#")]
    mine = [l for l in lines if "ASH" in l or "manage.py" in l]
    return mine or ["no Ash entries in crontab — nothing will fire"]


def _log_tail() -> str:
    from django.conf import settings
    path = os.path.join(settings.BASE_DIR, "logs", "scheduler.log")
    if not os.path.exists(path):
        return "scheduler.log does not exist — the cron jobs have never run"
    try:
        with open(path) as f:
            lines = f.readlines()[-LOG_TAIL_LINES:]
    except Exception as e:  # noqa: BLE001
        return f"could not read scheduler.log: {e}"
    age = _age(os.path.getmtime(path))
    tail = "".join(lines)[-MAX_LOG_CHARS:].strip()
    return f"last written {age} ago:\n{tail}"


def _age(timestamp) -> str:
    import time
    secs = int(time.time() - timestamp)
    if secs < 90:
        return f"{secs}s"
    if secs < 5400:
        return f"{secs // 60}m"
    if secs < 172800:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def collect() -> str:
    """One readable report of Ash's current running state."""
    from django.conf import settings
    from django.db import connection
    from django.utils import timezone

    from .llm import MODELS
    from . import engine as eng
    from .models import (Memory, Message, ScheduledTask, SelfChunk, Task)

    out = []

    # --- processes and configuration -------------------------------------
    out.append(f"PROCESSES: {_ports()}")
    out.append("MODELS: " + ", ".join(f"{r}={m}" for r, m in MODELS.items()))
    out.append(
        f"LIMITS: reply cap {eng.MAX_REPLY_TOKENS} tokens, "
        f"history budget {eng.HISTORY_BUDGET_CHARS} chars"
    )
    out.append(
        "KEYS: " + ", ".join(
            f"{name}={'set' if os.getenv(env) or getattr(settings, env, '') else 'MISSING'}"
            for name, env in (("groq", "GROQ_API_KEY"),
                              ("tavily", "TAVILY_API_KEY"),
                              ("discord", "DISCORD_WEBHOOK_URL"))
        )
    )

    # --- database ---------------------------------------------------------
    try:
        with connection.cursor() as c:
            c.execute("select pg_is_in_recovery()")
            read_only = c.fetchone()[0]
        db = "READ-ONLY (replica — writes will fail)" if read_only else "writable"
    except Exception as e:  # noqa: BLE001
        db = f"unreachable: {e}"
    out.append(
        f"DATABASE: {settings.DATABASES['default']['NAME']} on "
        f"{settings.DATABASES['default']['HOST']}, {db}"
    )
    out.append(
        f"ROWS: {Message.objects.count()} messages, {Memory.objects.count()} memories, "
        f"{Task.objects.count()} tasks, {ScheduledTask.objects.count()} scheduled"
    )

    # --- scheduler --------------------------------------------------------
    out.append("CRON:\n  " + "\n  ".join(_cron()))

    now = timezone.now()
    tasks = list(ScheduledTask.objects.all())
    if tasks:
        lines = []
        for t in tasks:
            when = _age(t.last_run.timestamp()) + " ago" if t.last_run else "never"
            state = "enabled" if t.enabled else "DISABLED"
            lines.append(f"  '{t.name}' [{t.cron_schedule}] {state}, "
                         f"last ran {when}, status {t.last_status}")
        out.append("SCHEDULED TASKS:\n" + "\n".join(lines))
    else:
        out.append("SCHEDULED TASKS: none exist")

    overdue = Task.objects.filter(
        status="pending", deadline__lt=now, deadline_notified=False).count()
    soon = Task.objects.filter(
        status="pending", deadline__gte=now,
        deadline__lte=now + timedelta(hours=24)).count()
    out.append(f"DEADLINES: {overdue} overdue not yet alerted, {soon} due within 24h")

    out.append("SCHEDULER LOG: " + _log_tail())

    # --- self-knowledge index --------------------------------------------
    chunks = SelfChunk.objects.count()
    if not chunks:
        out.append("SELF-KNOWLEDGE: no chunks indexed — run manage.py index_self")
    else:
        newest = SelfChunk.objects.order_by("-indexed_at").first().indexed_at
        doc = os.path.join(os.path.dirname(settings.BASE_DIR), "docs", "ASH_SELF.md")
        stale = os.path.exists(doc) and os.path.getmtime(doc) > newest.timestamp()
        out.append(
            f"SELF-KNOWLEDGE: {chunks} chunks, indexed {_age(newest.timestamp())} ago"
            + (" — STALE, the document changed since; run manage.py index_self"
               if stale else "")
        )

    return "\n".join(out)


def provider_headroom() -> str:
    """Remaining Groq allowance for the conversation model, right now."""
    from .llm import MODELS, client
    try:
        r = client.chat.completions.with_raw_response.create(
            model=MODELS["conversation"],
            messages=[{"role": "user", "content": "ok"}],
            max_tokens=1,
        )
        h = r.headers
        return (f"PROVIDER: {h.get('x-ratelimit-remaining-tokens')} of "
                f"{h.get('x-ratelimit-limit-tokens')} tokens left this window, "
                f"resets in {h.get('x-ratelimit-reset-tokens')}")
    except Exception as e:  # noqa: BLE001
        return f"PROVIDER: could not check ({str(e)[:120]})"
