"""
End-to-end tests of the daily job, offline: saved website + stand-in CRM.

The key promise tested here is re-run safety: after everything has been
decided, running the job again proposes nothing.
"""

import json

from bellhaven_sync import apply, audit_db, pipeline


def _run(crm, db, site_fetch, tmp_path):
    """Run the pipeline once against the test doubles and return its summary."""
    return pipeline.run("rehearsal", client=crm, fetch=site_fetch, db=db, runs_dir=tmp_path / "runs")


def test_pipeline_never_changes_the_crm(crm, db, site_fetch, tmp_path, accounts):
    _run(crm, db, site_fetch, tmp_path)
    assert crm.list_accounts() == accounts


def test_first_run_proposes_29_and_writes_the_trace(crm, db, site_fetch, tmp_path):
    summary = _run(crm, db, site_fetch, tmp_path)
    assert summary["status"] == "ok" and summary["locations"] == 35 and summary["accounts"] == 121
    assert summary["proposals"]["new"] == 29
    run_dir = tmp_path / "runs" / summary["started_at"]
    for trace in ("01_scrape/locations.json", "01_scrape/pages/home.html", "02_crm/accounts.json",
                  "03_matching/scores.csv", "03_matching/communities.json",
                  "04_proposals/proposals.json", "04_proposals/planned_requests.md", "summary.json"):
        assert (run_dir / trace).exists(), trace
    assert len(json.loads((run_dir / "01_scrape" / "locations.json").read_text())) == 35


def test_rerun_without_decisions_adds_nothing(crm, db, site_fetch, tmp_path):
    _run(crm, db, site_fetch, tmp_path)
    again = _run(crm, db, site_fetch, tmp_path)
    assert again["proposals"]["new"] == 0
    assert len(db.list_proposals()) == 29


def test_after_everything_is_decided_a_rerun_proposes_nothing(crm, db, site_fetch, tmp_path):
    """Approve all but one, reject that one, apply, then run again."""
    _run(crm, db, site_fetch, tmp_path)
    for p in db.list_proposals():
        if p["kind"] == "address_update":
            db.add_review(p["id"], "rejected", "PO Box is valid", "tester", "rehearsal")
        else:
            db.add_review(p["id"], "approved", "", "tester", "rehearsal")
            apply.apply_proposal(db, crm, p["id"])
    assert db.state_counts() == {audit_db.STATE_APPLIED: 28, audit_db.STATE_REJECTED: 1}

    again = _run(crm, db, site_fetch, tmp_path)
    # The only finding left is the rejected one, and it is not raised again.
    assert again["proposals"] == {"total": 1, "new": 0, "refreshed": 0, "suppressed": 1, "withdrawn": 0}
    assert db.state_counts() == {audit_db.STATE_APPLIED: 28, audit_db.STATE_REJECTED: 1}


def test_corrected_crm_end_state(crm, db, site_fetch, tmp_path):
    """After approving everything, the CRM reflects the website."""
    _run(crm, db, site_fetch, tmp_path)
    for p in db.list_proposals():
        db.add_review(p["id"], "approved", "", "tester", "rehearsal")
        apply.apply_proposal(db, crm, p["id"])
    final = crm.list_accounts()
    bellhaven = next(a for a in final if a["name"].startswith("Bellhaven Senior Living"))["account_id"]
    live_children = [a for a in final if a["parent_id"] == bellhaven
                     and not a["duplicate_of_account"] and not a["chow_current_account"]
                     and a["status"] == "Active"]
    # 35 website communities, each with exactly one active Bellhaven account.
    assert len(live_children) == 35
    assert len(final) == 121 + 6       # 4 new communities + 2 CHOW accounts
    assert sum(1 for a in final if a["duplicate_of_account"]) == 7
    assert sum(1 for a in final if a["chow_current_account"]) == 3
    assert sum(1 for a in final if a["status"] == "Needs Review") == 2


def test_run_stops_if_the_website_suddenly_lists_far_fewer_communities(crm, db, site_fetch, tmp_path):
    """A broken site must not make every account look 'no longer on website'."""
    _run(crm, db, site_fetch, tmp_path)

    def broken_fetch(path):
        # Serve only the home page links: 1 community instead of 35.
        if path.startswith("/communities?"):
            return "<html><body><div class='wrap'><h1>Our Communities</h1></div></body></html>"
        return site_fetch(path)

    summary = pipeline.run("rehearsal", client=crm, fetch=broken_fetch, db=db, runs_dir=tmp_path / "runs2")
    assert summary["status"] == "aborted"
    assert db.state_counts() == {audit_db.STATE_PENDING: 29}     # nothing withdrawn or added


def test_log_line_is_one_readable_line(crm, db, site_fetch, tmp_path):
    line = pipeline.log_line(_run(crm, db, site_fetch, tmp_path))
    assert "\n" not in line and "communities=35" in line and "new=29" in line
