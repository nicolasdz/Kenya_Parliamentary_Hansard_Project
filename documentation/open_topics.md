# Open Topics

Intended work, and questions that still need a final decision. When a question
here is settled and has project-wide impact, record it in the
[decision register](decision_register.md) and remove it from this file; finished
work can simply be removed.

- [Undecided](#undecided): questions deferred or still under discussion
- [Planned work](#planned-work): agreed in principle, not yet done

---

## Undecided

### Publishing and a citizen-facing front end

**Status:** on hold (2026-10-24). For now the project is published only as
code on GitHub; a user-friendly front end will be revisited later.

**Options discussed** (none chosen):
- **Static website**: one page per sitting and per member, generated from the
  database, with in-browser search (e.g. Pagefind), on free hosting such as
  Cloudflare Pages. Free, low-maintenance, works well on phones, and Google can
  index every sitting.
- **Datasette**: serves the database directly with search, filters, a JSON API
  and CSV export. Needs a host: Google Cloud Run's free tier (with a card on
  file) or a small paid server.
- **Custom web app**: most flexible (Kiswahili interface, alerts), but weeks of
  work and ongoing maintenance.
- **Bulk data release**: SQLite and Parquet files on Hugging Face Datasets or
  Zenodo (which gives a citable DOI), with a Colab notebook of example
  analyses. A complement to any of the above.
- **Partnering** with an existing Kenyan parliamentary-monitoring organisation.

**Findings so far:**
- Hugging Face Spaces no longer offers free Docker hosting: since about July
  2026, Docker and Gradio Spaces need a paid plan (PRO), and only static Spaces
  are free. Hugging Face dataset repositories are still free.
- Google Colab isn't a hosting option (sessions are temporary and have no
  stable public address), but it suits example notebooks for researchers.

**To decide:** the main audience (citizens, or researchers and journalists),
budget, and how much upkeep is acceptable. Before publishing anything, check
Parliament's terms of use, show the Hansard's own disclaimer (the certified
copy is the official record), and decide how to present duplicate copies of a
sitting and the limits of member matching.

### Parsing strategy: one file at a time or in parallel

**Status:** deferred (2026-10-23). Parsing runs one PDF at a time, about 2
seconds each.

**Background:** parsing in parallel worker processes on Windows caused random
crashes (access violations inside langdetect after PyMuPDF had run in the same
worker) whose cause wasn't found. Running one file at a time is fast enough
day to day, because only new PDFs are parsed: a weekly update takes under a
minute. A full rebuild takes about two hours.

**Lead to try:** Anaconda's outdated C++ runtime (`msvcp140.dll`) was later found
to break PyTorch on the same machine (see the
[user guide's troubleshooting](user_guide.md#troubleshooting)). It may also
explain the worker crashes, and the PyMuPDF 2.x import crash. Test parallel
parsing with the same workaround, or with a non-Anaconda Python.

**To decide:** whether faster rebuilds are worth the complexity, if the crash
can be fixed.

### Raw parliamentarian files

**Status:** left as they are for now (2026-10-24).

`inputs/parliamentarians/mps_raw.xlsx` holds the scraped member lists that the
members Google Sheet was built from; `googlesheet.tsv` is the exported copy the
pipeline uses. **To decide:** which file is the source of truth, and whether the
raw workbook stays in the repository.

---

## Planned work

### Delete the archived repository

Before the repository was prepared for publication (2026-10-25), its history
was rewritten to remove the ACLED and GADM data (whose licences don't allow
redistribution) and personal details, and pushed to a new repository. The
original, renamed `Kenya_Parliamentary_Hansard_Project_archive`, is private
and still contains the old history, including the licensed data. Keep it
private, and delete it once it's no longer needed as a fallback.

### Scheduled updates

Run `hansard scrape` and `hansard parse` automatically (for example weekly),
and report new sittings, failed downloads and data-quality changes. Running it
in the cloud needs somewhere to keep the PDFs (see [D2](decision_register.md#d2-hansard-pdfs-are-not-stored-in-git));
a scheduled task on the local machine works with the current setup.

### Member list gaps and aliases

Matching depends on `inputs/parliamentarians/googlesheet.tsv`, which:
- has no 11th Parliament (2013–2017) or 12th Senate (2017–2022), so speeches
  from those are never matched;
- misses some members, e.g. Sen. Gloria Orwoba, and Opiyo Wandayi in the 13th
  Parliament (listed only for the 12th);
- doesn't know other names members appear under in the Hansard, e.g.
  "Veronica Maina" (officially Veronica Waheti Nduati) and "Okiya Omtatah"
  (officially Okoiti Andrew Omtatah). An alias column would let these match.

These are edits to the Google Sheet, followed by a re-export to the TSV and
`hansard parse`. `hansard report` lists the most frequent unmatched speakers.

### Presiding officers

"Hon. Speaker", "Hon. Deputy Speaker" and similar lines (over 50,000 speeches)
aren't linked to a person. They could be resolved from who held each role on
each date.

### Members speaking in the other chamber

National Assembly members who speak in the Senate (for example as impeachment
managers) aren't matched, because matching only considers the chamber's own
members. Possible approach: fall back to the other chamber with a stricter
threshold.

### Duplicate copies of a sitting

About 80 sittings have more than one non-identical PDF: a joint sitting listed
under both chambers, or a revised upload. All copies are stored, so their
speeches appear more than once in searches and exports. Decide how to choose one
copy per sitting (e.g. the newest upload) and mark or hide the others.
`hansard report` lists them.

### Broken links on the website

34 Hansard links on parliament.go.ke return 404, almost all in two upload folders:
`2021-03` (National Assembly and Senate sittings, February–March 2021) and
`2017-05` (a few from November 2013 and 2017). Check whether the files moved to
other URLs. `hansard scrape` lists failures at the end of each run.

### Small data-quality items

- Two Hansards from 3 October 2013 (`Thursday_3rd_October_2013.pdf` and its
  copy) have no detected sitting time.
- About 140 speeches still contain fragments of the page disclaimer.
- The ACLED download in the Political Violence notebook (`USE_ACLED_API = True`)
  was rewritten for ACLED's current API but hasn't been run yet; run it once to
  confirm.

### Development tooling

- Continuous integration: run `pytest` on every push with GitHub Actions. The
  tests don't need the real PDFs, so this would work today.
- Linting and formatting with Ruff.
- A lock file of exact dependency versions, for reproducible installs (a fresh
  install once picked up an incompatible PyMuPDF).
- Re-test PyMuPDF 2.x (see [Parsing strategy](#parsing-strategy-one-file-at-a-time-or-in-parallel)).
