# Step: matching website communities to CRM accounts

## The question being answered

For each community on the website: **which CRM account, if any, is this same facility?**

Names cannot answer this alone. Facilities are renamed when they are bought ("Sunny Acres Retirement Home" is now "Bellhaven Willow Creek"), and different facilities can share a name ("Amberly Manor" exists in Ohio and in Colorado). So the tool weighs several pieces of evidence together and gives each pair a score out of 100.

## Tidying before comparing

People write the same thing in different ways. Before comparing, both sides are reduced to one standard spelling, so these are treated as identical:

| Written one way | Written another way |
|---|---|
| 210 Orchard **Ln** | 210 Orchard **Lane** |
| 4850 **NW** Sylvania **Ave** | 4850 **Northwest** Sylvania **Avenue** |
| 199 Barks **Rd W** | 199 Barks **Road West** |
| Bellhaven **Rehab and** Nursing | Bellhaven **Rehabilitation &** Nursing |
| **Health Care Center** | **Healthcare Centre** |

In names, words that carry no information here are ignored: "the", "of", "at", "and", and "Bellhaven" itself (it is in nearly every name, so it cannot tell two facilities apart). Word order is ignored too.

This tidying is only used for comparing. It never changes what is stored.

## The score: six pieces of evidence

A community is only compared with accounts **in the same state**. A different state scores zero outright, because a building cannot move states.

| Evidence | Points | Why it gets this weight |
|---|---|---|
| Same street address | 40 | The strongest clue. Owners and names change; the building stays put. |
| Street nearly the same (small typo) | 25 instead of 40 | Probably the same street, but not certain |
| Same zip code | 15 | Confirms the place |
| Zip differs only by two swapped digits | 8 instead of 15 | A typing slip (45626 for 45662), not a different town |
| Same city | 10 | Supports the address |
| Similar name | 0 to 20 | Scaled by how alike the tidied names are. Helpful, but names change on rebrand, so it is capped well below the address. |
| Same phone number | 10 | Good confirmation when present, but numbers often differ |
| The website's administrator is a contact on the CRM account | 5 | A small independent confirmation |
| **Maximum** | **100** | |

The address evidence (street, zip, city) adds up to 65 of the 100 points. That is deliberate: this problem is about buildings changing hands, and the address is the one thing that survives a sale.

## The cut-offs

| Score | Band | What the tool does |
|---|---|---|
| 65 to 100 | **Match**: same facility | Treats it as the community's account. If several accounts reach this score for one community, they are duplicates of each other. |
| 50 to 64 | **Probable**: likely the same | Treats it as the account, but marks any suggestion as low confidence so a person decides |
| 30 to 49 | **Lookalike** | Shown to the reviewer as evidence. The account is never changed. |
| 0 to 29 | **Unrelated** | Ignored |

### Why 65

Street + zip + city = 40 + 15 + 10 = **65**. So the rule in words is: *an account at exactly the same address is the same facility, whatever it is called.* Nothing else is needed to reach 65, and nothing short of an address match can reach it (everything else together adds up to only 60).

This is what catches renamed facilities. "Sunny Acres Retirement Home" shares almost nothing in its name with "Bellhaven Willow Creek", yet scores 71 because it is the same building.

### Why 50 and 30

These two were set by looking at how the real scores fall. All 35 communities were scored against every account in the same state: 1,501 pairs in total.

| Score range | Pairs | What they are |
|---|---|---|
| 65 to 100 | 37 | Every one is a genuine match. The lowest is 71. |
| 50 to 64 | 1 | Ashtabula, at 60. Name, zip, city, phone and administrator all agree, but the CRM holds a PO Box where the website shows a street address. |
| 30 to 49 | 2 | "Union Square Senior Living" (38) and "Maplewood Senior Care Center" (35). Same town and a similar name, but a different street, phone, administrator and owner. |
| 20 to 29 | 0 | |
| 0 to 19 | 1,461 | Unrelated accounts that happen to share a state |

