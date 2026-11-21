"""Tests for the review app, driven through Flask's test client."""

import pytest

from bellhaven_sync import audit_db, pipeline
from bellhaven_sync.review_app import create_app

from .conftest import by_title


@pytest.fixture()
def web(crm, db, site_fetch, tmp_path):
    """Return (test client, db, crm) for an app loaded with the 29 proposals.

    Only the rehearsal mode is supplied and production is switched off, so
    these tests cannot reach the real CRM.
    """
    pipeline.run("rehearsal", client=crm, fetch=site_fetch, db=db, runs_dir=tmp_path / "runs")
    app = create_app(
        contexts={"rehearsal": {"client": crm, "db": db, "export_csv": tmp_path / "audit.csv"}},
        allow_production=False, dry_run_db=tmp_path / "no-dry-run-yet.db")
    app.config["TESTING"] = True
    return app.test_client(), db, crm


def test_queue_lists_pending_proposals_and_shows_rehearsal_banner(web):
    client, _db, _crm = web
    page = client.get("/rehearsal/").get_data(as_text=True)
    assert "REHEARSAL" in page and "Change of ownership: Bellhaven of Tiffin" in page
    assert "Mark duplicate" in page


def test_viewing_pages_changes_nothing(web, accounts):
    client, db, crm = web
    for p in db.list_proposals():
        assert client.get(f"/rehearsal/proposal/{p['id']}").status_code == 200
    assert client.get("/rehearsal/communities").status_code == 200
    assert client.get("/rehearsal/audit").status_code == 200
    assert crm.list_accounts() == accounts
    assert db.history() == []


def test_proposal_page_shows_evidence_and_billing_rule(web):
    client, db, _crm = web
    pid = by_title(db.list_proposals(), "Change of ownership: Bellhaven of Tiffin")["id"]
    page = client.get(f"/rehearsal/proposal/{pid}").get_data(as_text=True)
    assert "Billing rule check" in page and "12,400" in page
    assert "Cedar Trail Communities" in page and "Approve and write to CRM" in page


def test_approve_writes_to_crm_and_audit_trail(web, tmp_path):
    client, db, crm = web
    p = by_title(db.list_proposals(), "Update details: Bellhaven of Chagrin Falls")
    response = client.post(f"/rehearsal/proposal/{p['id']}/approve", data={"reason": "matches website"},
                           follow_redirects=True)
    assert "Approved and written to the rehearsal copy" in response.get_data(as_text=True)
    assert crm.get_account(p["account_id"])["name"] == "Bellhaven of Chagrin Falls"
    assert db.get_proposal(p["id"])["state"] == audit_db.STATE_APPLIED
    assert db.review_for(p["id"])["reason"] == "matches website"
    assert [e["event"] for e in db.history()] == ["crm_change", "review"]
    assert (tmp_path / "audit.csv").exists()


def test_reject_sends_nothing_and_is_recorded(web, accounts):
    client, db, crm = web
    p = by_title(db.list_proposals(), "Address differs: Bellhaven of Ashtabula")
    response = client.post(f"/rehearsal/proposal/{p['id']}/reject", data={"reason": "PO Box is valid"},
                           follow_redirects=True)
    assert "Nothing was sent to the CRM" in response.get_data(as_text=True)
    assert crm.list_accounts() == accounts
    assert db.get_proposal(p["id"])["state"] == audit_db.STATE_REJECTED
    assert db.changes_for(p["id"]) == []


def test_cannot_decide_twice(web):
    client, db, _crm = web
    p = by_title(db.list_proposals(), "Address differs: Bellhaven of Ashtabula")
    client.post(f"/rehearsal/proposal/{p['id']}/reject", data={})
    client.post(f"/rehearsal/proposal/{p['id']}/approve", data={})
    assert db.get_proposal(p["id"])["state"] == audit_db.STATE_REJECTED
    assert db.changes_for(p["id"]) == []


def test_every_crm_change_has_an_approving_review(web):
    """Approve everything through the app, then check the audit trail links up."""
    client, db, _crm = web
    for p in db.list_proposals():
        client.post(f"/rehearsal/proposal/{p['id']}/approve", data={})
    changes = [c for p in db.list_proposals() for c in db.changes_for(p["id"])]
    assert len(changes) == 31          # 29 proposals; the 2 CHOW ones send 2 requests each
    for change in changes:
        review = db.conn.execute("SELECT * FROM reviews WHERE id = ?", (change["review_id"],)).fetchone()
        assert review["decision"] == "approved" and review["proposal_id"] == change["proposal_id"]
    assert client.get("/rehearsal/").get_data(as_text=True).count("Nothing here") == 1


# ---------------------------------------------------------------- mode switch

def test_bare_address_opens_rehearsal_by_default(web):
    client, _db, _crm = web
    response = client.get("/")
    assert response.status_code == 302 and response.headers["Location"].endswith("/rehearsal/")


