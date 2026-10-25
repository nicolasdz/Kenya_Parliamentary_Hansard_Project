# Decision Register

Major settled decisions with near project-wide impact, recorded so they aren't
reopened without a reason. Routine coding and workflow choices don't belong
here (the code, commit history and [user guide](user_guide.md) cover those), and
neither do questions still under discussion or deferred: those live in
[open topics](open_topics.md).

To revisit a decision, check its "Revisit if" condition first. If it's met,
move the question to open topics; once it's settled again, update the entry
here, keeping the old decision under its history.

Each entry records the date, the decision, why it was made, the alternatives
considered, and what would make it worth revisiting.

---

## D1. SQLite is the data store and search engine

**Decided:** 2026-10-23

**Decision:** All parsed data lives in one SQLite file (`outputs/hansard.db`),
holding documents, speeches and members. Full-text search uses SQLite's
built-in FTS5 index in the same file, with the `unicode61` tokenizer and **no
stemming**, so English and Kiswahili text are handled the same way.

**Why:**
- One portable file, with no server to install, run or pay for. It suits a
  small, mostly read-only, single-maintainer project.
- At this scale (about 2,800 sittings and half a million speeches, growing by a
  few megabytes a week) SQLite is fast: most searches take 10–100 ms.
- The same file works for the command line, the research notebooks, CSV
  exports, and publishing tools that read SQLite directly (Datasette, or
  SQLite running in a browser), so a future front end doesn't force a change.
- English stemmers would mangle Kiswahili words, and good Kiswahili stemming
  isn't readily available. Without stemming, both languages behave predictably;
  users search for word variants with `OR` or a prefix (`word*`).

**Alternatives considered:**
- **CSV files** (the original output): no search, no relationships between
  speeches and members, and too large to work with comfortably (over 400 MB).
- **PostgreSQL** with its full-text search: more capable, but needs a running
  server, which isn't justified at this size.
- **A separate search engine** (Elasticsearch, Meilisearch, Typesense): better
  ranking and typo tolerance, but another service to run and keep in sync.
- **FTS5 with the Porter (English) stemmer**: better English recall, but wrong
  for Kiswahili.

**Revisit if:** many people need to write to the data at once; the data
outgrows a single file (tens of GB); search quality becomes the main complaint,
for example a need for typo tolerance or Kiswahili-aware matching; or a chosen
publishing route can't use SQLite.

---

## D2. Hansard PDFs are not stored in git

**Decided:** 2026-10-23

**Decision:** The source PDFs are kept locally (`inputs/*_hansards/`), outside
version control. They can be re-downloaded at any time with `hansard scrape`.
The repository holds the code plus `inputs/manifest.csv`, which records every
PDF's official source URL. PDFs already committed were purged from the entire
git history.

**Why:**
- The PDFs made the repository over 1 GB (now under 5 MB), which slowed every
  clone and push.
- They are public records that already have an authoritative home
  (parliament.go.ke); the manifest keeps the link to each one, so every speech
  can still point to its official PDF and page.
- Everything derived from them (the database, exports) is reproducible from
  the PDFs and the code.

**Alternatives considered:**
- **Keep them in git**: simple, but the repository grows with every scrape.
- **Git LFS**: keeps them versioned, but every download counts against GitHub's
  LFS storage and bandwidth quotas, and it adds setup for every user.
- **Cloud storage** (e.g. a storage bucket) as the archive: worth it if the
  website's copies become unreliable, but an extra service to manage for now.

**Revisit if:** the website removes or changes Hansards so they can no longer
be re-downloaded (34 links already return 404); collaborators need a shared copy
of the exact PDFs that were parsed; or the project needs a permanent public
archive of the source files.
