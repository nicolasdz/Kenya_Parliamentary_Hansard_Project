# User Guide

Practical detail beyond the [README](../README.md): every command and its
options, how to write searches, how the pipeline works inside, and the research
notebooks. For settled project-wide decisions see the
[decision register](decision_register.md); for planned work and undecided
questions see [open topics](open_topics.md).

- [The pipeline at a glance](#the-pipeline-at-a-glance)
- [Commands](#commands)
  - [scrape](#hansard-scrape) · [parse](#hansard-parse) · [report](#hansard-report) · [search](#hansard-search) · [export](#hansard-export)
- [Writing searches](#writing-searches)
- [How it works](#how-it-works)
- [Research notebooks](#research-notebooks)
- [Third-party data](#third-party-data)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## The pipeline at a glance

```
parliament.go.ke ──scrape──▶ inputs/*_hansards/*.pdf  (+ inputs/manifest.csv)
                 ──parse───▶ outputs/hansard.db        (documents, speeches, members, search index)
                 ──report / search / export
```

A typical update after new sittings are published:

```bash
hansard scrape     # download any new PDFs
hansard parse      # parse only the new ones
hansard report     # check data quality
```

Run any command with `--help` for its full options.

## Commands

### `hansard scrape`

Downloads Hansard PDFs from parliament.go.ke into
`inputs/national_assembly_hansards/` and `inputs/senate_hansards/`.

| Option | Meaning |
|---|---|
| `--chamber national_assembly\|senate\|all` | Which website listing to scrape (default `all`) |
| `--session 2022` | Only this parliamentary session value; repeatable. Values come from the site's session filter (e.g. 2013, 2017, 2022) |
| `--dry-run` | List new files without downloading them |

- Sessions are discovered from the website, so new sessions are picked up
  automatically.
- Files already on disk are skipped, so re-running is cheap.
- Order papers and votes-and-proceedings documents in the listings are skipped.
- Every PDF link found, downloaded or not, is recorded in `inputs/manifest.csv`
  with its source URL. That's how each speech links back to the official PDF.
  The manifest is committed to git; the PDFs are not.
- Some links on the website are broken (404). They are listed at the end of the
  run, and the scraper carries on with the rest.
- It waits one second between downloads to go easy on the website.

### `hansard parse`

Parses downloaded PDFs into `outputs/hansard.db`.

| Option | Meaning |
|---|---|
| `--chamber …` | Which download folders to parse (default `all`) |
| `--rebuild` | Re-parse every PDF, not just new ones (about two hours for ~2,800 PDFs) |
| `--reclassify` | Re-detect each stored document's type, chamber, date and sitting from its first pages, without re-extracting speeches (under a minute) |
| `--limit N` | Only consider the first N PDFs per folder, for quick checks |
| `--members PATH` | Member list TSV (default `inputs/parliamentarians/googlesheet.tsv`) |
| `--database PATH` | Database file (default `outputs/hansard.db`) |

- **Incremental.** Each stored document records its file hash and the parser
  version that produced it. A PDF is parsed only if it's new or was parsed by an
  older version, so a run after a scrape takes about 2 seconds per new PDF.
- **Interruptible.** Each document is saved as soon as it's parsed, so a run
  stopped partway resumes where it left off.
- **Members are re-matched on every run**, so edits to the member list take
  effect without re-parsing anything.
- **Identical files are stored once**, even if they appear in both chambers'
  folders or under different names.
- One unreadable PDF is reported and skipped rather than stopping the run.

### `hansard report`

Prints a data-quality summary of the database:

- documents by type and chamber;
- Hansards whose content names a different chamber than the listing they came from;
- Hansards with no date, or whose filename and content dates disagree (and which one was used);
- Hansards with no detected sitting, or no speeches;
- documents with no text layer (scanned, would need OCR);
- sittings with more than one PDF (possible revised copies);
- Hansards with no source URL;
- speech totals, the share matched to a member, primary-language counts, and
  the most frequent unmatched speakers.

Run it after each parse. The unmatched-speakers list is the best guide to
gaps in the member list.

### `hansard search`

Full-text search of speech text. See [Writing searches](#writing-searches).

```bash
hansard search housing levy --chamber senate --from 2023-01-01
```

Each result shows the date, chamber and sitting, the speaker as printed, the
matched member and party, a snippet with the matching words in `[brackets]`, and
a link that opens the official PDF at the right page (`…pdf#page=68`).

### `hansard export`

Writes one CSV row per speech, with document and member details, to
`outputs/speeches.csv` (or `--output PATH`). `--chamber` limits it to one
chamber, including `joint`.

Columns: `speech_id`, `filename`, `chamber`, `date`, `sitting`,
`special_sitting`, `parliament`, `seq` (order within the sitting), `page`,
`speaker_raw`, `member_name`, `party`, `county`, `constituency`, `match_score`,
`primary_language`, `language_distribution`, `word_count`, `text`, `source_url`.

Speech text is not split, so about 100 very long speeches exceed Excel's limit
of 32,767 characters per cell and get cut off if the CSV is opened in Excel.
Use pandas or another tool to read the full text.

## Writing searches

By default, a search matches speeches that contain **all** the words given,
best matches first.

| You type | Matches |
|---|---|
| `housing levy` | speeches containing both words, anywhere |
| `"finance bill"` | the exact phrase |
| `impeach*` | words starting with "impeach" (impeach, impeachment, impeached) |
| `maji OR water` | either word |
| `"housing levy" OR "affordable housing"` | either phrase |

Tips:

- **There is no stemming.** `levy` does not match `levies`, and `elimu` does not
  match other forms of the word. This is deliberate, so English and Kiswahili
  behave the same. Search `levy OR levies`, or use a prefix, but check it isn't
  too broad: `lev*` also matches "level" and "leverage".
- **Case and accents don't matter.**
- **Punctuation is safe.** Names like `Ichung'wah` and terms like `COVID-19` work
  as typed.
- **Only speech text is searched**, not the speaker line. To find what someone
  said, use `--member`, which matches part of the official name or the name as
  printed (`--member Cheruiyot`).
- **Very common words** ("the", "and") match most speeches and are slow (about a
  second); add more specific words.

Filters and options:

| Option | Meaning |
|---|---|
| `--chamber national_assembly\|senate\|joint` | One chamber |
| `--from YYYY-MM-DD`, `--to YYYY-MM-DD` | Date range (inclusive) |
| `--member NAME` | Part of the member's official or printed name |
| `--party ODM` | Party abbreviation, as in the member list (case-insensitive) |
| `--language en\|sw` | Primary language of the speech |
| `--sort rank\|newest\|oldest` | Best match first (default), or by date |
| `--limit N`, `--offset N` | Page through results (default 10 per page) |
| `--raw` | Pass the query to SQLite FTS5 unchanged, for its [full query syntax](https://sqlite.org/fts5.html#full_text_query_syntax) (`NEAR`, `NOT`, column filters) |

`--member` and `--party` only find speeches matched to a member, so they miss
speakers the member list doesn't cover. See [Member matching](#member-matching).

## How it works

### Code layout

```
src/hansard/
  config.py     Paths and per-chamber settings
  scrape.py     Download Hansard PDFs from parliament.go.ke
  manifest.py   Record each PDF's source URL (inputs/manifest.csv)
  documents.py  Classify a PDF: document type, chamber, date, sitting
  parse.py      Split Hansards into individual speeches and clean the text
  members.py    Load the member list and fuzzy-match speaker names to it
  language.py   Estimate the English/Kiswahili mix of each speech
  store.py      The SQLite database: schema, migrations, saving
  search.py     Full-text search with filters
  report.py     Data-quality report and CSV export
  cli.py        The `hansard` command
tests/          Unit tests (`pytest`)
notebooks/      Research notebooks
inputs/
  national_assembly_hansards/, senate_hansards/   PDFs (local only, not in git)
  manifest.csv                                     Source URL of every PDF listed online
  parliamentarians/                                Member list (googlesheet.tsv) and its raw sources
  other_data/                                      ACLED and GADM data (local only, not in git)
outputs/        hansard.db and CSV exports (not in git, reproducible)
documentation/  This guide, the decision register, and open topics
```

### Data model

`outputs/hansard.db` is a single SQLite file:

- **documents**: one row per unique PDF, deduplicated by file hash. Columns
  include the document type (`hansard`, `order_paper`, `votes_and_proceedings`,
  `no_text` for scanned PDFs, `unknown`), chamber (`national_assembly`, `senate`,
  `joint`), date, Parliament number (11, 12, 13), sitting (`morning`,
  `afternoon`, `evening`), special-sitting flag, source URL, page count and
  parser version.
- **speeches**: one row per speech, in order within its sitting: the PDF page it
  starts on, the speaker as printed, the matched member (if any) and match score,
  the text (paragraphs separated by newlines), word count, language mix and
  primary language.
- **members**: one row per member per Parliament, loaded from the members TSV.
  Rebuilt on every parse.
- **speeches_fts**: the full-text search index of speech text and speaker lines.
  It reads text from `speeches`, so nothing is stored twice, and triggers keep it
  in sync. A database from before the index existed is indexed automatically the
  next time any `hansard` command opens it (about 20 seconds).

The database records its schema version (`PRAGMA user_version`), and `store.py`
applies any newer migrations when it opens an older database.

### Document classification

The website's filenames and listings are unreliable: Senate Hansards appear in
the National Assembly listing, order papers are mixed in, and filenames use
many different date formats, some with typos. So each fact is read from the
document's opening pages where possible, with the filename as a fallback:

- **Type**: "THE HANSARD", "OFFICIAL REPORT" or "DEBATES" in the header means a
  Hansard; order papers and votes and proceedings are recognised and stored
  without speeches. PDFs with almost no extractable text are flagged `no_text`.
- **Chamber**: "JOINT SITTING", "SENATE" or "NATIONAL ASSEMBLY" in the header.
- **Date**: from the filename and from the title line (e.g. "Tuesday, 14th March
  2017"). When they disagree, the one that falls on the weekday the document
  names wins; this catches typos in either.
- **Sitting**: from "The House met at 2.30 p.m." (also written in words at joint
  sittings, "ten minutes past three o'clock"), then "Morning Sitting" headings,
  then filename markers such as `(A)`, `(P)`, `(E)`, `AM`, `Morning`.
- **Parliament**: from the date (11th from March 2013, 12th from August 2017,
  13th from September 2022).

After changing `documents.py`, run `hansard parse --reclassify` to apply the
changes to stored documents.

### Speech extraction

Each page's paragraphs are extracted, and a speech starts at any paragraph of
the form `<speaker>: <text>`. The speaker is either an honorific and name
(`Hon. Kimani Ichung'wah (Kikuyu, UDA)`, `Sen. Cheruiyot`) or a role with the
person in brackets (`The Temporary Deputy Chairman (Hon. Omulele)`). The speech
runs until the next speaker or a procedural heading (PRAYERS, MOTION, BILLS…).

Running page headers, the disclaimer printed on every page, and notes such as
"(Applause)" are removed, including when the PDF splits them across
paragraphs.

After changing speech extraction in `parse.py`, increase `PARSER_VERSION`.
The next `hansard parse` then re-parses every document stored by an older
version.

### Member matching

Each speaker line is cleaned to a name (titles, roles and honours like "MGH"
removed) and fuzzy-matched against the member list:

- Only members of **the same chamber and Parliament** are candidates (both
  chambers for joint sittings). The member list currently covers the 12th and
  13th National Assembly and the 13th Senate; speeches from other chambers and
  Parliaments are left unmatched rather than guessed.
- The score must be at least 80, and **every word of the printed name must
  appear in the official name**. Without this rule, sharing one word produced
  wrong matches ("Robert Pukose" → "Mbui, Robert").
- Since 2022, speaker lines name the constituency ("(Suba North, ODM)"). When
  exactly one candidate represents it, a lower name score (60) is accepted,
  which catches married names and spelling differences.

The result favours accuracy over coverage. About 72% of speeches in covered
chambers and Parliaments are matched. Most unmatched speakers are presiding
officers ("Hon. Speaker"), non-members such as counsel at impeachment hearings,
or members missing from or named differently in the member list.

### Language detection

Each speech is split into sentence groups of at least five words, and each
group's language is detected (English or Kiswahili only). Groups that can't be
identified take the language of the previous group. The result is stored as a
share per language (`{"en": 0.8, "sw": 0.2}`) plus the primary language.

## Research notebooks

The notebooks in `notebooks/` read `outputs/hansard.db`, so run `hansard parse`
first. Install their libraries and open them with the project's virtual
environment as the Jupyter kernel:

```bash
pip install -e ".[notebooks]"
jupyter lab
```

- **Hansard ML Notebook**: sentiment over time (tabularisai multilingual
  sentiment model) and topic classification (zero-shot). Speeches are split into
  480-word chunks, because the models read at most 512 tokens.
- **Hansard Political Violence Notebook**: maps ACLED political-violence events
  in Kenya, for comparison with parliamentary speech. Needs the
  [third-party data](#third-party-data).

Each notebook's loading cell has settings:

| Setting | Meaning |
|---|---|
| `CHAMBER` | `"senate"`, `"national_assembly"` or `"joint"` |
| `SAMPLE_SIZE` | Analyse a random sample of speeches; `None` uses every speech. The models take many hours over every speech on a CPU; a sample of a few thousand runs in minutes |
| `RUN_MULTILINGUAL_ZERO_SHOT` | ML notebook only. The multilingual zero-shot cell takes over 24 hours on a CPU, so it runs only when this is `True` |
| `USE_ACLED_API` | Political Violence notebook only. Download the latest ACLED events instead of using a stored CSV |

The first run downloads the models from Hugging Face (roughly 0.5–1 GB each).

## Third-party data

The Political Violence notebook needs two datasets whose terms don't allow
redistribution, so they aren't in git. Each user downloads their own copy into
`inputs/other_data/`:

- **ACLED events**: register at [acleddata.com](https://acleddata.com), then
  either export Kenya events as `ACLED Kenya Data through <MM-DD-YYYY>.csv`, or
  put your login in `.env` (copy `.env.example`) and set `USE_ACLED_API = True`
  in the notebook. The notebook uses the newest `ACLED Kenya*.csv` in the folder.
- **Kenya boundaries**: GADM version 2.5 shapefiles for Kenya from
  [gadm.org](https://gadm.org) (non-commercial use only), in
  `inputs/other_data/kenya_adm1_shapefiles/`. The notebook reads `KEN_adm1.shp`.

## Troubleshooting

- **PyTorch fails with "DLL initialization routine failed" for `c10.dll`**
  (Windows, Anaconda-based Python). Anaconda ships an old Microsoft C++ runtime
  (`msvcp140.dll`) that recent PyTorch can't use. The ML notebook works around
  this by loading Windows' own copy before PyTorch; do the same in other scripts.
- **PyMuPDF 2.x crashes on import** (Windows). The project pins PyMuPDF below
  2.0, which is also the version family the stored data was parsed with.
- **"Updating the database (migration …)" on first run.** A one-off upgrade of an
  older database, such as building the search index.
- **A search returns nothing for a member.** The member may not be matched; try
  the name as printed with `--member`, or search for the name as a word.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The tests build small PDFs and databases on the fly, so they don't need the
real PDFs. When changing:

- **speech extraction** (`parse.py`): increase `PARSER_VERSION`, then run
  `hansard parse` to re-parse stored documents (about two hours);
- **document classification** (`documents.py`): run `hansard parse --reclassify`;
- **member matching** (`members.py`) or the member list: run `hansard parse`
  (re-matching takes under a minute);
- **the database schema** (`store.py`): add a step to `MIGRATIONS`, so existing
  databases are upgraded when opened.
