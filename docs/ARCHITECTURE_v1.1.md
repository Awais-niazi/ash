# Ash — Architecture Reference Addendum (v1.1)

This addendum updates `Ash_System_Architecture_Reference.pdf` (v1.0). Where they
disagree, **this file wins** — it reflects changes made in July 2026. Section
numbers refer to the v1.0 PDF.

---

## 1. Notifications — Web Push REMOVED, now Discord (supersedes any push mention)

Web Push (VAPID/service worker/PWA) was abandoned — it never reliably delivered
(HTTPS-origin, service-worker, iOS-install, and origin-bound-subscription
requirements each broke silently).

**Now:** all notifications post to a **private Discord channel via webhook**.

- `agent/notifications.py::send_notification(user, title, body)` — POSTs a maroon
  embed (username "Ash") to `settings.DISCORD_WEBHOOK_URL`. `send_push` is kept as
  an alias. Safe no-op if the URL is unset. Uses `requests` (no new deps).
- Config: `DISCORD_WEBHOOK_URL` in each machine's `.env` (Channel → Integrations
  → Webhooks). The server `.env` is the important one (that's where scheduled
  tasks / deadline alerts fire).
- **Removed:** `PushSubscription` model (dropped in migration 0009),
  `/api/push/*` endpoints, `client/public/sw.js`, `client/src/push.js`, the header
  bell button, `VAPID_*` settings, and the `pywebpush`/`py-vapid`/`http-ece` deps.
- **Kept:** `POST /api/notify/test/` — sends a test notification to Discord.

## 2. Scheduled Tasks — now fully wired (supersedes §6 "scaffolded, not wired")

`ScheduledTask` is live, driven by Celery.

- `ash/celery.py` defines the Celery app + beat schedule.
- **Beat jobs:** `agent.tasks.dispatch_due_tasks` every minute;
  `agent.tasks.check_deadlines` every 30 min.
- `dispatch_due_tasks` → `run_due_scheduled_tasks()` finds due tasks (via
  `croniter`) and runs each through `AgentEngine.chat`. Cron is evaluated in
  **Pakistan time** (see §6 below). Scheduled replies are asked to be short (1–2
  lines) and are pushed to Discord.
- **Shared-DB safety:** the dispatcher claims each task under
  `select_for_update(skip_locked=True)` and re-checks due-ness inside the lock, so
  running on two instances can't double-fire. **Run the scheduler on the SERVER
  ONLY.**
- New `ScheduledTask` fields: `last_status`, `last_result` (migration 0006).
- Agent tools: `add_scheduled_task`, `list_scheduled_tasks`,
  `delete_scheduled_task`, `toggle_scheduled_task`.
- Management-command fallback: `manage.py run_scheduled` (inline, no worker) if you
  prefer cron over celery-beat.

## 3. Deadline Alerts (new)

`check_deadlines` (beat, every 30 min) pushes a short Discord alert once per
pending `Task` within 24h of its deadline (or overdue). Guarded by
`Task.deadline_notified` (migration 0008), reset when a task's deadline changes.

## 4. Advanced File Management (new) + read/write sandbox

`agent/filesystem.py` adds `list_directory`, `create_folder`, `move_file`,
`rename_file`, `organize_folder` (sort a folder into ordered subfolders by type or
date). All file ops — **including `read_file`/`write_file`** — go through
`_safe_path()`, which confines them to `ASH_FILES_ROOT` (env; default `~`) and
blocks secrets (`.ssh`, `.env`, `*.pem`, `id_rsa`, …). This closed the previous
arbitrary-read/write hole. On the server, set `ASH_FILES_ROOT` to a dedicated dir
(home there holds deploy.sh, backups, the repo, the socket).

## 5. Auth / Sessions (supersedes §8, §16 "agent_sessions cache")

The in-memory `agent_sessions` dict is **gone**. `AgentEngine` is now built
**per request** (`api/views.py::get_agent`) — it rehydrates conversation +
memories from the shared DB every call, so it's correct across gunicorn workers
and leak-free. JWT auth is retained.

## 6. Timezone (supersedes §5.x, §13 TIME_ZONE=UTC)

`TIME_ZONE` and `CELERY_TIMEZONE` are now `Asia/Karachi`. Scheduled-task cron
expressions and displayed times are Pakistan time ("0 8 * * *" = 08:00 PKT). Each
chat also injects the current PKT date/time into the system prompt so Ash can turn
"in 2 hours" / "tomorrow 6pm" into absolute timestamps.

## 7. Model (supersedes §9 note)

`build_assignment` no longer uses the deprecated `llama-3.3-70b-versatile`. All
tool-side Groq calls use a single `GROQ_MODEL` constant (`qwen/qwen3.8-27b`) with
`reasoning_effort=none`. Task deadlines now parse both `YYYY-MM-DD` and
`YYYY-MM-DD HH:MM`.

## 8. Deployment & Ops (supersedes §14, §15)

- **`deploy.sh` hardened** (`deploy/deploy.sh`): `set -euo pipefail` (a failed
  `git pull` now aborts instead of falsely reporting success), explicit venv,
  and it restarts **gunicorn + celery-worker + celery-beat**. Install on the
  server as `/home/awais/deploy.sh`.
- **Server git auth:** switched from HTTPS (broke — GitHub killed password auth)
  to an **SSH deploy key** (`~/.ssh/id_ed25519`); remote is
  `git@github.com:Awais-niazi/ash.git`.
- **Passwordless service restarts:** `/etc/sudoers.d/ash-deploy` grants NOPASSWD
  for `systemctl restart gunicorn|celery-worker|celery-beat` and `reload nginx`,
  so deploy.sh runs non-interactively. (Restart services as separate commands to
  match the rules.)
- **Celery services:** `deploy/celery-worker.service` + `deploy/celery-beat.service`
  (systemd), server-only.
- **HTTPS:** the client is reachable over `https://ash-server.<tailnet>.ts.net`
  via `tailscale serve --bg 80` (free auto-renewing cert). Nginx `server_name` set
  to `_` (default_server) so it answers for the ts.net host too.
- **Frontend:** `client/.env.production` now uses an **empty `VITE_API_URL`** →
  origin-relative API calls (works over both the IP and the HTTPS ts.net URL, no
  mixed-content). Still shipped via `scp` of `client/dist` (not git).

## 9. Migrations added

- 0006 — ScheduledTask `last_status`/`last_result`
- 0007 — PushSubscription (later removed)
- 0008 — Task `deadline_notified`
- 0009 — delete PushSubscription

## 10. Current agent tools (delta from §9)

Added: file management (`list_directory`, `create_folder`, `move_file`,
`rename_file`, `organize_folder`), scheduling (`add_scheduled_task`,
`list_scheduled_tasks`, `delete_scheduled_task`, `toggle_scheduled_task`), and
`notify(user_id, title, message)` (send a short Discord notification — Ash's
"open hand" to alert the user).

## 11. Known gaps / TODO

- **No bulk delete.** `delete_task`/`delete_scheduled_task` are one-at-a-time, and
  the tool loop is capped at 5 calls/turn, so "delete all my tasks" is unreliable
  (may partially complete or be falsely reported). A `delete_all_tasks` /
  `delete_all_scheduled_tasks` tool is the fix.
- Legacy: the on-login morning briefing is unchanged (in-app, full text); it is
  **not** a scheduled/Discord push.
