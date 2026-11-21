# Bellhaven CRM clean-up: plan

## Context (why we are doing this)

Bellhaven Senior Living lists its communities on its website. Our CRM copy has about 120 accounts, and some are out of date: wrong owner, old names, duplicates, or missing altogether. We need a small system that:

1. reads every community from the website,
2. compares each one with the CRM,
3. shows a reviewer each suggested fix with the evidence for it,
4. writes a fix to the CRM only after the reviewer approves it,
5. can run every day without asking the same question twice.

The graded result is the **corrected CRM**, plus the tool, a write-up and a 2-minute demo video.

## Your working rules (these will be saved to `docs/00-rules.md`)

1. **Back up first.** Before anything else, save a full local copy of every CRM account and contact.
2. **Smoke test before any real change.** The CRM has no delete or undo, so every change is rehearsed and checked before it is sent for real.
3. **Plans live in `docs/` as `.md` files**, written in plain language a non-technical colleague can follow. This includes these rules.
4. **Every Python file is clearly commented**, explaining what the code does. Comments may use technical terms (arguments, return values).
5. **Clean folder layout**, with source code and tests kept apart.
6. **No outside library is installed without your approval** (list below).
7. **Billing rule (from the brief).** Before moving an account to a different owner, check its billing history. If it has past revenue AND money still owed, do not touch it: create a new account under the right owner and point the old one to it. Otherwise move it directly.
8. **Nothing is written to the CRM without an approval** in the review app.
9. **Every step can be re-traced.** Scraping, matching, the review app and the daily schedule each leave a record of what went in, what came out and why.
10. **The daily schedule is built last and is made live** on this computer.
11. **Matching is explained in detail**, including how the score cut-offs were chosen.
12. **Final work is stored in GitHub** at `https://github.com/sadiyahkasoo/clipboard-assessment`, with commits shown under Sadiyah's name.

## What I found (read-only look, nothing changed)

- Your token works. The CRM reports the candidate name on it as "Sadiyah Kasoo".
- **Website:** 35 communities. The directory lists only 34; *Bellhaven Meadows of Findlay* appears only as a link on the home page. The scraper must follow every community link, not just the directory. Asking for a page past the last one silently repeats the last page, so the scraper follows the "Next" link instead of counting pages.
- **CRM:** 121 accounts (6 are owner-company accounts, 29 facilities sit under Bellhaven) and 67 contacts.
- **The CRM can:** list, read, create and update accounts and contacts. It cannot delete or merge. The docs do not say which fields are required when creating an account, so that is confirmed during the smoke test.

### Changes I expect the tool to propose (about 29)

| Situation | Communities | Proposed action |
|---|---|---|
| Already correct | about 15 (Maplewood, Wooster, Akron, ...) | None. Shown for information only. |
| Small name difference | Grove City, Sycamore Ridge, Arbors Dayton, Ashland | Update the name to match the website |
| Old name, right owner | Chagrin Falls (now "Riverbend Manor Care Center"), Willow Creek ("Sunny Acres Retirement Home"), Chesterton ("Chesterton Senior Commons") | Rename |
| Typo in zip code | Portsmouth (45626 should be 45662) | Fix the zip |
| Address differs | Ashtabula (CRM has a PO Box, website has a street address) | Low-confidence suggestion; likely a reject, since a PO Box is a valid billing address |
| Wrong owner, safe to move | Lima (revenue but nothing owed), Zanesville (also needs renaming), Findlay (no owner set) | Move under Bellhaven directly |
| Wrong owner, billing rule applies | Tiffin (owes 12,400), Marietta (owes 3,800) | Leave old account untouched, create a new one under Bellhaven, point old to new |
| No CRM account | Batavia, Carlisle PA, Amberly Manor (Hudson OH), Union Square | Create a new account. Lookalikes are shown as evidence but not touched: "Amberly Manor" in Colorado, "Union Square Senior Living" at a different street with a different administrator, and "New Carlisle" in Ohio. |
| Duplicates | Port Clinton, Erie, Owosso (1 extra copy each), Monroe (2 extra copies), Kettering (3 copies, none under Bellhaven) | Keep one, mark the others Inactive and point them to the kept one. For Kettering, the kept copy is also renamed and moved under Bellhaven. |
| Under Bellhaven but not on the website | Alliance, Coldwater | Mark "Needs Review" with a note |
| Sold to another owner | Sandusky (owes 5,200; a "Millstone Care of Sandusky" account exists at the same address) | Leave as is and point it to the Millstone account |

Decisions built into the plan:

