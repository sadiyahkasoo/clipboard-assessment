"""Tests for the audit trail database."""

import csv
import sqlite3

import pytest

from bellhaven_sync import audit_db


def _load(db, result):
    """Store the standard proposals in a fresh run and return the counts."""
    return db.upsert_proposals(db.start_run("rehearsal"), result.proposals)


def test_first_run_stores_everything_as_new(db, result):
    counts = _load(db, result)
    assert counts["new"] == 29 and counts["suppressed"] == 0
    assert db.state_counts() == {audit_db.STATE_PENDING: 29}


def test_second_run_does_not_duplicate_pending_proposals(db, result):
    _load(db, result)
    counts = _load(db, result)
    assert counts["new"] == 0 and counts["refreshed"] == 29
    assert len(db.list_proposals()) == 29


def test_decided_proposals_are_not_raised_again(db, result):
    """Approved or rejected items stay decided when the same finding returns."""
    _load(db, result)
    first, second = db.list_proposals()[:2]
    db.add_review(first["id"], "rejected", "not needed", "tester", "rehearsal")
    db.add_review(second["id"], "approved", "", "tester", "rehearsal")
    counts = _load(db, result)
    assert counts["suppressed"] == 2 and counts["new"] == 0
    assert db.get_proposal(first["id"])["state"] == audit_db.STATE_REJECTED
    assert db.get_proposal(second["id"])["state"] == audit_db.STATE_APPROVED


def test_pending_proposal_no_longer_found_is_withdrawn(db, result):
    _load(db, result)
    counts = db.upsert_proposals(db.start_run("rehearsal"), result.proposals[1:])
    assert counts["withdrawn"] == 1
    assert db.state_counts()[audit_db.STATE_WITHDRAWN] == 1


def test_a_proposal_can_only_be_decided_once(db, result):
    _load(db, result)
    pid = db.list_proposals()[0]["id"]
    db.add_review(pid, "approved", "", "tester", "rehearsal")
    with pytest.raises(ValueError):
        db.add_review(pid, "rejected", "changed my mind", "tester", "rehearsal")


def test_reviews_and_changes_cannot_be_edited_or_deleted(db, result):
    """The history tables are locked by the database itself."""
    _load(db, result)
    pid = db.list_proposals()[0]["id"]
    rid = db.add_review(pid, "approved", "", "tester", "rehearsal")
    db.add_change(review_id=rid, proposal_id=pid, step=1, method="PATCH", path="/accounts/x",
                  account_id="x", request={"name": "B"}, before={"name": "A"}, after={"name": "B"},
                  response_status="ok", response={}, success=True, verified=True, error="", mode="rehearsal")
    for statement in ("UPDATE reviews SET decision = 'rejected'", "DELETE FROM reviews",
                      "UPDATE crm_changes SET success = 0", "DELETE FROM crm_changes"):
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(statement)


def test_a_change_must_reference_a_review(db, result):
    """There can be no CRM change without an approval behind it."""
    _load(db, result)
    pid = db.list_proposals()[0]["id"]
    with pytest.raises(sqlite3.IntegrityError):
        db.add_change(review_id=999, proposal_id=pid, step=1, method="PATCH", path="/accounts/x",
                      account_id="x", request={}, before=None, after=None, response_status="ok",
                      response={}, success=True, verified=True, error="", mode="rehearsal")


def test_change_records_before_and_after_per_field(db, result):
    _load(db, result)
    pid = db.list_proposals()[0]["id"]
    rid = db.add_review(pid, "approved", "", "tester", "rehearsal")
    db.add_change(review_id=rid, proposal_id=pid, step=1, method="PATCH", path="/accounts/x",
                  account_id="x", request={"name": "New"}, before={"name": "Old", "status": "Active"},
                  after={"name": "New", "status": "Active"}, response_status="ok", response={},
                  success=True, verified=True, error="", mode="rehearsal")
    change = db.changes_for(pid)[0]
    assert change["fields"] == {"name": ["Old", "New"]}
    assert change["before"]["status"] == "Active"


def test_csv_export_is_readable(db, result, tmp_path):
    _load(db, result)
    pid = db.list_proposals()[0]["id"]
    db.add_review(pid, "rejected", "PO Box is fine", "tester", "rehearsal")
    rows = list(csv.DictReader(db.export_csv(tmp_path / "out" / "audit.csv").open()))
    assert len(rows) == 1 and rows[0]["decision"] == "rejected" and rows[0]["reason"] == "PO Box is fine"
