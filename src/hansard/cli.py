"""Command-line interface: `hansard scrape`, `parse`, `report`, `search`, and `export`."""

import argparse
import sqlite3
from pathlib import Path

from tqdm import tqdm

from . import report, search, store
from .config import CHAMBERS, DATABASE_FILE, MEMBERS_FILE, OUTPUTS_DIR
from .manifest import load_manifest
from .members import SpeakerMatcher, load_members
from .parse import PARSER_VERSION, file_sha256, parse_document, reclassify_document
from .scrape import scrape_chamber


def _selected_chambers(choice):
    return list(CHAMBERS.values()) if choice == "all" else [CHAMBERS[choice]]


def run_scrape(args):
    for chamber in _selected_chambers(args.chamber):
        scrape_chamber(chamber, sessions=args.session, dry_run=args.dry_run)


def _pdfs_to_parse(conn, chambers, rebuild, limit):
    """Return [(path, folder_chamber)] for PDFs not yet stored by the current parser version."""
    stored = {} if rebuild else store.parsed_versions(conn)
    todo, seen = [], set()
    for chamber in chambers:
        # Sort by name string (case-sensitive) so processing order is the same on every OS.
        pdfs = sorted((p for p in chamber.pdf_dir.iterdir() if p.suffix.lower() == '.pdf'), key=lambda p: p.name)
        for path in pdfs[:limit] if limit else pdfs:
            sha = file_sha256(path)
            if sha in seen or stored.get(sha) == PARSER_VERSION:
                continue  # Already parsed, or the same file is in another folder.
            seen.add(sha)
            todo.append((path, chamber.key))
    return todo


def _reclassify(conn):
    """Re-read every stored document's opening pages and update its type, date, sitting, etc."""
    rows = conn.execute("SELECT id, filename, folder_chamber, text_chars FROM documents").fetchall()
    for row in tqdm(rows, unit="pdf", desc="Reclassifying"):
        path = CHAMBERS[row["folder_chamber"]].pdf_dir / row["filename"]
        if not path.exists():
            print(f"Missing PDF, not reclassified: {path}")
            continue
        classification = reclassify_document(path, row["folder_chamber"], row["text_chars"])
        store.update_classification(conn, row["id"], classification)


def run_parse(args):
    conn = store.connect(args.database)
    if args.rebuild:
        with conn:
            conn.execute("DELETE FROM speeches")
            conn.execute("DELETE FROM documents")

    if args.reclassify:
        _reclassify(conn)

    todo = _pdfs_to_parse(conn, _selected_chambers(args.chamber), args.rebuild, args.limit)
    print(f"{len(todo)} PDF(s) to parse into '{args.database}'.")
    # Each document is saved as soon as it is parsed, so an interrupted run resumes
    # where it stopped. One bad PDF is reported rather than stopping the run.
    failed = []
    for path, chamber in tqdm(todo, unit="pdf"):
        try:
            document, speeches = parse_document(path, chamber)
        except Exception as e:
            print(f"Could not parse {path.name}: {type(e).__name__}: {e}")
            failed.append(path)
            continue
        if document:
            store.save_document(conn, document, speeches, PARSER_VERSION)
    if failed:
        print(f"{len(failed)} PDF(s) could not be parsed: {', '.join(p.name for p in failed)}")

    manifest = load_manifest()
    store.update_source_urls(conn, {key: row["source_url"] for key, row in manifest.items()})

    members = load_members(args.members)
    store.replace_members(conn, members)
    matched = store.match_all_speakers(conn, SpeakerMatcher(members))
    print(f"Loaded {len(members)} members; matched {matched} speeches to a member.")
    print("Run `hansard report` for a data-quality summary.")


def run_report(args):
    report.print_report(store.connect(args.database))


