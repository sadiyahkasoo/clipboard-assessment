# Step: reading the website (scraping)

## What this step does

It visits the Bellhaven Senior Living website and writes down every community it lists: name, street, city, state, zip, care offerings, administrator and phone number.

It only reads. It changes nothing on the website or in the CRM.

## How it finds every community

The website has a directory of communities spread over three pages, and one page of details per community. Two things about the site would trip up a simple approach:

1. **The directory is not the full list.** The directory shows 34 communities, but the home page says Bellhaven serves 35. The 35th, *Bellhaven Meadows of Findlay*, is linked only from a "new this year" notice on the home page. So the tool collects community links from **every** page it visits (home, about, and each directory page), not just the directory.
2. **Asking for a page that does not exist returns the last page again**, instead of an error. A tool that counts "page 1, page 2, page 3, page 4..." until it gets nothing would loop forever or double-count. So the tool never counts pages. It follows the "Next" link the site itself shows, and remembers which pages it has already seen.

Once it has the full list of links, it opens each community's page and reads the details.

## Safety checks

- If a community page has no heading or no readable address, the run stops with an error. A broken page never becomes a half-empty record.
- If a run finds fewer than 80% of the communities the last good run found, the whole daily job stops without proposing anything. A website outage should not make every CRM account look like it "left" Bellhaven.

## What is saved, so the step can be re-traced

Each run saves a folder `data/runs/<date and time>/01_scrape/` containing:

| File | What it holds |
|---|---|
| `pages/*.html` | Every web page exactly as it was downloaded |
| `locations.json` | The list of communities read from those pages |
| `report.json` | Which pages were visited, which page each community was found on, and the counts the site states about itself (34 in the directory, 35 on the home page) |

Because the raw pages are kept, anyone can check a community's saved page against what the tool read from it, without going back to the website.

## Result of the first run

- 5 listing pages visited (home, about, three directory pages).
- 35 communities found: 34 from the directory and 1 found only on the home page.
- All 35 had a complete address and at least one care offering.

## Where the code is

- `src/bellhaven_sync/scraper.py`
- Tests: `tests/test_scraper.py` (run against saved copies of the pages in `tests/fixtures/site/`)
