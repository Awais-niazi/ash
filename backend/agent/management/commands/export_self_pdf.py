"""
Render docs/ASH_SELF.md to docs/ASH_SELF.pdf for reading and sharing.

The Markdown stays the source of truth — the retrieval pipeline never reads the
PDF. Rendering goes through headless Chrome, which is already installed, so
there are no extra system packages to maintain.

    cd ~/Dev/ASH/backend && venv/bin/python manage.py export_self_pdf
"""

import os
import shutil
import subprocess
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

CSS = """
@page { size: A4; margin: 20mm 18mm; }
body { font: 11pt/1.55 "Source Serif 4", Georgia, serif; color: #1C1719; max-width: none; }
h1 { font-family: "Bricolage Grotesque", Helvetica, sans-serif; font-size: 25pt;
     color: #8B1E2D; margin: 0 0 4pt; letter-spacing: -.01em; }
h2 { font-family: "Bricolage Grotesque", Helvetica, sans-serif; font-size: 15pt;
     margin: 22pt 0 6pt; padding-bottom: 3pt; border-bottom: 1px solid #E3DBDD;
     page-break-after: avoid; }
h3 { font-family: "Bricolage Grotesque", Helvetica, sans-serif; font-size: 12pt;
     margin: 14pt 0 4pt; color: #4A3F43; page-break-after: avoid; }
p, li { orphans: 2; widows: 2; }
code { font-family: "IBM Plex Mono", monospace; font-size: 9.5pt;
       background: #F6F3F3; padding: 1px 4px; border-radius: 2px; }
pre { background: #F6F3F3; border: 1px solid #E3DBDD; border-radius: 3px;
      padding: 8pt 10pt; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 9pt; }
table { border-collapse: collapse; width: 100%; font-size: 10pt; margin: 10pt 0;
        page-break-inside: avoid; }
th, td { border-bottom: 1px solid #E3DBDD; padding: 5pt 7pt; text-align: left;
         vertical-align: top; }
th { background: #F6F3F3; font-family: "IBM Plex Mono", monospace; font-size: 8.5pt;
     text-transform: uppercase; letter-spacing: .07em; }
hr { border: 0; border-top: 1px solid #E3DBDD; margin: 18pt 0; }
blockquote { margin: 10pt 0; padding-left: 12pt; border-left: 3px solid #8B1E2D;
             color: #4A3F43; }
"""


def _chrome() -> str:
    for name in ("google-chrome", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise CommandError(
        "No Chrome or Chromium found — install one, or read the Markdown instead."
    )


class Command(BaseCommand):
    help = "Render Ash's self-knowledge document to PDF."

    def handle(self, *args, **options):
        import markdown

        docs = os.path.join(os.path.dirname(settings.BASE_DIR), "docs")
        src = os.path.join(docs, "ASH_SELF.md")
        out = os.path.join(docs, "ASH_SELF.pdf")

        with open(src) as f:
            html_body = markdown.markdown(
                f.read(), extensions=["tables", "fenced_code", "toc"])

        html = (f"<!doctype html><meta charset='utf-8'>"
                f"<title>Ash — Self Knowledge</title>"
                f"<style>{CSS}</style>{html_body}")

        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
            tmp.write(html)
            tmp_path = tmp.name

        try:
            subprocess.run(
                [_chrome(), "--headless", "--disable-gpu", "--no-sandbox",
                 "--no-pdf-header-footer", f"--print-to-pdf={out}",
                 f"file://{tmp_path}"],
                capture_output=True, timeout=120, check=True,
            )
        except subprocess.CalledProcessError as e:
            raise CommandError(f"Chrome failed: {e.stderr.decode()[:300]}")
        finally:
            os.unlink(tmp_path)

        size = os.path.getsize(out) // 1024
        self.stdout.write(self.style.SUCCESS(f"Wrote {out} ({size} KB)"))
