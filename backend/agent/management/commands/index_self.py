"""
Re-chunk and re-embed Ash's self-knowledge document.

Run after editing docs/ASH_SELF.md:

    cd ~/Dev/ASH/backend && venv/bin/python manage.py index_self

The first run downloads the embedding model (~130MB) to the fastembed cache.
"""

from django.core.management.base import BaseCommand

from agent.knowledge import reindex


class Command(BaseCommand):
    help = "Rebuild the vector index over Ash's self-knowledge document."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=None,
            help="Markdown file to index (defaults to docs/ASH_SELF.md)",
        )

    def handle(self, *args, **options):
        stats = reindex(options["path"])
        self.stdout.write(self.style.SUCCESS(
            f"Indexed {stats['chunks']} chunks from {stats['source']} "
            f"(average {stats['avg_chars']} characters each)."
        ))
