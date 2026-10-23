# Kenya Parliamentary Hansard Project

A data pipeline that collects, cleans, makes searchable, and publishes the
Hansard (official verbatim record) of Kenya's National Assembly and Senate, so
that citizens can more easily access these public records.

**Status:** collection and parsing work, into a SQLite database. Search and
publishing are not built yet.

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
```

For the research notebooks, also install `pip install -e ".[notebooks]"`.

Credentials (currently only ACLED, used by the Political Violence notebook) go
in a `.env` file in the project root; copy `.env.example` to get started.

## Usage

```bash
hansard scrape --chamber all          # Download new PDFs and update inputs/manifest.csv
hansard scrape --chamber senate --session 2022 --dry-run   # List new files only
hansard parse                         # Parse new PDFs into outputs/hansard.db
hansard report                        # Data-quality summary
hansard export --chamber senate       # Speeches (with member details) -> outputs/speeches.csv
```

`hansard parse` only parses PDFs it hasn't stored yet (or that were stored by an
older parser version), so it is quick to re-run after a scrape. Speakers are
re-matched to members on every run, so edits to the member list take effect
without re-parsing. After changing how documents are classified (`documents.py`),
run `hansard parse --reclassify`, which takes under a minute. Use `--rebuild` to
re-parse everything; a full build of ~2,500 PDFs takes about two hours. Run any
command with `--help` for all options.

## Layout

```
src/hansard/
  config.py     Paths and per-chamber settings
  scrape.py     Download Hansard PDFs from parliament.go.ke
  manifest.py   Record each PDF's source URL (inputs/manifest.csv)
  documents.py  Classify a PDF: document type, chamber, date, sitting
  parse.py      Split Hansards into individual speeches and clean the text
  members.py    Load the member list and fuzzy-match speaker names to it
  language.py   Estimate the English/Kiswahili mix of each speech
  store.py      The SQLite database
  report.py     Data-quality report and CSV export
  cli.py        The `hansard` command
tests/          Unit tests (`pytest`)
notebooks/      Research notebooks (sentiment/topic models, political violence)
inputs/
  national_assembly_hansards/, senate_hansards/   PDFs (local only, gitignored)
  manifest.csv                                     Source URL of every PDF listed online
  parliamentarians/googlesheet.tsv                 Official member list
  other_data/                                      ACLED data, Kenya shapefiles
outputs/        hansard.db and CSV exports (gitignored, reproducible)
```

PDFs are not stored in git. Run `hansard scrape` to download them.

## Data model

`outputs/hansard.db` has three tables:

- **documents**: one row per unique PDF, deduplicated by file hash. Includes
  the document type (`hansard`, `order_paper`, `votes_and_proceedings`,
  `no_text` for scanned PDFs, `unknown`), chamber (`national_assembly`, `senate`,
  `joint`), date, Parliament number, sitting (`morning`, `afternoon`, `evening`),
  special-sitting flag, and source URL. Type, chamber, date and sitting are read
  from the document's opening text where possible, because the website's
  filenames and listings are unreliable; the filename is the fallback.
- **speeches**: one row per speech, in order, with the PDF page it starts on,
  the speaker as printed, the matched member (if any) and match score, the text
  (paragraphs separated by newlines), word count, and language mix.
- **members**: one row per member per Parliament, from the members TSV.

Speakers are only matched against members of the same chamber and Parliament.
The member list currently covers the 12th and 13th National Assembly and the
13th Senate, so speeches from other chambers or Parliaments are left unmatched.

## Later

- **Member list gaps.** Matching depends on `googlesheet.tsv`, which has no
  11th Parliament or 12th Senate, and misses some members (e.g. Sen. Gloria
  Orwoba; Opiyo Wandayi is listed only for the 12th Parliament). Some members
  appear in the Hansard under other names ("Veronica Maina" vs "Veronica Waheti
  Nduati", "Okiya" vs "Okoiti" Omtatah); an alias column would let these match.
  `hansard report` lists the most frequent unmatched speakers.
- **Presiding officers.** "Hon. Speaker" and "Hon. Deputy Speaker" lines aren't
  matched to a person; they could be resolved from who held the role on that date.
- **Members speaking in the other chamber.** National Assembly members appearing
  in the Senate (e.g. as impeachment managers) are not matched, because matching
  is limited to the chamber's own members.
- **Duplicate copies of a sitting.** About 60 sittings have more than one
  (non-identical) PDF, e.g. a joint sitting listed under both chambers, or a
  revised upload. All copies are kept; search should show one.
- **Parallel parsing.** Parsing runs one PDF at a time. Running it in worker
  processes on Windows caused random crashes (access violations inside
  langdetect after PyMuPDF had run in the same worker) whose cause wasn't found.
  Not needed for now, since only new PDFs are parsed after the first build.

## Credits

The original scraper and parser were written by Joshua Been (2025).