def test_unknown_mode_in_address_is_not_found(web):
    client, _db, _crm = web
    assert client.get("/staging/").status_code == 404


def test_production_can_be_switched_off_for_a_session(web):
    """With --rehearsal-only, production pages bounce back to rehearsal."""
    client, db, _crm = web
    response = client.get("/production/")
    assert response.status_code == 302 and response.headers["Location"].endswith("/rehearsal/")
    pid = db.list_proposals()[0]["id"]
    client.post(f"/production/proposal/{pid}/approve", data={})
    assert db.history() == []                       # nothing was decided anywhere


def test_smoke_page_is_shown_in_rehearsal(web):
    client, _db, _crm = web
    page = client.get("/rehearsal/smoke").get_data(as_text=True)
    assert "Smoke test and dry run" in page and "Automated tests" in page
    assert "not run yet" in page                    # no dry-run database supplied


@pytest.fixture()
def both_modes(accounts, contacts, site_fetch, tmp_path):
    """Return an app with BOTH modes backed by separate stand-in CRMs.

    "Production" here is a second local stand-in, never the real CRM. It lets
    the tests prove the two modes are completely separate.
    """
    from bellhaven_sync.crm_client import LocalCrm

    made = {}
    for mode in ("rehearsal", "live"):
        crm = LocalCrm(path=None, accounts=accounts, contacts=contacts)
        db = audit_db.AuditDb(tmp_path / f"{mode}.db")
        pipeline.run(mode, client=crm, fetch=site_fetch, db=db, runs_dir=tmp_path / f"runs-{mode}")
        made[mode] = {"client": crm, "db": db, "export_csv": tmp_path / f"{mode}.csv"}
    app = create_app(contexts=made, dry_run_db=tmp_path / "live.db")
    app.config["TESTING"] = True
    return app.test_client(), made


def test_each_mode_shows_its_own_banner_and_the_switch(both_modes):
    client, _made = both_modes
    rehearsal_page = client.get("/rehearsal/").get_data(as_text=True)
    production_page = client.get("/production/").get_data(as_text=True)
    assert "REHEARSAL" in rehearsal_page and "PRODUCTION ·" not in rehearsal_page
    assert "PRODUCTION ·" in production_page and "REHEARSAL ·" not in production_page
    assert "Switch to Production?" in rehearsal_page          # confirmation before switching
    assert "/rehearsal/" in production_page                   # link back


def test_links_on_a_page_stay_in_that_pages_mode(both_modes):
    """A rehearsal page can only post to rehearsal addresses, and vice versa."""
    client, made = both_modes
    pid = made["rehearsal"]["db"].list_proposals()[0]["id"]
    page = client.get(f"/rehearsal/proposal/{pid}").get_data(as_text=True)
    assert f"/rehearsal/proposal/{pid}/approve" in page
    assert f"/production/proposal/{pid}/approve" not in page


def test_approving_in_rehearsal_never_touches_production(both_modes, accounts):
    client, made = both_modes
    p = by_title(made["rehearsal"]["db"].list_proposals(), "Update details: Bellhaven of Chagrin Falls")
    client.post(f"/rehearsal/proposal/{p['id']}/approve", data={})
    assert made["rehearsal"]["client"].get_account(p["account_id"])["name"] == "Bellhaven of Chagrin Falls"
    assert made["live"]["client"].list_accounts() == accounts          # production untouched
    assert made["live"]["db"].history() == []
    assert made["live"]["db"].state_counts() == {audit_db.STATE_PENDING: 29}


def test_approving_in_production_writes_to_production_only(both_modes, accounts):
    client, made = both_modes
    p = by_title(made["live"]["db"].list_proposals(), "Update details: Bellhaven of Portsmouth")
    client.post(f"/production/proposal/{p['id']}/approve", data={})
    assert made["live"]["client"].get_account(p["account_id"])["billing_zip"] == "45662"
    assert made["live"]["db"].review_for(p["id"])["mode"] == "live"
    assert made["rehearsal"]["client"].list_accounts() == accounts
    assert made["rehearsal"]["db"].history() == []


def test_dry_run_lists_production_requests_without_sending(both_modes, accounts):
    """The Smoke test page shows what production would send; viewing it sends nothing."""
    client, made = both_modes
    page = client.get("/rehearsal/smoke").get_data(as_text=True)
    assert "29 proposals · 31 requests waiting" in page
    assert "Change of ownership: Bellhaven of Tiffin" in page and "PATCH" in page and "POST" in page
    assert made["live"]["client"].list_accounts() == accounts
    assert made["live"]["db"].history() == []


def test_smoke_page_is_rehearsal_only(both_modes):
    client, _made = both_modes
    response = client.get("/production/smoke")
    assert response.status_code == 302 and response.headers["Location"].endswith("/rehearsal/smoke")
