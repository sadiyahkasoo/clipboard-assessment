# Bellhaven ownership sync

Keeps CRM facility-to-parent links in step with the communities listed on the Bellhaven Senior Living website.

1. **Scrape** every community from the website.
2. **Match** each one to CRM accounts and classify it.
3. **Review** each proposed change, with its evidence, in a local web app. Nothing is written without an approval.
4. **Run daily**, safely: anything already decided is never proposed again.

## Where to read more

Plain-language documents, in order:

| Document | About |
|---|---|
| [docs/00-rules.md](docs/00-rules.md) | The rules this exercise follows |
| [docs/01-plan.md](docs/01-plan.md) | The plan |
| [docs/02-scraping.md](docs/02-scraping.md) | Reading the website |
| [docs/03-matching-explained.md](docs/03-matching-explained.md) | How matching works and how the cut-offs were chosen |
| [docs/04-review-app.md](docs/04-review-app.md) | The review app and its audit trail |
| [docs/05-daily-schedule.md](docs/05-daily-schedule.md) | The daily schedule |
| [docs/06-smoke-test.md](docs/06-smoke-test.md) | How everything was checked before any real change |
| [docs/demo/](docs/demo/) | Recording of the demo |
| [docs/writeup.md](docs/writeup.md) | Write-up of the choices made |

## Setup

Requires Python 3.12 or newer.

    python -m venv .venv
    .venv/bin/pip install -r requirements.txt
    cp .env.example .env      # then paste your CRM sandbox token into .env

## Commands

All commands are run from the project folder.

| What | Command |
|---|---|
| Back up the CRM | `PYTHONPATH=src .venv/bin/python -m bellhaven_sync.backup` |
| Run the tests | `PYTHONPATH=src .venv/bin/python -m pytest` |
| Build a fresh rehearsal copy of the CRM | `PYTHONPATH=src .venv/bin/python -m bellhaven_sync.rehearsal reset` |
| Daily job, rehearsal | `PYTHONPATH=src .venv/bin/python -m bellhaven_sync.pipeline --mode rehearsal` |
| Daily job, real CRM (read-only) | `PYTHONPATH=src .venv/bin/python -m bellhaven_sync.pipeline --mode live` |
| Dry run: print the requests that would be sent | add `--print-plan` to either pipeline command |
| Review app (opens in Rehearsal; switch to Production in the app) | `PYTHONPATH=src .venv/bin/python -m bellhaven_sync.review_app` |
| Review app with Production switched off | `PYTHONPATH=src .venv/bin/python -m bellhaven_sync.review_app --rehearsal-only` |
| Switch on the daily schedule | `crontab schedule/crontab.txt` |

The review app opens at http://127.0.0.1:5001.

## Layout

    docs/                 plain-language documents
    src/bellhaven_sync/   the code
        backup.py         full CRM backup (read-only)
        scraper.py        reads the website
        normalize.py      tidies text before comparing
        matcher.py        scores community/account pairs
        classify.py       turns scores into proposed changes
        audit_db.py       audit trail database (SQLite)
        apply.py          sends an approved change to the CRM and verifies it
        crm_client.py     the real CRM, and a local stand-in for rehearsal
        pipeline.py       the read-only daily job
        rehearsal.py      builds the rehearsal copy of the CRM
        review_app/       the local review website
    tests/                automated tests and saved sample data
    data/backups/         CRM backup taken before any change
    data/runs/            one dated folder of trace records per daily run
    data/audit.db         audit trail database
    data/decisions/       readable export of the audit trail
    logs/                 daily run log
    schedule/crontab.txt  the daily schedule entry