The scores form separate clumps with wide empty gaps between them: nothing between 39 and 59, and nothing between 20 and 34. Each cut-off sits inside a gap:

- **50** separates "everything agrees except one field" (60) from "same town, different building" (38).
- **30** separates accounts worth showing a reviewer (35, 38) from background noise (under 20).

No pair sits within 5 points of any cut-off, so the result would be the same if the cut-offs were moved a few points either way.

### An honest limit

These cut-offs are fitted to one data set of 35 communities and 121 accounts. They are a sensible starting point, not a proven law. Two protections are built in:

1. Every run saves every score with its six-part breakdown (`03_matching/scores.csv`), so a pair that lands near a cut-off in future is visible, not hidden.
2. An automated test fails if any pair ever falls inside the gaps around the cut-offs in the reference data, which would be the signal to revisit them.

## From scores to groups

After scoring, an account "belongs" to at most one community: the one it scores highest against. Then each community lands in one group:

| What was found | Group | What is proposed |
|---|---|---|
| One match, already under Bellhaven, details agree | Confident match | Nothing |
| One match, but the name, zip or street differs | Needs a fix | Update the details |
| A match under a different owner (or no owner) | Needs a fix | Move it under Bellhaven. **The billing rule decides how** (see below). |
| Several matches | Duplicates | Keep one; mark the others Inactive and point them at the kept one |
| Nothing scores 50 or more | No CRM account | Create an account. Lookalikes are shown but left alone. |

Then the tool looks the other way: any account under Bellhaven that **no** community claimed is "no longer on the website".

### Choosing which duplicate to keep

When several accounts are the same facility, the tool keeps one, in this order of preference:

1. the one already under Bellhaven;
2. otherwise the one with billing history;
3. otherwise the one with the most contacts;
4. otherwise one that has an owner over one that has none;
5. otherwise the highest score;
6. and finally the lowest account id, purely so the choice is the same on every run.

For most duplicate sets rule 1 settles it. **Kettering is the exception**: three accounts share the address and none is under Bellhaven, none has billing history and none has contacts. Rules 4 and 5 choose "Kettering Care Centre". This is the least certain decision in the whole exercise, so those proposals are marked medium confidence and the reviewer sees all three accounts side by side.

### The billing rule

Before an account is moved to a different owner, the tool checks its billing figures:

- **Revenue history AND money still owed:** the account is not moved. A new account is created under Bellhaven and the old one's "CHOW pointer" is set to the new account. Nothing else on the old account is touched.
- **No revenue history, or nothing owed:** the existing account is moved directly.

In this data: Tiffin (owes 12,400) and Marietta (owes 3,800) get new accounts. Lima has revenue history but owes nothing, so it is moved directly, as are Zanesville, Kettering and Findlay.

### Accounts no longer on the website

- **Sandusky** has no community on the website, but another owner (Millstone Health Partners) has an account at the same address. It looks sold. Sandusky owes 5,200, so under the billing rule it is left as it is and pointed at the Millstone account.
- **Alliance** and **Coldwater** have no community and no other account at their address. The tool cannot tell whether they were sold or closed, so it proposes marking them "Needs Review" with a note, and does not guess.

### What the tool deliberately does not change

- **Phone numbers.** Many differ between the website and the CRM, but the CRM number may be a billing line. Phones are used as evidence only.
- **Addresses that differ only in spelling.** "Ln" and "Lane" are the same; no change is proposed.
- **Lookalike accounts.** They are shown as evidence and never touched.
- **Revenue and amounts owed.** The code refuses to send these fields at all.

## The real scores

Every community with every account that scored 30 or more against it, from the first run. The full list of all 1,501 pairs is in `data/runs/<date>/03_matching/scores.csv`.

