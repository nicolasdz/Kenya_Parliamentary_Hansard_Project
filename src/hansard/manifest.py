"""The manifest records where each PDF was downloaded from.

It is a small CSV committed to git (unlike the PDFs themselves), so every
document can link back to its official source on parliament.go.ke.
"""

import csv

from .config import MANIFEST_FILE

FIELDS = ["chamber", "filename", "source_url", "session"]


def load_manifest(path=MANIFEST_FILE):
    """Return {(chamber_key, filename): row} for every PDF seen on the website."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {(row["chamber"], row["filename"]): row for row in csv.DictReader(f)}


def save_manifest(manifest, path=MANIFEST_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        # LF line endings, matching .gitattributes (csv defaults to CRLF).
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest[key] for key in sorted(manifest))
