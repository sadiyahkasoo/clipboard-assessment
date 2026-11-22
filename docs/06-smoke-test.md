# Smoke testing: checking before anything real is changed

The CRM has no delete and no undo. So before any real change is sent, the tool is checked in four stages, each a step closer to the real thing.

| Stage | What it proves | Touches the real CRM? | Status |
|---|---|---|---|
| 1. Automated tests | The logic is right: scraping, matching, the billing rule, duplicates, the audit trail, safe re-runs | No | **Done: 86 tests pass** |
| 2. Rehearsal | The whole flow works end to end, including approving and rejecting in the app | No (local copy) | **Done**, and repeatable any time |
| 3. Dry run | The exact requests that *would* be sent to the real CRM are correct | Reads only | **Done and signed off** |
| 4. First real changes | The real CRM accepts our requests | Yes, two approved items | **Done:** one rename (Chagrin Falls) and one new account (Batavia) landed and were confirmed before the rest were approved |

## Stage 1: automated tests

    PYTHONPATH=src .venv/bin/python -m pytest

The tests run against saved copies of the website and the CRM backup, so they can never reach the real CRM. Among other things they check that:

- all 35 communities are found, including the one missing from the directory;
- the 29 expected suggestions are produced, no more and no fewer;
- an account with revenue and money owed is never re-parented, and only its pointer is set;
- nothing can be sent without an approval, and a rejected item is never sent;
- a half-finished change of ownership can be retried without creating a second account;
- reviews and CRM changes cannot be edited or deleted;
- after everything is decided, running again proposes nothing;
- after approving everything, each of the 35 communities has exactly one active account under Bellhaven.

## Stage 2: rehearsal

Start the review app; it opens in Rehearsal mode, working on a local copy of the CRM built from the backup:

    PYTHONPATH=src .venv/bin/python -m bellhaven_sync.review_app

The **Smoke test** page in Rehearsal mode brings the three safe stages together: a button to run the automated tests, the rehearsal with its Reset button, and the dry-run list.

What was rehearsed, through the app's own Approve and Reject buttons:

| Action | Result on the local copy |
|---|---|
| Approved the Chagrin Falls rename | "Riverbend Manor Care Center" became "Bellhaven of Chagrin Falls" |
| Rejected the Ashtabula address change | Nothing sent; the PO Box is unchanged |
| Approved the Tiffin change of ownership | New account created under Bellhaven. The old account kept its owner (Cedar Trail), revenue (84,000) and amount owed (12,400); only its pointer was set. |
| Approved the Owosso duplicate | Extra copy marked Inactive and pointed at the kept account |
| Approved the Batavia creation | New account created under Bellhaven |
| Tried to approve Batavia a second time | Refused: already decided |
| Ran the pipeline again | 0 new suggestions; the rejected one was not raised again |

The **Reset rehearsal** button on the Smoke test page wipes the rehearsal and starts fresh, so this can be repeated as often as needed.

## Stage 3: dry run against the real CRM

    PYTHONPATH=src .venv/bin/python -m bellhaven_sync.pipeline --mode live --print-plan

This reads the real website and the real CRM and writes out every request it would send, without sending any. The same list is shown on the Smoke test page in the app ("Refresh dry run" does the same read-only job). The full list is saved at:

    data/runs/20261121T204606Z/04_proposals/planned_requests.md

Result: **29 suggestions, 31 requests** (the two change-of-ownership suggestions send two requests each). After the dry run the real CRM was compared with the backup and was **identical**: 121 accounts, nothing changed.

**Signed off.** The 29 suggestions:

| Kind | Count | Communities |
|---|---|---|
| Update details | 8 | Grove City, Sycamore Ridge, Arbors Dayton, Ashland (small name differences); Chagrin Falls, Willow Creek, Chesterton (old names); Portsmouth (zip typo) |
| Address differs | 1 | Ashtabula (PO Box in CRM) |
| Move under Bellhaven | 4 | Findlay, Lima, Zanesville (also renamed), Kettering (also renamed) |
| Change of ownership (billing rule) | 2 | Tiffin, Marietta |
| Create new account | 4 | Batavia, Carlisle, Amberly Manor, Union Square |
| Mark duplicate | 7 | Port Clinton, Erie, Owosso (1 each); Monroe (2); Kettering (2) |
| No longer on website | 2 | Alliance, Coldwater |
| Sold to another owner | 1 | Sandusky |

## Stage 4: first real changes (done)

One thing could not be learned without a real request: the CRM's documentation does not say which fields it requires when creating an account. So the first two approvals in **Production** were made one at a time and checked before anything else was approved:

1. **One edit:** "Update details: Bellhaven of Chagrin Falls" (a one-field rename, which could be put back from the backup if needed).
2. **One creation:** "Create account: Bellhaven of Batavia" (needed anyway, and has no lookalikes).

Both showed "confirmed by read-back" and were checked directly against the CRM, which proved the real CRM accepts our requests. The remaining items were then approved. All 30 requests succeeded; the results are in [writeup.md](writeup.md).

