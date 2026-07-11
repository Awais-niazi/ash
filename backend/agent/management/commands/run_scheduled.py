"""
Run any due scheduled tasks once, inline (no Celery worker required).

Use this if you'd rather drive Ash's schedule from system cron than run a
Celery beat + worker. Add to crontab:

    * * * * * cd /home/awais-faiz/Dev/ASH/backend && venv/bin/python manage.py run_scheduled
"""

from django.core.management.base import BaseCommand

from agent.tasks import run_due_scheduled_tasks


class Command(BaseCommand):
    help = "Run scheduled tasks that are currently due (inline)."

    def handle(self, *args, **options):
        result = run_due_scheduled_tasks(sync=True)
        fired = result["fired"]
        if fired:
            self.stdout.write(self.style.SUCCESS(
                f"Ran {len(fired)} scheduled task(s): {fired}"))
        else:
            self.stdout.write("No scheduled tasks due.")