- **Phone numbers are evidence only.** Many differ between website and CRM, but the CRM number may be a billing line, so the tool does not propose phone changes.
- **Kettering is the least certain item.** Nothing clearly shows which of the three copies should survive. The tool applies a fixed rule (billing history first, then contacts, then a known previous owner) and the reviewer sees all three side by side.

## How matching works (saved in full to `docs/03-matching-explained.md`)

Each website community is compared with every CRM account **in the same state**. Each pair gets a score out of 100, built from six pieces of evidence:

| Evidence | Points | Why this weight |
|---|---|---|
| Street address is the same | 40 | A building does not move when owners or names change. This is the strongest clue. |
| Zip code is the same | 15 (8 if two digits are swapped) | Confirms the place; a swapped-digit zip is treated as a typo, not a different place |
| City is the same | 10 | Supports the address |
| Name is similar | 0 to 20 | Names change on rebrand, so the name helps but cannot decide alone |
| Phone number is the same | 10 | Useful when present, but often differs |
| Website administrator is a CRM contact on the account | 5 | A small extra confirmation |

Before comparing, text is tidied so that spelling habits do not count as differences: "Ln" and "Lane", "W" and "West", "Rehab" and "Rehabilitation", "Centre" and "Center", "&" and "and". Words every name shares ("Bellhaven", "of", "the") are ignored. An account in a different state scores zero, which rules out the "Amberly Manor" in Colorado.

**Cut-offs and how they were chosen**

| Score | Meaning | What the tool does |
|---|---|---|
| 65 or more | Same facility | Treated as a match. If several accounts reach this, they are duplicates of each other. |
| 50 to 64 | Probably the same facility | Shown as a match, but marked low confidence so the reviewer decides |
| 30 to 49 | Lookalike | Shown as evidence only. The account is never changed. |
| Under 30 | Unrelated | Ignored |

- **Why 65:** street + zip + city add up to exactly 65. An account at the very same address is the same building, whatever it is called. This is what catches the renamed facilities ("Sunny Acres Retirement Home" scores 71, "Riverbend Manor Care Center" 75).
- **Why 50 and 30:** I scored all 35 communities against all accounts (a read-only test, nothing saved or changed). The scores fall into clear groups with wide empty gaps between them:
  - 37 pairs score 65 to 100. Every one is a real match (lowest: 71).
  - 1 pair scores 60: Ashtabula, where everything matches except the street (the CRM holds a PO Box).
  - 2 pairs score 35 and 38: the lookalikes "Maplewood Senior Care Center" and "Union Square Senior Living" (same town, different street, phone and administrator).
  - Everything else, about 1,450 pairs, scores under 20.
  - The cut-offs sit inside the empty gaps (39 to 59, and 20 to 34), so no pair is close to a line.
- **Honest limit:** these cut-offs are fitted to one small data set. The tool saves every score with its six-part breakdown on every run, so if a future pair lands near a line it is visible and the cut-offs can be revisited.

**After matching, each community is put into one group:**

1. One match, right owner, details agree: **confident match**, nothing to do.
2. One match, but name, zip or owner differs: **needs a fix** (the billing rule decides *how* an owner change is made).
3. Several matches: **duplicates**. One is kept: the one already under Bellhaven if there is one, otherwise the one with billing history, then contacts, then a known previous owner. The rest are marked Inactive and pointed at the kept one.
4. No match: **new account needed**, with any lookalikes shown.
5. Accounts under Bellhaven that no community matched: **no longer on the website**.

## Re-tracing every step

Each run gets its own dated folder, so anyone can follow what happened without re-running anything:

| Step | What is saved |
|---|---|
| Backup | Full copy of accounts and contacts, with the date and counts |
| Scraping | Every web page exactly as downloaded, plus the list of communities read from them |
| Matching | Every score with its six-part breakdown, the group each community landed in, and the reason in a plain sentence |
| Review app | Each decision: what was proposed, the evidence shown, approve or reject, the reason, the exact change sent, the CRM's reply, and before and after values |
| Daily schedule | A log line per run: when it ran, how many communities and accounts it read, how many new suggestions it made |

These records are saved to GitHub with the code (the data is fictional; the API token is never saved there). Each step is also its own commit, and each has a short plain-language page in `docs/`.

## Git and GitHub

What I found on this computer: the default git name is not Sadiyah's, GitHub is signed in as a different account (`isdawjee`), and the new repository is reachable and empty.

