"""
Shared test fixtures.

All tests run OFFLINE against saved copies:
    tests/fixtures/site/pages/*.html   the Bellhaven website as scraped
    tests/fixtures/crm/*.json          the CRM as first backed up

Nothing in the test suite can reach the real website or the real CRM.
"""

import json
from pathlib import Path

import pytest

from bellhaven_sync import audit_db, classify, scraper
from bellhaven_sync.crm_client import LocalCrm

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def site_fetch():
    """Return a fetch function that serves the saved website pages."""
    return scraper.file_fetcher(FIXTURES / "site" / "pages")


@pytest.fixture(scope="session")
def locations(site_fetch):
    """Return the communities parsed from the saved website pages."""
    found, _report = scraper.crawl(site_fetch)
    return found


@pytest.fixture(scope="session")
def accounts():
    """Return the CRM accounts from the original backup."""
    return json.loads((FIXTURES / "crm" / "accounts.json").read_text())


@pytest.fixture(scope="session")
def contacts():
    """Return the CRM contacts from the original backup."""
    return json.loads((FIXTURES / "crm" / "contacts.json").read_text())


@pytest.fixture()
def crm(accounts, contacts):
    """Return a fresh in-memory stand-in CRM holding the backup data."""
    return LocalCrm(path=None, accounts=accounts, contacts=contacts)


@pytest.fixture()
def db():
    """Return a fresh in-memory audit trail."""
    return audit_db.AuditDb(":memory:")


@pytest.fixture(scope="session")
def result(locations, accounts, contacts):
    """Return the classification of the saved website against the backup CRM."""
    return classify.classify(locations, accounts, contacts)


def by_title(proposals, text):
    """Return the single proposal whose title contains `text` (test helper)."""
    hits = [p for p in proposals if text in (p.title if hasattr(p, "title") else p["title"])]
    assert len(hits) == 1, f"expected one proposal matching {text!r}, got {len(hits)}"
    return hits[0]
