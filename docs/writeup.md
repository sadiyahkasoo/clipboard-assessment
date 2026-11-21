# Write-up: Bellhaven ownership sync

> **Draft.** The sections marked "to complete after the review" depend on the real review and should be filled in once it is done. Edit the wording so it reads in your own voice.

## What I built

A small system that keeps the CRM's facility-to-parent links in step with the Bellhaven Senior Living website.

1. **A scraper** that reads every community from the website.
2. **Matching logic** that scores each community against CRM accounts and classifies it.
3. **A review app** that shows each proposed change with its evidence. Nothing is written to the CRM without an approval.
4. **A daily schedule** that is safe to re-run: anything already decided is never proposed again.

Each part has its own plain-language page in `docs/`, and each run leaves trace files so any decision can be followed back to the evidence.

## How I approached it

**Backup first.** Before anything else I saved a full copy of all 121 accounts and 67 contacts. The CRM has no delete, so I wanted a fixed reference to compare against and restore edits from.

**Rehearse before writing.** I built a local stand-in for the CRM that behaves like the real one. The whole flow, including approving and rejecting in the app, was rehearsed against a copy of the backup. Then I ran a dry run against the real CRM that listed every request it would send without sending any. Only after that did real changes begin, starting with one edit and one creation to confirm the CRM accepted the requests.

## Scraping

The directory lists 34 communities, but the home page says 35. The 35th, Bellhaven Meadows of Findlay, is linked only from a notice on the home page. So the scraper collects community links from every page it visits, not only the directory.

Asking the directory for a page past the end returns the last page again instead of an error. So the scraper follows the site's own "Next" links and tracks visited pages, and never counts page numbers.

If a run finds under 80% of the communities the last good run found, it stops. A website outage should not make the tool flag every account as having left Bellhaven.

## Matching

Names are unreliable for this problem: facilities are renamed when sold, and different facilities share names. The one thing that survives a sale is the building. So the score is built mostly on the address.

Each community is compared with accounts in the same state and scored out of 100:

| Evidence | Points |
|---|---|
| Same street | 40 |
| Same zip (8 if two digits are swapped) | 15 |
| Same city | 10 |
| Similar name | 0 to 20 |
| Same phone | 10 |
| Website administrator is a CRM contact | 5 |

Before comparing, spelling habits are tidied away ("Ln" and "Lane", "Rehab" and "Rehabilitation", "Centre" and "Center").

**Cut-offs.** 65 or more is a match; 50 to 64 is a probable match that a person must confirm; 30 to 49 is a lookalike shown as evidence only.

- **65** is exactly street + zip + city. The rule is: an account at the same address is the same facility, whatever it is called. That is what finds "Sunny Acres Retirement Home" as Bellhaven Willow Creek.
- **50 and 30** were placed by looking at the real scores. Of 1,501 same-state pairs, 37 score 65 or more (all genuine, lowest 71), one scores 60, two score 35 and 38, and the rest score under 20. The cut-offs sit in the empty gaps, and no pair is within 5 points of one.

The limit of this: the cut-offs are fitted to one small data set. Every run saves every score with its breakdown so a borderline pair would be visible, and a test fails if a pair ever lands near a cut-off in the reference data.

Full detail, with the real scores, is in `docs/03-matching-explained.md`.

## What the tool found

35 communities on the website; 16 were already correct. The other findings produced 29 proposals:

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

Before any owner change the tool checks `lifetime_revenue` and `outstanding_ar`.

- **Tiffin** (revenue 84,000, owes 12,400) and **Marietta** (revenue 51,250, owes 3,800): the old account is left exactly as it is. A new account is created under Bellhaven and `chow_current_account` on the old account is set to the new one. No other field on the old account is touched, and a test checks that.
- **Lima** has revenue (47,000) but owes nothing, so the rule allows a direct move. Zanesville, Kettering and Findlay have no amount owed either and are moved directly.

After a change of ownership, the preserved old account is treated as history and is no longer matched. Otherwise the next run would see the old and new accounts at the same address and call them duplicates.