| Community | Best CRM account | Owner in CRM | Score | Band | Street | Zip | City | Name | Phone | Admin |
|---|---|---|---|---|---|---|---|---|---|---|
| Bellhaven of Maplewood | Bellhaven of Maplewood | Bellhaven Senior Living | 100 | match | 40 | 15 | 10 | 20 | 10 | 5 |
| Bellhaven of Maplewood | Maplewood Senior Care Center | Stonebridge Eldercare | 35 | lookalike | 0 | 15 | 10 | 10 | 0 | 0 |
| Bellhaven of New Carlisle | Bellhaven of New Carlisle | Bellhaven Senior Living | 100 | match | 40 | 15 | 10 | 20 | 10 | 5 |
| Bellhaven Terrace of Akron | Bellhaven Terrace of Akron | Bellhaven Senior Living | 100 | match | 40 | 15 | 10 | 20 | 10 | 5 |
| Bellhaven Woods of Toledo | Bellhaven Woods of Toledo | Bellhaven Senior Living | 100 | match | 40 | 15 | 10 | 20 | 10 | 5 |
| Bellhaven of Kalamazoo | Bellhaven of Kalamazoo | Bellhaven Senior Living | 100 | match | 40 | 15 | 10 | 20 | 10 | 5 |
| Bellhaven Court of Altoona | Bellhaven Court of Altoona | Bellhaven Senior Living | 100 | match | 40 | 15 | 10 | 20 | 10 | 5 |
| Bellhaven of Owosso | Bellhaven of Owosso | Bellhaven Senior Living | 100 | match | 40 | 15 | 10 | 20 | 10 | 5 |
| Bellhaven of Owosso | Bellhaven of Owosso | Bellhaven Senior Living | 85 | match | 40 | 15 | 10 | 20 | 0 | 0 |
| Bellhaven of Wooster | Bellhaven of Wooster | Bellhaven Senior Living | 95 | match | 40 | 15 | 10 | 20 | 10 | 0 |
| Bellhaven of Saline | Bellhaven of Saline | Bellhaven Senior Living | 95 | match | 40 | 15 | 10 | 20 | 10 | 0 |
| Bellhaven of Meadville | Bellhaven of Meadville | Bellhaven Senior Living | 95 | match | 40 | 15 | 10 | 20 | 10 | 0 |
| Bellhaven Rehabilitation & Nursing of Grove City | Bellhaven Rehab and Nursing of Grove City | Bellhaven Senior Living | 95 | match | 40 | 15 | 10 | 20 | 10 | 0 |
| Bellhaven of Portsmouth | Bellhaven of Portsmouth | Bellhaven Senior Living | 93 | match | 40 | 8 | 10 | 20 | 10 | 5 |
| Bellhaven of Chesterton | Chesterton Senior Commons | Bellhaven Senior Living | 91 | match | 40 | 15 | 10 | 11 | 10 | 5 |
| Bellhaven Meadows of Findlay | Bellhaven Meadows of Findlay | none | 90 | match | 40 | 15 | 10 | 20 | 0 | 5 |
| Bellhaven of Goshen | Bellhaven of Goshen | Bellhaven Senior Living | 90 | match | 40 | 15 | 10 | 20 | 0 | 5 |
| Bellhaven of Defiance | Bellhaven of Defiance | Bellhaven Senior Living | 90 | match | 40 | 15 | 10 | 20 | 0 | 5 |
| Bellhaven of Marion | Bellhaven of Marion | Bellhaven Senior Living | 90 | match | 40 | 15 | 10 | 20 | 0 | 5 |
| The Arbors at Bellhaven - Dayton | Arbors at Bellhaven Dayton | Bellhaven Senior Living | 90 | match | 40 | 15 | 10 | 20 | 0 | 5 |
| Bellhaven Healthcare Centre of Ashland | Bellhaven Health Care Center of Ashland | Bellhaven Senior Living | 90 | match | 40 | 15 | 10 | 20 | 0 | 5 |
| Bellhaven of Port Clinton | Bellhaven of Port Clinton | Bellhaven Senior Living | 90 | match | 40 | 15 | 10 | 20 | 0 | 5 |
| Bellhaven of Port Clinton | Harborview Nursing & Rehab of Port Clinton | Harborview Care Group | 73 | match | 40 | 15 | 10 | 8 | 0 | 0 |
| Bellhaven Shores of Erie | Bellhaven Shores of Erie | Bellhaven Senior Living | 90 | match | 40 | 15 | 10 | 20 | 0 | 5 |
| Bellhaven Shores of Erie | Harborview Shores of Erie | Harborview Care Group | 78 | match | 40 | 15 | 10 | 13 | 0 | 0 |
| Bellhaven at Sycamore Ridge | Bellhaven of Sycamore Ridge | Bellhaven Senior Living | 85 | match | 40 | 15 | 10 | 20 | 0 | 0 |
| Bellhaven Gardens of Monroe | Bellhaven Gardens of Monroe | Bellhaven Senior Living | 85 | match | 40 | 15 | 10 | 20 | 0 | 0 |
| Bellhaven Gardens of Monroe | Monroe Gardens Care Center | Harborview Care Group | 79 | match | 40 | 15 | 10 | 14 | 0 | 0 |
| Bellhaven Gardens of Monroe | Cedar Trail of Monroe | Cedar Trail Communities | 76 | match | 40 | 15 | 10 | 11 | 0 | 0 |
| Bellhaven of Tiffin | Bellhaven of Tiffin | Cedar Trail Communities | 85 | match | 40 | 15 | 10 | 20 | 0 | 0 |
| Bellhaven of Marietta | Bellhaven of Marietta | Cedar Trail Communities | 85 | match | 40 | 15 | 10 | 20 | 0 | 0 |
| Bellhaven Crossings of Lima | Bellhaven Crossings of Lima | Harborview Care Group | 85 | match | 40 | 15 | 10 | 20 | 0 | 0 |
| Bellhaven of Zanesville | Cedar Trail of Zanesville | Cedar Trail Communities | 82 | match | 40 | 15 | 10 | 12 | 0 | 5 |
| Bellhaven of Kettering | Kettering Care Centre | Harborview Care Group | 77 | match | 40 | 15 | 10 | 12 | 0 | 0 |
| Bellhaven of Kettering | Kettering Senior Campus | Cedar Trail Communities | 76 | match | 40 | 15 | 10 | 11 | 0 | 0 |
| Bellhaven of Kettering | Kettering Nursing & Rehabilitation | none | 74 | match | 40 | 15 | 10 | 9 | 0 | 0 |
| Bellhaven of Chagrin Falls | Riverbend Manor Care Center | Bellhaven Senior Living | 75 | match | 40 | 15 | 10 | 5 | 0 | 5 |
| Bellhaven Willow Creek | Sunny Acres Retirement Home | Bellhaven Senior Living | 71 | match | 40 | 15 | 10 | 6 | 0 | 0 |
| Bellhaven of Ashtabula | Bellhaven of Ashtabula | Bellhaven Senior Living | 60 | probable | 0 | 15 | 10 | 20 | 10 | 5 |
| Bellhaven at Union Square | Union Square Senior Living | Juniper Point Healthcare | 38 | lookalike | 0 | 15 | 10 | 13 | 0 | 0 |
| Bellhaven of Batavia | (nothing scores 30 or more) | | | unrelated | | | | | | |
| Bellhaven of Carlisle | (nothing scores 30 or more) | | | unrelated | | | | | | |
| Amberly Manor | (nothing scores 30 or more) | | | unrelated | | | | | | |
## What is saved, so the step can be re-traced

In `data/runs/<date and time>/03_matching/`:

| File | What it holds |
|---|---|
| `scores.csv` | Every pair in the same state: total, band, and points for each of the six pieces of evidence |
| `communities.json` | For each community: its group, the reason in a sentence, and the accounts considered |
| `off_website.json` | Bellhaven accounts no community claimed, and why |

## Where the code is

- `src/bellhaven_sync/normalize.py` (tidying), `matcher.py` (scoring), `classify.py` (groups and proposals)
- The weights and cut-offs are named settings at the top of `src/bellhaven_sync/config.py`
- Tests: `tests/test_normalize.py`, `tests/test_matcher.py`, `tests/test_classify.py`
