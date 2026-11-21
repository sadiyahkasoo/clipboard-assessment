# Working rules for this exercise

These are the rules everyone (and every tool) working on this exercise follows. They are written in plain language on purpose.

## Rules set by the reviewer

1. **Back up first.** Before anything else, save a full local copy of every CRM account and contact. The CRM only has about 120 accounts, so a complete copy is cheap and gives us something to compare against and restore from.
2. **Smoke test before any real change.** The CRM has no delete and no undo. Every change is rehearsed and checked before it is sent for real, even though this is a sandbox.
3. **Plans live in `docs/` as `.md` files.** They are written so a non-technical colleague can follow them. That includes these rules.
4. **Every Python file is clearly commented.** Comments explain what the code does. They may use technical terms (arguments, parameters, return values).
5. **Clean folder layout.** Source code lives in `src/`, tests live in `tests/`.
6. **No outside library without approval.** Anything not built into Python is listed in the plan and approved before it is installed.
7. **Every step can be re-traced.** Scraping, matching, the review app and the daily schedule each leave a record of what went in, what came out, and why.
8. **The daily schedule is built last and is made live** on this computer.
9. **Matching is explained in detail,** including how the score cut-offs were chosen.
10. **The review app keeps an audit trail.** A local database records every review decision and every change the app made to the CRM.
11. **The review app has a clean Bootstrap interface** styled after clipboard.com.
12. **Final work is stored in GitHub** at `https://github.com/sadiyahkasoo/clipboard-assessment`, with commits shown under Sadiyah's name.

## Rules from the exercise brief

13. **Nothing writes without approval.** A change reaches the CRM only after a reviewer approves it in the review app.
14. **Re-runs are safe.** Running the daily job again never re-proposes something that was already approved or rejected.
15. **Duplicates.** There is no merge or delete. The losing copy gets `duplicate_of_account` set to the surviving account's id and is marked `Inactive`.
16. **Other outcomes** are expressed with the `status` field (`Active`, `Inactive`, `Needs Review`) and the free-text `note` field.
17. **The billing rule (change of ownership, "CHOW").** Before moving an account to a different owner, check `lifetime_revenue` and `outstanding_ar`:
    - If the account has revenue history **and** money still owed (outstanding AR above zero): do **not** change its owner. Leave the old account exactly as it is, create a new account for the facility under the correct owner, and set `chow_current_account` on the old account to the new account's id.
    - If it has no revenue history, **or** nothing is owed: move the existing account to the new owner directly.

## Approved outside libraries

| Library | Used for |
|---|---|
| `requests` | Talking to the website and the CRM |
| `beautifulsoup4` | Reading details out of web pages |
| `flask` | The local review app |
| `pytest` | Running the automated tests |
| Bootstrap 5 | Layout of the review app (a copy is kept inside the project) |
| Lora and Work Sans typefaces | Matching the clipboard.com look |
