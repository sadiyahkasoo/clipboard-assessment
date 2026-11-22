# Write-up: Bellhaven ownership sync

## What I built

I built a small system that keeps the CRM's facility-to-parent links in line with the Bellhaven Senior Living website. It has four parts:

1. **A scraper** that reads every community from the website.
2. **Matching** that scores each community against the CRM accounts and decides what kind of case it is.
3. **A review app** where I see each proposed change with its evidence and approve or reject it. Nothing is written to the CRM without my approval.
4. **A daily schedule** that is safe to run again and again. Once I've decided something, it doesn't ask me twice.

Every part has its own plain-language page in `docs/`, and every run saves its working files, so any decision can be traced back to the evidence behind it.

## How I approached it

This was a different type of exercise for me, so I leaned on the habits I trust.

**I always start with a backup.** I do this with any data, and especially with data that can't be deleted (and it never should be). Before anything else I saved a full copy of all 121 accounts and 67 contacts from the API. That gave me a fixed reference to compare against at the end, and a way to put any edit back.

**I smoke test before I touch anything real.** Even in a sandbox, I didn't want to create or change records I couldn't undo. So I worked in stages:

1. Automated tests against saved copies of the website and the backup.
2. A full rehearsal in the review app against a local copy of the CRM, including approving and rejecting.
3. A dry run against the real CRM that listed every request it would send, without sending any.
4. Only then the real changes, starting with one rename and one new account to confirm the CRM accepted them.

**I kept the build simple.** It's Python with Flask, because Flask is lightweight and LLMs know Python very well. The audit trail is a local SQLite database, which ships with Python. I'm not a designer, so I asked Claude to build the review app to look like your main website.

## How I used AI tools

I used Claude Code to write the code, the tests and the first drafts of the docs. My part was to direct it and check it.

- **I set the rules before any code was written:** backup first, smoke test before any real change, plans in plain language, every outside library approved by me, every step traceable, and an audit trail of everything the review app changes.
- **I approved the plan before the build started**, and sent it back twice to add things I wanted.
- **I checked the output against the real data**: the dry-run list of requests before anything was sent, and the CRM against my backup afterwards.
- **Every approve and reject decision was mine**, made one at a time in the review app.

## Scraping

The directory lists 34 communities, but the home page says there are 35. The missing one, Bellhaven Meadows of Findlay, is only linked from a notice on the home page. So the scraper picks up community links from every page it visits, not just the directory.

I also noticed that asking the directory for a page past the end doesn't give an error; it quietly returns the last page again. So the scraper follows the site's own "Next" links and keeps track of where it has been, and never counts page numbers.

One safety check: if a run finds fewer than 80% of the communities the last good run found, it stops. If the website is down, I don't want the tool telling me every account has left Bellhaven.

## Matching

I didn't want to rely on names. Facilities get renamed when they are sold, and different facilities share names. The one thing that doesn't change in a sale is the building, so I built the score mostly around the address.

Each community is compared with the accounts in the same state and scored out of 100:

| Evidence | Points |
|---|---|
| Same street | 40 |
| Same zip (8 if two digits are swapped) | 15 |
| Same city | 10 |
| Similar name | 0 to 20 |
| Same phone | 10 |
| Website administrator is a CRM contact | 5 |

Before comparing, spelling habits are tidied away, so "Ln" and "Lane", "Rehab" and "Rehabilitation", and "Centre" and "Center" count as the same.

**How I chose the cut-offs.** 65 or more is a match. 50 to 64 is a probable match that I have to confirm. 30 to 49 is a lookalike, shown as evidence but never changed.

- **65** is exactly street + zip + city. My rule is that an account at the same address is the same facility, whatever it is called. That is how "Sunny Acres Retirement Home" was found to be Bellhaven Willow Creek.
- **50 and 30** came from looking at the real scores. Of 1,501 same-state pairs, 37 score 65 or more (all genuine, the lowest is 71), one scores 60, two score 35 and 38, and everything else is under 20. I put the cut-offs in the empty gaps, and no pair sits within 5 points of one.

I want to be honest about the limit here: these cut-offs fit one small data set. Every run saves every score with its breakdown, so a borderline pair would show up, and a test fails if a pair ever lands near a cut-off in the reference data.

The full detail, with the real scores, is in `docs/03-matching-explained.md`.

## What the tool found

There are 35 communities on the website, and 16 were already correct in the CRM. The rest came to 29 proposals:

| Finding | Count | Examples |
|---|---|---|
| Name, zip or old name to update | 8 | "Riverbend Manor Care Center" is Bellhaven of Chagrin Falls; Portsmouth zip 45626 should be 45662 |
| Address differs | 1 | Ashtabula: PO Box in the CRM |
| Wrong owner, moved directly | 4 | Lima, Zanesville, Kettering, Findlay |
| Wrong owner, billing rule applies | 2 | Tiffin, Marietta |
| No CRM account | 4 | Batavia, Carlisle, Amberly Manor, Union Square |
| Duplicates | 7 | Port Clinton, Erie, Owosso, Monroe (2), Kettering (2) |
| Under Bellhaven but not on the website | 2 | Alliance, Coldwater |
| Sold to another owner | 1 | Sandusky |

## The billing rule (CHOW)

I followed the SOP exactly. Before any change of owner, the tool checks `lifetime_revenue` and `outstanding_ar`.

- **Tiffin** (revenue 84,000, owes 12,400) and **Marietta** (revenue 51,250, owes 3,800) have both, so I did not move them. The old account stays exactly as it is, a new account is created under Bellhaven, and `chow_current_account` on the old account points to the new one. Nothing else on the old account is touched, and a test checks that.
- **Lima** has revenue (47,000) but owes nothing, so the SOP allows a direct move. Zanesville, Kettering and Findlay owe nothing either and were moved directly.

