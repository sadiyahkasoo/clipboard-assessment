"""Tests for the apply step: the only code that changes the CRM."""

import pytest

from bellhaven_sync import apply, audit_db
from bellhaven_sync.crm_client import CrmError

from .conftest import by_title

BELLHAVEN = "0015QAPLGS3FVYEEEM"


@pytest.fixture()
def loaded(db, result):
    """Return an audit trail holding the 29 standard proposals, all pending."""
    db.upsert_proposals(db.start_run("rehearsal"), result.proposals)
    return db


def _approve(db, title):
    """Approve the proposal with this title and return its id."""
    pid = by_title(db.list_proposals(), title)["id"]
    db.add_review(pid, "approved", "", "tester", "rehearsal")
    return pid


def test_nothing_is_sent_without_an_approval(loaded, crm, accounts):
    pid = by_title(loaded.list_proposals(), "Update details: Bellhaven of Chagrin Falls")["id"]
    with pytest.raises(apply.ApplyError, match="not been approved"):
        apply.apply_proposal(loaded, crm, pid)
    assert crm.list_accounts() == accounts            # CRM untouched
    assert loaded.changes_for(pid) == []


def test_a_rejected_proposal_is_never_sent(loaded, crm, accounts):
    pid = by_title(loaded.list_proposals(), "Address differs: Bellhaven of Ashtabula")["id"]
    loaded.add_review(pid, "rejected", "PO Box is valid", "tester", "rehearsal")
    with pytest.raises(apply.ApplyError):
        apply.apply_proposal(loaded, crm, pid)
    assert crm.list_accounts() == accounts


def test_approved_rename_lands_and_is_audited(loaded, crm):
    pid = _approve(loaded, "Update details: Bellhaven of Chagrin Falls")
    apply.apply_proposal(loaded, crm, pid)
    account_id = loaded.get_proposal(pid)["account_id"]
    assert crm.get_account(account_id)["name"] == "Bellhaven of Chagrin Falls"
    assert loaded.get_proposal(pid)["state"] == audit_db.STATE_APPLIED
    (change,) = loaded.changes_for(pid)
    assert change["success"] == 1 and change["verified"] == 1
    assert change["fields"] == {"name": ["Riverbend Manor Care Center", "Bellhaven of Chagrin Falls"]}
    assert change["review_id"] == loaded.review_for(pid)["id"]


def test_chow_creates_new_account_and_leaves_old_one_untouched(loaded, crm, accounts):
    pid = _approve(loaded, "Change of ownership: Bellhaven of Tiffin")
    old_id = loaded.get_proposal(pid)["account_id"]
    before = next(a for a in accounts if a["account_id"] == old_id)
    apply.apply_proposal(loaded, crm, pid)

    after = crm.get_account(old_id)
    new = crm.get_account(after["chow_current_account"])
    assert new["parent_id"] == BELLHAVEN and new["name"] == "Bellhaven of Tiffin"
    assert new["created_by_candidate"] is True
    # Everything on the old account except the pointer (and its timestamp) is unchanged.
    for name, value in before.items():
        if name not in ("chow_current_account", "updated_at"):
            assert after[name] == value, name
    assert [c["method"] for c in loaded.changes_for(pid)] == ["POST", "PATCH"]


def test_retry_after_half_finished_chow_does_not_create_a_second_account(loaded, crm):
    """If step 2 fails, a retry reuses the account created in step 1."""
    pid = _approve(loaded, "Change of ownership: Bellhaven of Marietta")
    real_update = crm.update_account
    crm.update_account = lambda *a, **k: (_ for _ in ()).throw(CrmError("boom", status=500))
    with pytest.raises(apply.ApplyError):
        apply.apply_proposal(loaded, crm, pid)
    assert loaded.get_proposal(pid)["state"] == audit_db.STATE_FAILED
    count_after_failure = len(crm.list_accounts())

    crm.update_account = real_update
    apply.apply_proposal(loaded, crm, pid)
    assert len(crm.list_accounts()) == count_after_failure     # no second create
    assert loaded.get_proposal(pid)["state"] == audit_db.STATE_APPLIED
    outcomes = [(c["method"], c["success"]) for c in loaded.changes_for(pid)]
    assert outcomes == [("POST", 1), ("PATCH", 0), ("PATCH", 1)]   # failure stays on record


def test_lost_reply_on_create_adopts_the_existing_account(loaded, crm):
    """If the CRM created the account but the reply never arrived, adopt it."""
    pid = _approve(loaded, "Create account: Bellhaven of Batavia")
    fields = loaded.get_proposal(pid)["operations"][0]["set"]
    orphan = crm.create_account(fields)            # simulates the lost-reply create
    apply.apply_proposal(loaded, crm, pid)
    assert len([a for a in crm.list_accounts() if a["name"] == "Bellhaven of Batavia"]) == 1
    assert loaded.changes_for(pid)[0]["account_id"] == orphan["account_id"]


def test_stale_proposal_is_refused(loaded, crm):
    """If the account changed after the proposal was made, do not overwrite it."""
    pid = _approve(loaded, "Update details: Bellhaven of Portsmouth")
    account_id = loaded.get_proposal(pid)["account_id"]
    crm.update_account(account_id, {"billing_zip": "99999"})    # someone else edits it
    with pytest.raises(apply.ApplyError, match="changed since"):
        apply.apply_proposal(loaded, crm, pid)
    assert crm.get_account(account_id)["billing_zip"] == "99999"
    assert loaded.get_proposal(pid)["state"] == audit_db.STATE_FAILED


def test_duplicate_is_marked_inactive_and_pointed_at_survivor(loaded, crm):
    pid = _approve(loaded, "Mark duplicate: Harborview Shores of Erie")
    apply.apply_proposal(loaded, crm, pid)
    dup = crm.get_account(loaded.get_proposal(pid)["account_id"])
    assert dup["status"] == "Inactive"
    assert crm.get_account(dup["duplicate_of_account"])["name"] == "Bellhaven Shores of Erie"
    assert dup["parent_name"].startswith("Harborview")       # owner left alone


def test_client_refuses_to_write_money_or_unknown_fields(crm):
    with pytest.raises(ValueError):
        crm.update_account(BELLHAVEN, {"outstanding_ar": 0})
    with pytest.raises(ValueError):
        crm.update_account(BELLHAVEN, {"status": "Deleted"})
