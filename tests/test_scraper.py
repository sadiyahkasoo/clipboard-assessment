"""Tests for the website scraper, run against saved pages."""

import pytest

from bellhaven_sync import scraper


def test_finds_every_community_including_the_one_missing_from_the_directory(site_fetch):
    """The directory lists 34, but a 35th is linked only from the home page."""
    locations, report = scraper.crawl(site_fetch)
    assert len(locations) == 35
    assert report["communities_in_directory"] == 34
    assert report["only_outside_directory"] == ["bellhaven-meadows-of-findlay"]
    assert len({loc.slug for loc in locations}) == 35   # no repeats


def test_follows_pager_links_and_never_revisits_a_page(site_fetch):
    """Pages are discovered from the site's own Next links, each visited once."""
    _locations, report = scraper.crawl(site_fetch)
    assert report["pages_visited"] == [
        "/", "/about", "/communities?page=1", "/communities?page=2", "/communities?page=3"]


def test_records_the_counts_the_site_claims(site_fetch):
    """The trace keeps what the site says about itself, for cross-checking."""
    _locations, report = scraper.crawl(site_fetch)
    assert report["counts_claimed_by_site"]["/"] == 35
    assert report["counts_claimed_by_site"]["/communities?page=1"] == 34


def test_detail_page_fields(locations):
    """Name, split address, care offerings, administrator and phone are read."""
    erie = next(loc for loc in locations if loc.slug == "bellhaven-shores-of-erie")
    assert erie.name == "Bellhaven Shores of Erie"
    assert (erie.street, erie.city, erie.state, erie.zip) == ("4930 W Lake Rd", "Erie", "PA", "16505")
    assert erie.care_offerings == ["Assisted Living", "Memory Support"]
    assert erie.administrator == "Angela Quinn"
    assert erie.phone == "(614) 792-9343"


def test_ampersand_in_name_is_decoded(locations):
    """HTML escapes such as &amp; become real characters."""
    grove = next(loc for loc in locations if "grove-city" in loc.slug)
    assert grove.name == "Bellhaven Rehabilitation & Nursing of Grove City"


def test_every_location_is_complete(locations):
    """No community is missing a required field."""
    for loc in locations:
        assert loc.name and loc.street and loc.city and len(loc.state) == 2 and len(loc.zip) == 5
        assert loc.care_offerings


def test_broken_detail_page_raises_instead_of_returning_half_a_record():
    """A page without an address must fail loudly."""
    with pytest.raises(scraper.ScrapeError):
        scraper.parse_detail("<html><body><h1>Oops</h1></body></html>", "oops")


def test_crawl_saves_the_trace(site_fetch, tmp_path):
    """Raw pages, the location list and the report are written for re-tracing."""
    scraper.crawl(site_fetch, tmp_path)
    assert (tmp_path / "pages" / "home.html").exists()
    assert (tmp_path / "pages" / "communities_page-2.html").exists()
    assert (tmp_path / "locations.json").exists() and (tmp_path / "report.json").exists()