def run_search(args):
    conn = store.connect(args.database)
    try:
        total, rows = search.search(
            conn, " ".join(args.query), chamber=args.chamber, date_from=args.date_from,
            date_to=args.date_to, member=args.member, party=args.party, language=args.language,
            sort=args.sort, limit=args.limit, offset=args.offset, raw=args.raw,
        )
    except (ValueError, sqlite3.OperationalError) as e:  # Empty query, or bad --raw syntax.
        raise SystemExit(f"Search failed: {e}")

    shown = f"{args.offset + 1}-{args.offset + len(rows)}" if rows else "none"
    print(f"{total} matching speeches; showing {shown}, sorted by {args.sort}.\n")
    for row in rows:
        member = f"  [{row['member_name']}{', ' + row['party'] if row['party'] else ''}]" if row["member_name"] else ""
        print(f"{row['date']}  {row['chamber']}  {row['sitting'] or ''}  {row['speaker_raw']}{member}")
        print(f"    {row['snippet'].replace(chr(10), ' ')}")
        print(f"    {row['pdf_link'] or row['filename'] + ', page ' + str(row['page'])}\n")


def run_export(args):
    output = args.output or OUTPUTS_DIR / "speeches.csv"
    rows = report.export_speeches_csv(store.connect(args.database), output, chamber=args.chamber)
    print(f"Wrote {rows} speeches to '{output}'.")


def build_parser():
    parser = argparse.ArgumentParser(prog="hansard", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    chamber_choices = [*CHAMBERS, "all"]

    scrape = sub.add_parser("scrape", help="Download new Hansard PDFs from parliament.go.ke.")
    scrape.add_argument("--chamber", choices=chamber_choices, default="all")
    scrape.add_argument("--session", action="append",
                        help="Only scrape this session value (repeatable), e.g. 2022.")
    scrape.add_argument("--dry-run", action="store_true",
                        help="List new files without downloading them (the manifest is still updated).")
    scrape.set_defaults(func=run_scrape)

    parse = sub.add_parser("parse", help="Parse downloaded PDFs into the database.")
    parse.add_argument("--chamber", choices=chamber_choices, default="all",
                       help="Which download folders to parse.")
    parse.add_argument("--database", type=Path, default=DATABASE_FILE, help="Default: %(default)s")
    parse.add_argument("--members", type=Path, default=MEMBERS_FILE,
                       help="TSV of official members (default: %(default)s).")
    parse.add_argument("--rebuild", action="store_true", help="Re-parse every PDF, not just new ones.")
    parse.add_argument("--reclassify", action="store_true",
                       help="Re-detect type, chamber, date and sitting for stored documents "
                            "(quick; use after changing documents.py).")
    parse.add_argument("--limit", type=int, help="Only consider the first N PDFs per folder (for quick checks).")
    parse.set_defaults(func=run_parse)

    rep = sub.add_parser("report", help="Print a data-quality summary of the database.")
    rep.add_argument("--database", type=Path, default=DATABASE_FILE)
    rep.set_defaults(func=run_report)

    find = sub.add_parser("search", help="Full-text search of speeches.",
                          description='Words must all appear; use "quoted phrases", word* for prefixes, '
                                      'and OR between alternatives.')
    find.add_argument("query", nargs="+")
    find.add_argument("--database", type=Path, default=DATABASE_FILE)
    find.add_argument("--chamber", choices=[*CHAMBERS, "joint"])
    find.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    find.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
    find.add_argument("--member", help="Part of a member's name, e.g. Cheruiyot.")
    find.add_argument("--party", help="Party abbreviation, e.g. ODM.")
    find.add_argument("--language", choices=["en", "sw"], help="Primary language of the speech.")
    find.add_argument("--sort", choices=["rank", "newest", "oldest"], default="rank")
    find.add_argument("--limit", type=int, default=10)
    find.add_argument("--offset", type=int, default=0)
    find.add_argument("--raw", action="store_true", help="Pass the query to SQLite FTS5 unchanged.")
    find.set_defaults(func=run_search)

    export = sub.add_parser("export", help="Export speeches, with document and member details, to CSV.")
    export.add_argument("--database", type=Path, default=DATABASE_FILE)
    export.add_argument("--chamber", choices=[*CHAMBERS, "joint"], help="Only export one chamber.")
    export.add_argument("--output", type=Path, help="Default: outputs/speeches.csv")
    export.set_defaults(func=run_export)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
