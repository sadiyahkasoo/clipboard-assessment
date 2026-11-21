"""
Step 2: read every Bellhaven community from the public website.

The website has three kinds of page we care about:
    /                     home page (links to featured communities)
    /about                about page
    /communities?page=N   paginated directory of community cards
    /communities/<slug>   one detail page per community

Two quirks shape how this scraper works:

1. The directory is NOT the full list. At least one community is linked only
   from the home page. So we collect community links from every page we
   visit, not just the directory.
2. Asking for a directory page beyond the last one silently returns the last
   page again. So we never count pages; we only follow the "Next" links the
   site itself gives us, and we remember which pages we have already seen.

Parsing (turning HTML into data) is kept separate from fetching (downloading
HTML) so the parsing can be tested against saved pages without the internet.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from . import config

# Pages we start crawling from.
START_PATHS: tuple[str, ...] = ("/", "/about", "/communities")

# A community detail link looks like /communities/<slug> (no query string).
_COMMUNITY_LINK = re.compile(r"^/communities/([a-z0-9][a-z0-9-]*)$")

# "Maplewood, OH 44280" -> city, state, zip
_CITY_STATE_ZIP = re.compile(r"^(?P<city>.+?),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5})(?:-\d{4})?$")


@dataclass
class Location:
    """One community as published on the website.

    Attributes:
        slug: The last part of the page address, e.g. "bellhaven-of-tiffin".
            It is the website's own stable identifier for the community.
        url: Full address of the detail page.
        name: Community name as shown in the page heading.
        street: Street line of the address.
        city: City.
        state: Two-letter state code.
        zip: Five-digit zip code.
        care_offerings: Care types listed on the page, in page order.
        administrator: Administrator's name (used only as matching evidence).
        phone: Phone number as shown (used only as matching evidence).
    """

    slug: str
    url: str
    name: str
    street: str
    city: str
    state: str
    zip: str
    care_offerings: list[str] = field(default_factory=list)
    administrator: str = ""
    phone: str = ""


class ScrapeError(RuntimeError):
    """Raised when a page cannot be read into the data we expect."""


def parse_links(html: str) -> tuple[list[str], list[str]]:
    """Find community links and directory-page links on any page.

    Args:
        html: Raw HTML of a page.

    Returns:
        A pair (community_slugs, directory_paths):
            community_slugs: slugs of every /communities/<slug> link, in page
                order, without repeats.
            directory_paths: every /communities?page=N link found (the pager).
    """
    soup = BeautifulSoup(html, "html.parser")
    slugs: list[str] = []
    pages: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        parsed = urlparse(href)
        # Ignore links that leave the site.
        if parsed.netloc and parsed.netloc != urlparse(config.SITE_BASE).netloc:
            continue
        match = _COMMUNITY_LINK.match(parsed.path)
        if match and not parsed.query:
            if match.group(1) not in slugs:
                slugs.append(match.group(1))
        elif parsed.path == "/communities" and "page" in parse_qs(parsed.query):
            path = f"/communities?page={parse_qs(parsed.query)['page'][0]}"
            if path not in pages:
                pages.append(path)
    return slugs, pages


def parse_claimed_count(html: str) -> int | None:
    """Read a "34 communities listed" / "serve 35 communities" style number.

    The site states its own community count in two places. We record these
    so the trace shows whether what we scraped agrees with what the site says.

    Args:
        html: Raw HTML of a page.

    Returns:
        The number found, or None if the page states no count.
    """
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    match = re.search(r"(\d+)\s+communities", text)
    return int(match.group(1)) if match else None


def parse_detail(html: str, slug: str) -> Location:
    """Turn one community detail page into a Location.

    The page is a heading plus a definition list of labelled values
    (Address, Care Offerings, Administrator, Phone).

    Args:
        html: Raw HTML of the detail page.
        slug: The community's slug (from its address).

    Returns:
        The community's details.

    Raises:
        ScrapeError: if the heading or address is missing or unreadable, so a
            broken page can never turn into a half-empty record.
    """
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one("div.wrap h1") or soup.find("h1")
    detail = soup.select_one("dl.detail")
    if heading is None or detail is None:
        raise ScrapeError(f"{slug}: page has no heading or detail list")

    # Build {label: <dd> element} from the definition list.
    values: dict[str, object] = {}
    for label in detail.find_all("dt"):
        value = label.find_next_sibling("dd")
        if value is not None:
            values[label.get_text(strip=True)] = value

    address = values.get("Address")
    if address is None:
        raise ScrapeError(f"{slug}: no Address on page")
    # The address is "street<br>city, ST zip"; split on the line break.
    lines = [line.strip() for line in address.get_text("\n", strip=True).split("\n") if line.strip()]
    if len(lines) < 2:
        raise ScrapeError(f"{slug}: address has {len(lines)} line(s), expected 2")
    place = _CITY_STATE_ZIP.match(lines[-1])
    if not place:
        raise ScrapeError(f"{slug}: cannot read city/state/zip from {lines[-1]!r}")

    offerings = values.get("Care Offerings")
    care = [b.get_text(strip=True) for b in offerings.select("span.badge")] if offerings else []

    def text_of(label: str) -> str:
        element = values.get(label)
        return element.get_text(" ", strip=True) if element is not None else ""

    return Location(
        slug=slug,
        url=f"{config.SITE_BASE}/communities/{slug}",
        name=heading.get_text(" ", strip=True),
        street=" ".join(lines[:-1]),
        city=place.group("city").strip(),
        state=place.group("state"),
        zip=place.group("zip"),
        care_offerings=care,
        administrator=text_of("Administrator"),
        phone=text_of("Phone"),
    )


def http_fetcher(session: requests.Session | None = None) -> Callable[[str], str]:
    """Build a function that downloads a page from the live website.

    Args:
        session: Optional requests session to reuse connections.

    Returns:
        A function taking a site path ("/communities?page=2") and returning
        the page's HTML. It raises on any non-200 answer.
    """
    session = session or requests.Session()

    def fetch(path: str) -> str:
        response = session.get(config.SITE_BASE + path, timeout=config.HTTP_TIMEOUT)
        response.raise_for_status()
        return response.text

    return fetch


def file_fetcher(folder: Path) -> Callable[[str], str]:
    """Build a function that "downloads" pages from saved files instead.

    Used by tests and for replaying an earlier run exactly.

    Args:
        folder: Folder of pages saved by `crawl` (see `_filename_for`).

    Returns:
        A function with the same shape as the one from `http_fetcher`.
    """

    def fetch(path: str) -> str:
        return (folder / _filename_for(path)).read_text(encoding="utf-8")

    return fetch


def _filename_for(path: str) -> str:
    """Map a site path to a safe file name for saving the raw page.

    Args:
        path: Site path such as "/", "/communities?page=2".

    Returns:
        A file name such as "home.html" or "communities_page-2.html".
    """
    if path == "/":
        return "home.html"
    cleaned = path.strip("/").replace("/", "_").replace("?", "_").replace("=", "-")
    return f"{cleaned}.html"


def crawl(fetch: Callable[[str], str], save_dir: Path | None = None) -> tuple[list[Location], dict]:
    """Visit the site and return every community found.

    Args:
        fetch: Function that returns the HTML for a site path.
        save_dir: If given, every page is saved here exactly as downloaded
            (the scraping trace), plus `locations.json` and `report.json`.

    Returns:
        A pair (locations, report):
            locations: one Location per community, in discovery order.
            report: how the crawl went - pages visited, where each community
                was found, and the counts the site claims about itself.

    Raises:
        ScrapeError: if no communities are found at all.
    """
    pages_dir = (save_dir / "pages") if save_dir else None
    if pages_dir:
        pages_dir.mkdir(parents=True, exist_ok=True)

    def get(path: str) -> str:
        html = fetch(path)
        if pages_dir:
            (pages_dir / _filename_for(path)).write_text(html, encoding="utf-8")
        return html

    to_visit: list[str] = list(START_PATHS)
    visited: list[str] = []
    found_on: dict[str, list[str]] = {}   # slug -> pages that link to it
    claimed: dict[str, int] = {}          # page -> community count it states

    # Breadth-first walk over the listing pages, following pager links.
    while to_visit:
        path = to_visit.pop(0)
        # "/communities" and "/communities?page=1" are the same page.
        canonical = "/communities?page=1" if path == "/communities" else path
        if canonical in visited:
            continue
        visited.append(canonical)
        html = get(canonical)
        slugs, pager = parse_links(html)
        count = parse_claimed_count(html)
        if count is not None:
            claimed[canonical] = count
        for slug in slugs:
            found_on.setdefault(slug, []).append(canonical)
        for next_page in pager:
            if next_page not in visited and next_page not in to_visit:
                to_visit.append(next_page)

    if not found_on:
        raise ScrapeError("No community links found on the website.")

    locations = [parse_detail(get(f"/communities/{slug}"), slug) for slug in found_on]

    directory_slugs = {s for s, pages in found_on.items() if any(p.startswith("/communities?") for p in pages)}
    report = {
        "pages_visited": visited,
        "communities_found": len(locations),
        "communities_in_directory": len(directory_slugs),
        "only_outside_directory": sorted(set(found_on) - directory_slugs),
        "counts_claimed_by_site": claimed,
        "found_on": found_on,
    }
    if save_dir:
        (save_dir / "locations.json").write_text(
            json.dumps([asdict(loc) for loc in locations], indent=2), encoding="utf-8"
        )
        (save_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return locations, report


if __name__ == "__main__":
    # Quick manual check: print what the live site lists. Saves nothing.
    found, summary = crawl(http_fetcher())
    for loc in found:
        print(f"{loc.name} | {loc.street}, {loc.city}, {loc.state} {loc.zip} | {', '.join(loc.care_offerings)}")
    print(json.dumps({k: v for k, v in summary.items() if k != "found_on"}, indent=2))
