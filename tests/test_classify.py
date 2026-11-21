"""
Tests for classification: do the scores turn into the right proposals?

These check the expected findings table in docs/01-plan.md, the billing
rule (CHOW), duplicate handling and the fingerprint used for safe re-runs.
"""

import collections
import copy

from bellhaven_sync import classify
from bellhaven_sync.classify import (KIND_ADDRESS, KIND_CHOW, KIND_CHOW_LINK, KIND_CREATE,
                                     KIND_DUPLICATE, KIND_OFF_WEBSITE, KIND_REPARENT,
                                     KIND_UPDATE, NEW_ACCOUNT_REF)

from .conftest import by_title

BELLHAVEN = "0015QAPLGS3FVYEEEM"


def test_proposal_counts_match_the_plan(result):
    kinds = collections.Counter(p.kind for p in result.proposals)
    assert kinds == {KIND_UPDATE: 8, KIND_DUPLICATE: 7, KIND_REPARENT: 4, KIND_CREATE: 4,
                     KIND_CHOW: 2, KIND_OFF_WEBSITE: 2, KIND_ADDRESS: 1, KIND_CHOW_LINK: 1}
    assert len(result.proposals) == 29


def test_community_groups(result):
    groups = collections.Counter(g for row in result.communities for g in row["groups"])
    assert groups["confident_match"] == 16
    assert groups["new_account"] == 4
    assert len(result.communities) == 35


def test_confident_match_produces_no_proposal(result):
    row = next(r for r in result.communities if r["slug"] == "bellhaven-of-maplewood")
    assert row["groups"] == ["confident_match"] and row["proposal_keys"] == []


def test_billing_rule_preserves_account_with_revenue_and_outstanding_ar(result, accounts):
    """Tiffin owes money: create a new account, only set the pointer on the old."""
    p = by_title(result.proposals, "Change of ownership: Bellhaven of Tiffin")
    create, pointer = p.operations
    assert create["action"] == "create" and create["set"]["parent_id"] == BELLHAVEN
    assert create["set"]["name"] == "Bellhaven of Tiffin"
    # The ONLY field touched on the old account is the CHOW pointer.
    assert pointer["action"] == "update" and pointer["set"] == {"chow_current_account": NEW_ACCOUNT_REF}
    old = next(a for a in accounts if a["account_id"] == pointer["account_id"])
    assert old["lifetime_revenue"] > 0 and old["outstanding_ar"] > 0


def test_revenue_but_nothing_owed_is_reparented_directly(result):
    """Lima has revenue history but zero AR, so the rule allows a direct move."""
    p = by_title(result.proposals, "Move under Bellhaven: Bellhaven Crossings of Lima")
    assert p.kind == KIND_REPARENT
    assert p.operations == [{**p.operations[0], "set": {"parent_id": BELLHAVEN}}]
    assert p.evidence["billing"] == {"lifetime_revenue": 47000, "outstanding_ar": 0}


def test_needs_chow_truth_table():
    assert classify.needs_chow({"lifetime_revenue": 100, "outstanding_ar": 1})
    assert not classify.needs_chow({"lifetime_revenue": 100, "outstanding_ar": 0})
    assert not classify.needs_chow({"lifetime_revenue": 0, "outstanding_ar": 50})
    assert not classify.needs_chow({"lifetime_revenue": 0, "outstanding_ar": 0})


def test_reparent_can_carry_a_rename(result):
    p = by_title(result.proposals, "Move under Bellhaven: Bellhaven of Zanesville")
    assert p.operations[0]["set"] == {"parent_id": BELLHAVEN, "name": "Bellhaven of Zanesville"}
    assert p.operations[0]["expect"]["name"] == "Cedar Trail of Zanesville"


def test_duplicates_point_at_the_copy_already_under_bellhaven(result, accounts):
    monroe = [p for p in result.proposals if p.kind == KIND_DUPLICATE and p.slug == "bellhaven-gardens-of-monroe"]
    assert len(monroe) == 2
    keep = next(a for a in accounts if a["name"] == "Bellhaven Gardens of Monroe")["account_id"]
    for p in monroe:
        assert p.operations[0]["set"]["status"] == "Inactive"
        assert p.operations[0]["set"]["duplicate_of_account"] == keep
        assert p.account_id != keep


