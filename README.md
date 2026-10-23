# Kenya Parliamentary Hansard Project

A data pipeline that collects, cleans, makes searchable, and publishes the
Hansard (official verbatim record) of Kenya's National Assembly and Senate, so
that citizens can more easily access these public records.

**Status:** collection and parsing work. Search and publishing are not built yet.

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
hansard scrape --chamber all          # Download any PDFs not already in inputs/
hansard scrape --chamber senate --session 2022 --dry-run   # List new files only
hansard parse --chamber national_assembly                 # PDFs -> outputs/*.csv
hansard parse --chamber senate --limit 5 --output outputs/test.csv   # Quick check
```

Run `hansard scrape --help` or `hansard parse --help` for all options.

## Layout

```
src/hansard/
  config.py     Paths and per-chamber settings
  scrape.py     Download Hansard PDFs from parliament.go.ke
  parse.py      Split PDFs into individual speeches and clean the text
  members.py    Fuzzy-match speaker names to the official member list
  language.py   Estimate the English/Kiswahili mix of each speech
  cli.py        The `hansard` command
tests/          Unit tests (`pytest`)
notebooks/      Research notebooks (sentiment/topic models, political violence)
inputs/
  national_assembly_hansards/, senate_hansards/   PDFs (local only, gitignored)
  parliamentarians/googlesheet.tsv                 Official member list
  other_data/                                      ACLED data, Kenya shapefiles
outputs/        Parser CSVs (gitignored, reproducible)
```

PDFs are not stored in git. Run `hansard scrape` to download them.

## Output columns

| Column | Meaning |
|---|---|
| `filename` | Source PDF |
| `date` | Sitting date (YYYY-MM-DD); blank on continuation rows |
| `speaker` | Speaker as written in the Hansard, e.g. `Hon. Speaker` |
| `matched_name`, `match_score` | Best fuzzy match in the member list (2017 onwards, score ≥ 80) |
| `language_distribution` | JSON share of words per language, e.g. `{"en": 0.8, "sw": 0.2}` |
| `content` | Speech text, split into chunks of at most 480 words |
| `source_link` | Spreadsheet hyperlink formula to the PDF |
| `is_continuation` | True for the second and later chunks of one long speech |

## Credits

The original scraper and parser were written by Joshua Been (2025).
