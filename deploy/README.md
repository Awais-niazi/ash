# Ash server — scheduled task services

Ash's scheduled tasks run on the **server only** (it's the 24/7 instance; the
laptop is often off). Because both instances share one Postgres database,
running the scheduler on both would double-fire every task. The dispatcher is
hardened with a row lock as a safety net, but still install these on the server
only.

## Option A — Celery (matches the existing Redis broker)

One-time setup on the server (`ssh awais@100.123.230.103`):

```bash
sudo cp /home/awais/ash/deploy/celery-worker.service /etc/systemd/system/
sudo cp /home/awais/ash/deploy/celery-beat.service   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now celery-worker celery-beat
```

Check they're up / tail logs:

```bash
systemctl status celery-worker celery-beat
journalctl -u celery-beat -f
```

Beat ticks every minute and dispatches any due `ScheduledTask` to the worker.

## Option B — cron (simpler, no worker/beat)

If you'd rather not run two more services, drive it from cron instead. As user
`awais`:

```cron
* * * * * cd /home/awais/ash/backend && venv/bin/python manage.py run_scheduled >> /home/awais/scheduled.log 2>&1
```

`run_scheduled` runs due tasks inline (no broker needed). Use **either** Option A
**or** Option B, never both.

## Server .env additions

```
# Restrict the file-management sandbox to a safe folder — the server home
# contains deploy.sh, backups/, the repo and the gunicorn socket.
ASH_FILES_ROOT=/home/awais/files
```