def test_identical_twins_keep_the_one_with_more_evidence(result, accounts):
    """Two 'Bellhaven of Owosso' accounts: keep the one whose phone and contacts match."""
    p = by_title(result.proposals, "Mark duplicate: Bellhaven of Owosso")
    kept = next(a for a in accounts if a["account_id"] == p.operations[0]["set"]["duplicate_of_account"])
    assert kept["phone"] == "(734) 503-1363"      # the website's phone number


def test_three_copies_none_under_bellhaven(result):
    """Kettering: one copy is kept and moved, the other two become duplicates."""
    move = by_title(result.proposals, "Move under Bellhaven: Bellhaven of Kettering")
    dups = [p for p in result.proposals if p.kind == KIND_DUPLICATE and p.slug == "bellhaven-of-kettering"]
    assert len(dups) == 2
    assert {p.operations[0]["set"]["duplicate_of_account"] for p in dups} == {move.account_id}
    assert move.operations[0]["set"]["name"] == "Bellhaven of Kettering"


def test_lookalikes_are_shown_but_never_changed(result, accounts):
    """Union Square Senior Living is evidence on the create proposal, nothing more."""
    p = by_title(result.proposals, "Create account: Bellhaven at Union Square")
    lookalike = next(a for a in accounts if a["name"] == "Union Square Senior Living")
    assert [a["account_id"] for a in p.evidence["accounts"]] == [lookalike["account_id"]]
    touched = {op.get("account_id") for q in result.proposals for op in q.operations}
    assert lookalike["account_id"] not in touched
    for decoy in ("Maplewood Senior Care Center", "Amberly Manor"):
        assert next(a for a in accounts if a["name"] == decoy)["account_id"] not in touched


def test_create_uses_website_values_and_crm_vocabulary(result):
    p = by_title(result.proposals, "Create account: Bellhaven of Carlisle")
    fields = p.operations[0]["set"]
    assert fields["billing_city"] == "Carlisle" and fields["billing_state"] == "PA"
    assert fields["care_type"] == "Skilled Nursing"      # mapped from the website wording
    assert fields["parent_id"] == BELLHAVEN and fields["status"] == "Active"


def test_po_box_address_is_a_low_confidence_suggestion(result):
    p = by_title(result.proposals, "Address differs: Bellhaven of Ashtabula")
    assert p.confidence == "low" and p.operations[0]["set"] == {"billing_street": "3156 W Prospect Rd"}


def test_zip_typo_fix(result):
    p = by_title(result.proposals, "Update details: Bellhaven of Portsmouth")
    assert p.operations[0]["set"] == {"billing_zip": "45662"}


def test_off_website_accounts_are_flagged_not_guessed(result):
    for name in ("Alliance", "Coldwater"):
        p = by_title(result.proposals, f"No longer on website: Bellhaven {'Care Center of ' if name == 'Alliance' else 'of '}{name}")
        assert p.operations[0]["set"]["status"] == "Needs Review"
        assert "parent_id" not in p.operations[0]["set"]


def test_sold_account_with_billing_gets_only_a_pointer(result, accounts):
    """Sandusky owes money and Millstone already has an account at that address."""
    p = by_title(result.proposals, "Sold to another owner: Bellhaven of Sandusky")
    millstone = next(a for a in accounts if a["name"] == "Millstone Care of Sandusky")
    assert p.operations[0]["set"] == {"chow_current_account": millstone["account_id"]}


def test_phones_are_never_proposed_for_change(result):
    for p in result.proposals:
        for op in p.operations:
            if op["action"] == "update":
                assert "phone" not in op["set"]


def test_money_fields_are_never_written(result):
    for p in result.proposals:
        for op in p.operations:
            assert not {"lifetime_revenue", "outstanding_ar"} & set(op["set"])


def test_keys_are_unique_and_stable(result, locations, accounts, contacts):
    """The same finding gives the same fingerprint on every run."""
    keys = [p.key for p in result.proposals]
    assert len(set(keys)) == len(keys)
    again = classify.classify(locations, copy.deepcopy(accounts), contacts)
    assert [p.key for p in again.proposals] == keys


def test_planned_requests_show_method_path_and_body(result):
    p = by_title(result.proposals, "Change of ownership: Bellhaven of Marietta")
    first, second = classify.planned_requests(p)
    assert (first["method"], first["path"]) == ("POST", "/accounts")
    assert second["method"] == "PATCH" and second["path"].startswith("/accounts/001")
