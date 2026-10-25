# Kenya Parliamentary Hansard Project

A data pipeline that collects, cleans, makes searchable, and publishes the
Hansard (official verbatim record) of Kenya's National Assembly and Senate, so
that citizens can more easily access these public records.

**Status:** collection, parsing, and full-text search work, in a SQLite
database. Publishing is not built yet.

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
```

For the research notebooks, also install `pip install -e ".[notebooks]"`
(see [Research notebooks](#research-notebooks)).

Credentials (currently only ACLED, used by the Political Violence notebook) go
in a `.env` file in the project root; copy `.env.example` to get started.

## Usage

```bash
hansard scrape --chamber all          # Download new PDFs and update inputs/manifest.csv
hansard scrape --chamber senate --session 2022 --dry-run   # List new files only
hansard parse                         # Parse new PDFs into outputs/hansard.db
hansard report                        # Data-quality summary
hansard search housing levy --chamber senate --from 2023-01-01
hansard export --chamber senate       # Speeches (with member details) -> outputs/speeches.csv
```

### Searching

`hansard search` finds speeches containing all the words given, best matches
first, and prints each with a snippet and a link that opens the PDF at the
right page.

- `"finance bill"` matches an exact phrase; `impeach*` matches words starting
  with "impeach"; `maji OR water` matches either word.
- Filters: `--chamber`, `--from`/`--to` (dates), `--member` (part of the official
  or printed name), `--party`, `--language en|sw`.
- `--sort newest|oldest`, `--limit`, `--offset`; `--raw` passes the query to
  [SQLite FTS5](https://sqlite.org/fts5.html#full_text_query_syntax) unchanged.

There is no stemming (so it works the same for English and Kiswahili): `levy`
does not match `levies`, so search `levy OR levies`. (A prefix like `lev*` would
also match "level".)

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
  search.py     Full-text search with filters
  report.py     Data-quality report and CSV export
  cli.py        The `hansard` command
tests/          Unit tests (`pytest`)
notebooks/      Research notebooks (sentiment/topic models, political violence)
inputs/
  national_assembly_hansards/, senate_hansards/   PDFs (local only, gitignored)
  manifest.csv                                     Source URL of every PDF listed online
  parliamentarians/googlesheet.tsv                 Official member list
  other_data/                                      ACLED data, Kenya shapefiles (local only, gitignored)
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
- **speeches_fts**: an FTS5 full-text index of speech text and speaker lines.
  It reads text from `speeches` (nothing is stored twice) and is kept in sync by
  triggers. Databases from before it existed are indexed automatically the next
  time any `hansard` command opens them (about 20 seconds).

Speakers are only matched against members of the same chamber and Parliament.
The member list currently covers the 12th and 13th National Assembly and the
13th Senate, so speeches from other chambers or Parliaments are left unmatched.

## Research notebooks

The notebooks in `notebooks/` read `outputs/hansard.db`, so run `hansard parse`
first. Open them with the project's virtual environment as the Jupyter kernel
(`pip install -e ".[notebooks]"`, then `jupyter lab` from the activated venv).

- **Hansard ML Notebook**: sentiment over time (tabularisai multilingual
  sentiment model) and topic classification (zero-shot). Speeches are split
  into 480-word chunks for the models.
- **Hansard Political Violence Notebook**: maps ACLED political-violence events
  in Kenya, for comparison with parliamentary speech.

Each notebook's loading cell has settings: `CHAMBER`, and `SAMPLE_SIZE` to
analyse a random sample of speeches. The models take many hours over every
speech on a CPU; a sample of a few thousand runs in minutes. The multilingual
zero-shot cell (over 24 hours on a CPU) only runs when
`RUN_MULTILINGUAL_ZERO_SHOT = True`.

On Windows with an Anaconda-based Python, the ML notebook loads Windows' own
C++ runtime before PyTorch, because Anaconda's older copy makes PyTorch fail
with "DLL initialization routine failed" for `c10.dll`.

### Third-party data

The Political Violence notebook needs two datasets that can't be redistributed,
so they are gitignored and each user downloads their own copy into
`inputs/other_data/`:

- **ACLED events**: register at [acleddata.com](https://acleddata.com), then
  either export Kenya events as `ACLED Kenya Data through <MM-DD-YYYY>.csv`, or
  put your login in `.env` and set `USE_ACLED_API = True` in the notebook to
  download them. The notebook uses the newest `ACLED Kenya*.csv` in the folder.
- **Kenya boundaries**: GADM version 2.5 shapefiles for Kenya from
  [gadm.org](https://gadm.org) (non-commercial use only), in
  `inputs/other_data/kenya_adm1_shapefiles/` (the notebook reads `KEN_adm1.shp`).

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
  Not needed for now, since only new PDFs are parsed after the first build. A
  lead to try: Anaconda's outdated C++ runtime (see
  [Research notebooks](#research-notebooks)) also breaks PyTorch on this setup.

## License

The code is released under the [MIT License](LICENSE). This covers the code
only: Hansard records belong to the Parliament of Kenya, and the third-party
datasets above have their own terms.

## Credits

The original scraper and parser were written by Joshua Been (2025).
