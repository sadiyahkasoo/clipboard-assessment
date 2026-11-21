# Step: the review app and its audit trail

## What this step does

The review app is a small website that runs only on your own computer. It shows each suggested CRM change with its evidence, and a person approves or rejects it.

**An approval is the only way a change reaches the CRM.** The daily job cannot write to the CRM, and neither can any other part of the tool.

## Starting it

From the project folder:

    PYTHONPATH=src .venv/bin/python -m bellhaven_sync.review_app

Then open http://127.0.0.1:5001 in a browser. To stop the app, press Ctrl+C in the terminal.

## Two modes, one app

The app has two modes. Switch between them with the **Rehearsal | Production** control at the top of every page.

| | Rehearsal | Production |
|---|---|---|
| Works on | A local copy of the CRM, built from the backup | The real CRM |
| Approving | Changes only the local copy | Writes to the real CRM straight away; cannot be undone |
| Banner colour | Yellow | Red |
| Extra page | **Smoke test** (automated tests, rehearsal, dry run) | none |
| Queue and audit trail | Its own, and can be reset | Its own, permanent |

- The app **always opens in Rehearsal**.
- Switching to Production asks you to confirm first.
- The two modes share nothing. Each has its own queue, its own audit trail and its own connection, so practising in Rehearsal can never affect Production.
- The mode is part of the page address (`/rehearsal/...` or `/production/...`). A button on a Rehearsal page can only ever act on Rehearsal, even if another browser tab has since switched to Production.
- The real CRM is not contacted at all until you open a Production page (or press "Refresh dry run").

To practise with no possibility of reaching Production, start the app with Production switched off:

    PYTHONPATH=src .venv/bin/python -m bellhaven_sync.review_app --rehearsal-only

### The Smoke test page (Rehearsal only)

| Section | What it does |
|---|---|
| 1 · Automated tests | A button that runs all the automated tests and shows whether they passed |
| 2 · Rehearsal | Links to the rehearsal queue and audit trail, and a **Reset rehearsal** button that wipes the practice decisions and rebuilds the local copy from the backup |
| 3 · Dry run | The exact requests Production would send if every waiting proposal were approved. Listing them sends nothing. "Refresh" re-reads the website and the real CRM without writing. |

## The pages

| Page | What it shows |
|---|---|
| **Review queue** | Suggestions grouped by kind (update details, move under Bellhaven, change of ownership, create, duplicate, and so on), with counts of waiting, approved, rejected and failed |
| **Suggestion** | Why it is proposed; a "now" and "will become" table of exactly what would change; the website and the CRM accounts side by side with differences highlighted; the match score with its breakdown; billing figures and the billing rule check; and the Approve and Reject buttons |
| **Communities** | All 35 website communities, the group each fell into, and why. This is where the "already correct" ones can be seen. |
| **Audit trail** | Every decision and every change sent to the CRM, newest first, plus a list of pipeline runs |
| **Smoke test** | Rehearsal only; described above |

## What happens when you click

**Approve:**

1. The approval is saved to the audit trail, with your reason if you typed one.
2. Just before sending, the tool re-reads the account and checks it still holds the values the suggestion was based on. If someone changed it in the meantime, nothing is sent and you are told to re-run the pipeline.
3. The change is sent.
4. The account is read back from the CRM to confirm the new values really landed.
5. The request, the values before, the values after and the CRM's reply are all saved to the audit trail.

**Reject:** the rejection and your reason are saved. Nothing is sent. The same suggestion will not be raised again.

**If a change fails** (for example the internet drops), the suggestion is marked "failed" with the error shown, and a Retry button appears. Steps that already succeeded are not repeated. This matters most for the change-of-ownership suggestions, which have two steps (create the new account, then point the old one at it): a retry reuses the account already created and never makes a second one.

## The audit trail

The app keeps its own permanent record in a database file (`data/audit.db` for Production; Rehearsal has a separate, resettable one under `data/rehearsal/`). It has four lists:

| List | One row per | What it records |
|---|---|---|
| Runs | Daily run | When it ran, how many communities and accounts it read, how many suggestions it found, how many were new |
| Suggestions | Proposed change | The community and account, the kind of change, the evidence and score shown, confidence, and its current state |
| Reviews | Approve or reject | Which suggestion, the decision, the reason, who, and when |
| CRM changes | Request sent to the CRM | The review that authorised it, the account, the exact request, the whole account before and after, each changed field's before and after value, the CRM's reply, and whether the read-back confirmed it |

Three guarantees, enforced by the database itself and checked by automated tests:

1. **Reviews and CRM changes can be added but never edited or deleted.** The database rejects any attempt.
2. **Every CRM change must point to a review.** A change with no approval behind it cannot be recorded, and the code refuses to send one.
3. **A suggestion can only be decided once.**

(A suggestion's *current state* does move forward, from waiting to approved to applied. The proof of each step is in the two locked lists.)

Because a database file cannot be read on GitHub, the same history is also written to a spreadsheet-style file, `data/decisions/audit-export.csv`, after every decision.

The "before" values are also the undo information: any edit can be put back by hand from them. Created accounts cannot be removed (the CRM has no delete), which is why creations are rehearsed first.

## How this stops the tool asking twice

Each suggestion has a fingerprint made from exactly what it would change. When the daily job runs again:

| Situation | What happens |
|---|---|
| Fingerprint never seen | Added to the queue as waiting |
| Seen, still waiting | Evidence refreshed; still one entry |
| Seen, already approved or rejected | Left alone, not raised again |
| Was waiting, but no longer found | Marked withdrawn (the CRM or website changed, so it no longer applies) |

Approved changes also disappear naturally: once the CRM is fixed, there is no longer a difference to find.

## Look and feel

The app uses Bootstrap for layout, with colours and typefaces taken from clipboard.com: a warm cream background, dark maroon text and top bar, a bright yellow primary button, a serif typeface (Lora) for headings and a sans-serif (Work Sans) for body text. It does not use the Clipboard name or logo.

Bootstrap is stored inside the project, so the app works without internet. The two typefaces load from Google Fonts and fall back to standard ones if offline.

## Where the code is

- `src/bellhaven_sync/review_app/` (the app, its pages and styling)
- `src/bellhaven_sync/audit_db.py` (the audit trail)
- `src/bellhaven_sync/apply.py` (the only code that changes the CRM)
- `src/bellhaven_sync/crm_client.py` (the real CRM and the local stand-in used for rehearsal)
- Tests: `tests/test_review_app.py`, `tests/test_audit_db.py`, `tests/test_apply.py`
