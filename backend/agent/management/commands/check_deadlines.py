"""
Send deadline reminders once, inline (no Celery worker required).

Cron counterpart to the check-task-deadlines beat entry. Add to crontab:

    */30 * * * * cd /home/awais-faiz/Dev/ASH/backend && venv/bin/python manage.py check_deadlines
"""

from django.core.management.base import BaseCommand

from agent.tasks import run_deadline_checks


class Command(BaseCommand):
    help = "Alert on pending tasks due within 24h (inline)."

    def handle(self, *args, **options):
        alerted = run_deadline_checks()["alerted"]
        if alerted:
            self.stdout.write(self.style.SUCCESS(
                f"Sent {len(alerted)} deadline reminder(s): {alerted}"))
        else:
            self.stdout.write("No deadline reminders due.")