Once an account has been handled this way, the old account is treated as history and is no longer matched. Otherwise the next daily run would see the old and new accounts at the same address and call them duplicates.

## Judgement calls

These are the places where I had to decide, and what I decided.

- **Lookalikes: left alone.** "Union Square Senior Living" (New Albany) and "Maplewood Senior Care Center" share a town and part of a name with a Bellhaven community, but the street, phone, administrator and owner are all different. The "Amberly Manor" in the CRM is in Colorado; Bellhaven's is in Hudson, Ohio. I treated these as different facilities and created new accounts where one was needed.
- **Kettering: my least certain call.** There are three accounts at the same address and none is under Bellhaven. Nothing marks one as the right survivor, since none has billing history or contacts. A fixed tie-break rule chose "Kettering Care Centre". I marked it medium confidence, and it is the first thing I would check with someone who knows the accounts.
- **Owosso:** two identical accounts under Bellhaven. I kept the one whose phone number and contacts match the website.
- **Sandusky:** under Bellhaven in the CRM, not on the website, and "Millstone Care of Sandusky" sits at the same address under another owner. I read that as a sale. Sandusky still owes 5,200, so I left the account as it is and pointed its `chow_current_account` at the Millstone account.
- **Alliance and Coldwater:** under Bellhaven but not on the website, with no other account at their address. I couldn't tell whether they were sold or closed, so I set them to "Needs Review" with a note. I would rather flag them than guess.
- **Ashtabula: rejected.** The CRM has a PO Box where the website shows a street address. The field is a billing address and a PO Box is a valid one, so I rejected the change.
- **Phone numbers: evidence only.** They often differ between the website and the CRM, and the CRM number may well be a billing line. I never proposed changing a phone number.
- **Duplicates** follow the brief: `duplicate_of_account` set to the survivor's id, status `Inactive`, and a note saying which account it duplicates. I left the duplicate's owner as it was.

## The review app and audit trail

Each proposal page shows me why it is proposed, a "now" and "will become" table of exactly what would be written, the website and CRM accounts side by side, the score breakdown, the billing figures and the billing rule check.

The app has two modes, switched at the top of the page. **Rehearsal** works on a local copy of the CRM and has a Smoke test page (the automated tests, the rehearsal, and the dry-run list of requests). **Production** works on the real CRM. The two share nothing, and the mode is part of every page address, so a rehearsal page can never act on production.

When I approve, the app re-reads the account to make sure it hasn't changed since the proposal was made, sends the change, reads it back to confirm it landed, and records all of it.

The audit trail is the part I care about most. It has four tables: runs, proposals, reviews and CRM changes. Reviews and CRM changes can only be added, never edited or removed, and the database enforces that. Every CRM change has to point to the approval behind it. A readable CSV copy is written after each decision.

## Running daily, safely

A cron job runs the check every morning at 07:00. It only reads the website and the CRM and fills the review queue; it cannot write to the CRM.

Each proposal has a fingerprint made from what it would change. On a re-run, a proposal I've already decided is not raised again, a pending one is refreshed in place, and one that no longer applies is withdrawn. Approved changes also stop appearing by themselves, because once the CRM is corrected there is nothing left to find.

Two-step changes (create a new account, then point the old one at it) record their progress, so a retry after a failure reuses the account already created and never makes a second one.

## Testing

86 automated tests run offline against saved copies of the website and the CRM backup. They cover the scraper, the matching cut-offs, every finding in the table above, the billing rule, the add-only audit trail, safe re-runs, and the end state after approving everything (each of the 35 communities has exactly one active account under Bellhaven).

## Result

I did the review in Production on 22 November 2026.

- **Decisions:** I approved 28 of the 29 proposals and rejected 1 (Ashtabula, because a PO Box is a valid billing address).
- **Requests sent:** 30, all confirmed by reading the account back: 24 updates and 6 new accounts. None failed.
- **CRM before and after:** 121 accounts before, 127 after. The 6 new accounts are Batavia, Carlisle, Amberly Manor, Union Square, and the new Tiffin and Marietta accounts. 24 existing accounts changed.
- **Checked against the backup:** every difference between the CRM and my original backup traces to an approved change in the audit trail, and every change in the audit trail is present in the CRM. Nothing else moved.
- **End state:** each of the 35 website communities has exactly one active account under Bellhaven. 34 match the website exactly; Ashtabula keeps its PO Box by my decision.
- **Duplicates:** 7 accounts are Inactive and point to the surviving account.
- **Changes of ownership:** 3 accounts carry a `chow_current_account` pointer (Tiffin, Marietta, Sandusky). Their owner, name, status and billing figures are unchanged from the backup.
- **Needs Review:** Alliance and Coldwater.
- **Re-run:** a run after the review proposed 0 new items. The one remaining difference (Ashtabula) was recognised as already decided and not raised again.

## What I would do next

- **Run it on a server**, not a laptop, with the audit database somewhere shared. A sleeping laptop skips its run.
- **Check the uncertain cases with someone who knows the accounts**: the Kettering survivor, and what happened to Alliance and Coldwater.
- **Move contacts** from the retired duplicates to the surviving account. I left contacts untouched in this exercise.
- **Re-check the cut-offs on more data.** They fit this data set cleanly, but one operator is a small sample.
- **Add reviewer sign-in** to the app so the audit trail records a verified person, and notify someone when the daily run finds something new.

This was a different approach for me, but I enjoyed it, and I'm looking forward to hearing back.