## Judgement calls

- **Lookalikes are left alone.** "Union Square Senior Living" (New Albany) and "Maplewood Senior Care Center" share a town and part of a name with a Bellhaven community, but have a different street, phone, administrator and owner. "Amberly Manor" in the CRM is in Colorado; the Bellhaven one is in Hudson, Ohio. I treated these as different facilities and created new accounts where needed.
- **Kettering** has three accounts at the same address and none under Bellhaven. Nothing clearly marks one as the right survivor: none has billing history or contacts. A fixed tie-break rule chose "Kettering Care Centre". I marked these as medium confidence because this is the least certain decision.
- **Owosso** has two identical accounts under Bellhaven. I kept the one whose phone number and contacts match the website.
- **Sandusky** is under Bellhaven in the CRM, is not on the website, and "Millstone Care of Sandusky" exists at the same address under another owner. I read that as a sale. Because Sandusky owes 5,200, I left the account as it is and set its `chow_current_account` to the Millstone account.
- **Alliance and Coldwater** are under Bellhaven but not on the website, with no other account at their address. I could not tell whether they were sold or closed, so I set them to "Needs Review" with a note instead of guessing at Inactive or changing their owner.
- **Ashtabula** has a PO Box in the CRM where the website shows a street address. The field is a billing address and a PO Box is valid for billing, so I rejected that proposal. *(Confirm this is what you decided.)*
- **Phone numbers** often differ between the website and the CRM. The CRM number may be a billing line, so I used phones as evidence only and never proposed changing them.
- **Duplicates** follow the convention in the brief: `duplicate_of_account` set to the survivor's id, status `Inactive`, plus a note saying which account it duplicates. The duplicate's owner is left as it was.

## The review app and audit trail

Each proposal page shows why it is proposed, a "now" and "will become" table of exactly what would be written, the website and CRM accounts side by side, the score breakdown, the billing figures and the billing rule check.

The app has two modes, switched from the top of the page. **Rehearsal** works on a local copy of the CRM and includes a Smoke test page (automated tests, the rehearsal itself, and the dry-run list of requests). **Production** works on the real CRM. The two share nothing, and the mode is part of every page address, so a rehearsal page can never act on production.

On approval the app re-reads the account to make sure it has not changed since the proposal was made, sends the change, reads it back to confirm, and records everything.

The audit trail is a local SQLite database with four tables: runs, proposals, reviews and CRM changes. Reviews and CRM changes are append-only, enforced by database triggers. Every CRM change must reference an approving review. A readable CSV export is written after each decision.

## Running daily, safely

A cron entry runs the read-only job each morning. Each proposal has a fingerprint made from what it would change. On a re-run, a fingerprint that already has a decision is not raised again; a pending one is refreshed in place; and one that no longer applies is withdrawn. Approved changes also stop appearing naturally, because once the CRM is corrected there is no difference left to find.

Two-step changes (create a new account, then point the old one at it) record their progress, so a retry after a failure reuses the account already created.

## Testing

86 automated tests run offline against saved copies of the website and the CRM backup. They cover the scraper, the matching cut-offs, every finding in the table above, the billing rule, the append-only audit trail, safe re-runs, and the end state after approving everything (each of the 35 communities has exactly one active account under Bellhaven).

## Result *(to complete after the review)*

- Proposals approved: __ of 29. Rejected: __ (which, and why).
- A second pipeline run after the review proposed __ new items.
- Final check of the CRM against the backup showed only the approved changes.

## What I would do next

- **Run it on a server**, not a laptop, with the audit database somewhere shared. A sleeping laptop skips its run.
- **Confirm the uncertain cases with a person who knows the accounts**: the Kettering survivor, and what happened to Alliance and Coldwater.
- **Move contacts** from retired duplicates to the surviving account. I left contacts untouched in this exercise.
- **Re-check the cut-offs on more data.** They fit this data set cleanly, but one operator is a small sample.
- **Add reviewer sign-in** to the app so the audit trail records a verified person, and notify someone when the daily run finds something new.