- **Showing Sadiyah on commits:** the name and email are set *for this folder only*, leaving the computer's defaults untouched:
  ```
  git config user.name  "Sadiyah Kasoo"
  git config user.email "<email on the sadiyahkasoo GitHub account>"
  ```
  GitHub links a commit to a profile by the email, so it must be one registered on that account (the private "noreply" address from GitHub's email settings also works).
- **Needed from you before the first commit:**
  1. The email address to use.
  2. Push access. The signed-in account can read the repository but needs to be added as a collaborator to push, or Sadiyah's own sign-in is used. Commits still show Sadiyah as author either way.
- Nothing is pushed without your go-ahead.

## How it will work

**Daily run (reads only, never writes to the CRM):**

1. Scrape the website.
2. Download the current CRM accounts.
3. Match each community to accounts using address, zip, name, phone and administrator name.
4. Classify each one and save the suggestions to a local decisions file.

**Safety checks in the daily run:**

- If the website returns far fewer communities than last time (for example, the site is down), the run stops instead of flagging everything as "missing".
- Every suggestion has a fixed identity based on what it would change. If it was already approved or rejected, it is not suggested again.

**Review app (runs on your computer, opened in a browser):**

- Lists each suggestion with before and after values, the evidence (website details, matching fields, billing figures, lookalikes) and a confidence level.
- Has Approve and Reject buttons, with an optional reason.
- On approval, sends the change to the CRM, reads the account back to confirm it landed, and records the result.
- Multi-step changes (create a new account, then point the old one to it) remember their progress, so a retry never creates a second account.

**Audit trail (a local database file, `data/audit.db`):**

The review app keeps its own permanent record of everything it did. It is built into Python (SQLite), so nothing extra is installed. Records are only ever added, never edited or removed. It holds four lists:

| List | One row per | What it records |
|---|---|---|
| Runs | Daily run | When it ran, how many communities and accounts it read, how many suggestions it made |
| Suggestions | Proposed change | Which community and account, the kind of change, the evidence and score shown, confidence, and current state (waiting, approved, rejected, applied, failed) |
| Reviews | Approve or reject click | Which suggestion, the decision, the reason typed in, and the date and time |
| CRM changes | Request sent to the CRM | Which review caused it, the account, each field's value **before** and **after**, the exact request, the CRM's reply, whether it succeeded, and the read-back check that confirmed it landed |

- Every CRM change row links back to the review that authorised it, so there is never a change without an approval behind it.
- The "before" values make it possible to put any edit back.
- This is also what stops the tool asking twice: a suggestion that already has a review is not raised again.
- The app has an **Audit trail page** showing this history, and the same history is exported as a readable file (`data/decisions/audit-export.csv`) saved to GitHub, since a database file cannot be read on GitHub.

**Look and feel of the review app:**

- Built with Bootstrap (a standard, free styling kit) for a clean layout that works at any window size.
- Styled after clipboard.com. From its public style sheet I noted: warm cream backgrounds, a dark maroon for text and the top bar, a bright yellow accent for primary buttons, a serif typeface (Lora) for headings and a plain sans-serif (Work Sans) for body text, and softly rounded corners.
- It borrows the colours and typefaces only. It does not use the Clipboard logo or name, so it reads as "in their style" rather than passing itself off as their product.
- I worked from the style sheet, not a picture of the site. If you share a screenshot of the look you want, I will match it more closely.
- Pages:
  - **Review queue:** cards grouped by kind of change, with filters and counts of waiting, approved and rejected.
  - **Suggestion detail:** website and CRM values side by side with differences highlighted, the score breakdown, billing figures, lookalikes, and the Approve and Reject buttons.
  - **Audit trail:** the history described above.
- A clear banner shows whether the app is in **Rehearsal** (local copy) or **Live** (real CRM) mode, so the two are never confused while recording.

## Daily schedule (built last, made live)

- A scheduled entry (cron) on this Mac runs the daily run every morning at 07:00. There are no scheduled entries on this computer today.
- It only reads the website and CRM and prepares suggestions. It can never change the CRM; that still needs an approval in the app.
- Each run adds a line to a log file, so you can see it fired.
- Before going live I run the exact scheduled command by hand, then set it a few minutes ahead once to watch it fire by itself.
- Limits to know: the Mac must be awake at that time, and macOS may ask once for permission. The page in `docs/` shows how to check it and how to switch it off.

## Smoke testing (rule 2), in four stages

1. **Offline tests.** Automated tests run against saved copies of the website pages and the CRM backup. They check that the tool produces exactly the table above, including the billing rule and the "don't ask twice" rule. Nothing touches the real CRM.
2. **Rehearsal mode.** The review app runs against a *local copy* of the CRM built from the backup. Approve and reject as often as you like, and reset at any time. This is where you practise the demo.
3. **Dry run against the real CRM.** The tool prints the exact changes it *would* send, without sending them. You compare that list with the table above and sign off.
4. **First real changes, one at a time.** Before recording, you approve two low-risk items through the app: one edit (which can be reversed from the backup) and one account creation that is needed anyway (Batavia). This confirms the real CRM accepts our requests. Then the rest go ahead.

Every real change is logged with its before and after values, so any edit can be put back from the backup. Created accounts cannot be removed, which is why creations are rehearsed first.

## Demo video

- A roughly 2-minute recording, saved in `docs/demo/`.
- Items held back for the recording, so they are still pending when you record:
  - **Approve on camera:** Chagrin Falls rename (easy to see change in the CRM browser).
  - **Reject on camera:** Ashtabula address change (PO Box is valid for billing).
  - **Show evidence for:** Tiffin (billing rule) and Owosso (duplicate).
- You rehearse the full demo in rehearsal mode first. The real recording happens once, during the real review.

## Outside libraries needing your approval (rule 6)

| Library | Used for |
|---|---|
| `requests` | Talking to the website and the CRM |
| `beautifulsoup4` | Reading details out of web pages |
| `flask` | The local review app |
| `pytest` | Running the automated tests |
| Bootstrap 5 (styling files, not a Python package) | The clean layout of the review app. A copy is kept inside the project so the app works without internet during the demo. |
| Lora and Work Sans typefaces (Google Fonts) | Matching the clipboard.com look. Loaded from the internet, with standard typefaces as a fallback if offline. |

Everything else (the audit database, name comparison, scheduling) uses what ships with Python.

## Folder layout

```
clipboard-assessment/
  docs/                  00-rules, 01-plan, 02-scraping, 03-matching-explained,
                         04-review-app, 05-daily-schedule, writeup, demo/ (the recording)
  src/bellhaven_sync/    backup, scraper, CRM client, local CRM copy (rehearsal),
                         matcher, proposals, decisions store, apply, pipeline, review_app/
  tests/                 one test file per source file, plus saved sample pages
  data/backups/          the CRM backup
  data/runs/<date>/      per-run records: pages, communities, scores, suggestions
  data/audit.db          the audit trail database (reviews and CRM changes)
  data/decisions/        readable export of the audit trail
  logs/                  daily schedule log
  schedule/crontab.txt   the live schedule entry
  .env                   your API token (kept out of the code and out of GitHub)
  requirements.txt, README.md, .gitignore
```

The folder becomes a git repository linked to the GitHub repository above. `.venv` and `.env` are excluded.

## Order of work

Each numbered step ends with its `docs/` page updated and its own commit, so the history reads as the story of the exercise.

1. Set up git for this folder (Sadiyah's name and email) and save `docs/00-rules.md` and `docs/01-plan.md`.
2. **Back up the CRM** (all accounts and contacts) to `data/backups/`. Uses built-in Python only.
3. Install the approved libraries.
4. **Scraping:** build the scraper, with tests and its trace records.
5. **Matching:** build the CRM client, local CRM copy, scoring and grouping, with tests against the expected table, and write `docs/03-matching-explained.md` with the real scores.
6. Build the audit trail database and "don't ask twice" safety, with tests.
7. **Review app:** build the app (Bootstrap, clipboard.com styling), the apply step and the audit trail page, tested in rehearsal mode. Tests check that every CRM change has a matching review and correct before and after values.
8. Smoke stages 1 to 3, then you sign off on the dry-run list.
9. You rehearse the demo in rehearsal mode.
10. Smoke stage 4, then you review and approve for real, recording the demo.
11. Run the pipeline a second time to prove nothing is re-proposed, and check the CRM end state against the backup.
12. **Daily schedule (last):** install the live cron entry, prove it fires, and document it.
13. Draft `docs/writeup.md` and push to GitHub on your go-ahead.

## How we will know it worked

- All automated tests pass.
- The dry-run list matches the expected table.
- After the real review, a second pipeline run proposes nothing new.
- The live schedule fires by itself and writes its log line.
- Each step (scraping, matching, review, schedule) can be followed from its saved records and its commit alone.
- A final comparison of the CRM against the backup shows only the approved changes.
- Spot checks in the CRM browser: Tiffin's old account is unchanged apart from its pointer, the new Tiffin account sits under Bellhaven, and the duplicate copies are Inactive and point to the kept account.
