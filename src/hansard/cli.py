"""Command-line interface: `hansard scrape` and `hansard parse`."""

import argparse
import csv
from pathlib import Path

from tqdm import tqdm

from .config import CHAMBERS, MEMBERS_FILE
from .language import analyze_language_distribution
from .members import infer_speaker_metadata, load_official_names
from .parse import process_pdf_file
from .scrape import scrape_chamber

OUTPUT_FIELDS = [
    'filename', 'date', 'speaker',
    'matched_name', 'match_score', 'language_distribution', 'content',
    'source_link', 'is_continuation',
]


def _selected_chambers(choice):
    return list(CHAMBERS.values()) if choice == "all" else [CHAMBERS[choice]]


def run_scrape(args):
    for chamber in _selected_chambers(args.chamber):
        scrape_chamber(chamber, sessions=args.session, dry_run=args.dry_run)


def parse_chamber(pdf_dir, output_csv, official_names, limit=None):
    """Parse every PDF in pdf_dir into one CSV of speeches. Returns the number of rows written."""
    # Sort by name string (case-sensitive) so row order is the same on every OS.
    pdf_files = sorted((p for p in Path(pdf_dir).iterdir() if p.suffix.lower() == '.pdf'), key=lambda p: p.name)
    if limit:
        pdf_files = pdf_files[:limit]
    print(f"Parsing {len(pdf_files)} PDF(s) from '{pdf_dir}'...")

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for pdf_path in tqdm(pdf_files, unit="pdf"):
            for record in process_pdf_file(pdf_path):
                infer_speaker_metadata(record, official_names)
                record['language_distribution'] = analyze_language_distribution(record['content'])
                writer.writerow(record)
                rows += 1
    print(f"Wrote {rows} rows to '{output_csv}'.")
    return rows


def run_parse(args):
    official_names = load_official_names(args.members)
    print(f"Loaded {len(official_names)} official member names from '{args.members}'.")
    for chamber in _selected_chambers(args.chamber):
        pdf_dir = args.input_dir or chamber.pdf_dir
        output_csv = args.output or chamber.output_csv
        parse_chamber(pdf_dir, output_csv, official_names, limit=args.limit)


def build_parser():
    parser = argparse.ArgumentParser(prog="hansard", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    chamber_choices = [*CHAMBERS, "all"]

    scrape = sub.add_parser("scrape", help="Download new Hansard PDFs from parliament.go.ke.")
    scrape.add_argument("--chamber", choices=chamber_choices, default="all")
    scrape.add_argument("--session", action="append",
                        help="Only scrape this session value (repeatable), e.g. 13th-parliament.")
    scrape.add_argument("--dry-run", action="store_true", help="List new files without downloading them.")
    scrape.set_defaults(func=run_scrape)

    parse = sub.add_parser("parse", help="Extract speeches from downloaded PDFs into a CSV.")
    parse.add_argument("--chamber", choices=chamber_choices, default="all")
    parse.add_argument("--members", type=Path, default=MEMBERS_FILE,
                       help="TSV of official member names (default: %(default)s).")
    parse.add_argument("--input-dir", type=Path, help="Override the chamber's PDF folder.")
    parse.add_argument("--output", type=Path, help="Override the chamber's output CSV.")
    parse.add_argument("--limit", type=int, help="Only parse the first N PDFs (for quick checks).")
    parse.set_defaults(func=run_parse)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "parse" and args.chamber == "all" and (args.input_dir or args.output):
        build_parser().error("--input-dir and --output need a single --chamber.")
    args.func(args)


if __name__ == "__main__":
    main()
