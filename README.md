# Kenya Parliamentary Hansard Project

A data pipeline that collects, cleans, makes searchable, and publishes the
Hansard (the official verbatim record) of Kenya's National Assembly and Senate,
so that citizens can more easily access these public records.

**Status:** collecting, parsing and searching work. The database covers the
sittings published on parliament.go.ke from March 2013 onwards: about 2,800
sittings and half a million speeches, each with its speaker (matched to a
member where possible) and a link to the official PDF. A public, user-friendly front
end is not built yet.

## Getting started

Requires Python 3.10 or later.

```bash
git clone https://github.com/nicolasdz/Kenya_Parliamentary_Hansard_Project.git
cd Kenya_Parliamentary_Hansard_Project
python -m venv .venv
.venv/Scripts/activate        # Windows; on macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

The Hansard PDFs aren't stored in the repository, so the first step is to
download them, then parse them into a searchable database:

```bash
hansard scrape        # download the Hansard PDFs (about 1.6 GB, an hour or two the first time)
hansard parse         # build outputs/hansard.db (about two hours the first time)
hansard search housing levy --chamber senate --from 2023-01-01
```

After that, running `hansard scrape` and `hansard parse` again fetches and adds
only new sittings, which takes a minute or two. Other commands:

```bash
hansard report        # data-quality summary
hansard export        # every speech, with member details, to outputs/speeches.csv
```

Run any command with `--help` for its options.

## Documentation

- **[User guide](documentation/user_guide.md)**: every command in detail, how
  to write searches, how the pipeline works, and the research notebooks.
- **[Decision register](documentation/decision_register.md)**: major settled
  decisions and why they were made.
- **[Open topics](documentation/open_topics.md)**: planned work and questions
  still to be decided.

## License

The code is released under the [MIT License](LICENSE). This covers the code
only: Hansard records belong to the Parliament of Kenya, and third-party
datasets used by the research notebooks have their own terms (see the
[user guide](documentation/user_guide.md#third-party-data)).

## Acknowledgements

I am grateful to all the staff at the Kenyan Parliament for their work in transcribing floor speeches, collecting them into Hansards, and publishing them online.  This project is intended to make their excellent work even more accessible to ordinary Kenyans. 

This project was originally begun as a Data Research Fellowship supported by the Baylor University Libraries' Data & Digital Scholarship initiative.  I am exceedingly grateful to Sinai Wood and Josh Been for their support and assistance. In particular, Josh coded the original versions of the scraper and parser used in this project.
