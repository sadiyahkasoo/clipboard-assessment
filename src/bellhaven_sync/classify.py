"""
Step 3b: turn match scores into proposed changes.

matcher.py says how alike a community and an account are. This module
decides what that means and what, if anything, should be proposed:

    one match, everything agrees      -> confident match, nothing to do
    one match, details differ         -> "update details" proposal
    match under the wrong owner       -> "re-parent" proposal, or, when the
                                         billing rule applies, a "CHOW"
                                         proposal (new account + pointer)
    several matches                   -> keep one, "mark duplicate" for the rest
    no match                          -> "create account" proposal
    Bellhaven account, no community   -> "no longer on website" proposal

It never talks to the CRM. It takes data in and returns proposals, which
makes it fully testable offline.

Each proposal carries:
    key         a fingerprint of exactly what it would change. The same
                finding always produces the same key, which is how re-runs
                recognise something that was already decided.
    operations  the exact CRM requests it would make, in order.
    evidence    everything the reviewer needs to judge it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from . import config
from .matcher import (BAND_LOOKALIKE, BAND_MATCH, BAND_PROBABLE, Score,
                      contacts_by_account, score_all)
from .normalize import norm_street
from .scraper import Location

# Proposal kinds (stored in the audit trail and shown in the review app).
KIND_UPDATE = "update_details"        # fix name / zip / care type on a matched account
KIND_ADDRESS = "address_update"       # replace the street address (low confidence)
KIND_REPARENT = "reparent"            # move the account under Bellhaven directly
KIND_CHOW = "chow_new_account"        # billing rule: new account + pointer on the old one
KIND_CREATE = "create_account"        # community has no CRM account
KIND_DUPLICATE = "mark_duplicate"     # losing copy -> Inactive + duplicate_of_account
KIND_OFF_WEBSITE = "off_website"      # under Bellhaven but not on the website
KIND_CHOW_LINK = "chow_link_existing"  # sold: point old account at the new owner's account

KIND_LABELS: dict[str, str] = {
    KIND_UPDATE: "Update details",
    KIND_ADDRESS: "Address differs",
    KIND_REPARENT: "Move under Bellhaven",
    KIND_CHOW: "Change of ownership (billing rule)",
    KIND_CREATE: "Create new account",
    KIND_DUPLICATE: "Mark duplicate",
    KIND_OFF_WEBSITE: "No longer on website",
    KIND_CHOW_LINK: "Sold to another owner",
}

# Placeholder used in later operations to mean "the id of the account that
# the create operation in this same proposal produced".
NEW_ACCOUNT_REF = "{{new_account}}"

# Account fields shown to the reviewer as evidence.
EVIDENCE_FIELDS = (
    "account_id", "name", "parent_id", "parent_name", "billing_street", "billing_city",
    "billing_state", "billing_zip", "care_type", "status", "phone",
    "lifetime_revenue", "outstanding_ar", "chow_current_account",
    "duplicate_of_account", "note",
)


@dataclass
class Proposal:
    """One suggested change awaiting a reviewer's decision.

    Attributes:
        key: Fingerprint of what this proposal would change.
        kind: One of the KIND_* constants.
        title: Short heading for the review queue.
        summary: One or two plain sentences saying what and why.
        confidence: "high", "medium" or "low".
        slug: Website community this relates to ("" if none).
        account_id: Main CRM account affected ("" for a pure create).
        evidence: Supporting facts for the reviewer (website values, account
            values, score breakdown, billing figures, lookalikes).
        operations: Ordered CRM requests. Each is a dict:
            {"step": 1, "action": "update", "account_id": "...",
             "set": {field: new}, "expect": {field: current}}
            or
            {"step": 1, "action": "create", "set": {field: value}}
    """

    key: str
    kind: str
    title: str
    summary: str
    confidence: str
    slug: str
    account_id: str
    evidence: dict = field(default_factory=dict)
    operations: list[dict] = field(default_factory=list)


@dataclass
class Result:
    """Everything one classification pass produced.

    Attributes:
        scores: Every pair score (the matching trace).
        communities: One report row per website community: which group it
            fell into, why, and which accounts were considered.
        off_website: Report rows for Bellhaven accounts no community matched.
        proposals: The proposed changes.
    """

    scores: list[Score]
    communities: list[dict]
    off_website: list[dict]
    proposals: list[Proposal]


def proposal_key(kind: str, slug: str, account_id: str, operations: list[dict]) -> str:
    """Compute the fingerprint that identifies a proposal across runs.

    It depends only on what would change (kind, target, and the values to be
    written), never on dates, scores or wording. So tomorrow's run produces
    the same key for the same finding, and a different key if the finding
    itself changes (for example the website shows a new name).

    Args:
        kind: Proposal kind.
        slug: Community slug ("" if none).
        account_id: Main account id ("" if none).
        operations: The proposal's operations.

    Returns:
        A 16-character hex fingerprint.
    """
    essence = [kind, slug, account_id, [
        [op["action"], op.get("account_id", ""), sorted(op["set"].items())]
        for op in operations
    ]]
    return hashlib.sha1(json.dumps(essence, sort_keys=True).encode()).hexdigest()[:16]


def needs_chow(account: dict) -> bool:
    """Apply the billing rule: must this account be preserved on an owner change?

    Args:
        account: CRM account about to move to a different owner.

    Returns:
        True if it has revenue history AND outstanding AR above zero. In that
        case the account must be left exactly as it is and a new account
        created instead. False means it may be re-parented directly.
    """
    return (account.get("lifetime_revenue") or 0) > 0 and (account.get("outstanding_ar") or 0) > 0


def _confidence(total: int) -> str:
    """Map a match score to a confidence label for the reviewer."""
    if total >= 85:
        return "high"
    if total >= config.THRESHOLD_MATCH:
        return "medium"
    return "low"


def _account_evidence(account: dict, score: Score | None, role: str) -> dict:
    """Build the evidence block describing one account.

    Args:
        account: CRM account.
        score: Its score against the community, if any.
        role: Why it is shown: "match", "keep", "duplicate", "lookalike",
            "successor", "subject".

    Returns:
        A dict of the account's reviewer-relevant fields plus score details.
    """
    block = {name: account.get(name) for name in EVIDENCE_FIELDS}
    block["role"] = role
    if score is not None:
        block["score"] = score.total
        block["band"] = score.band
        block["score_parts"] = score.parts
        block["score_notes"] = score.notes
    return block


def _update_op(step: int, account: dict, changes: dict) -> dict:
    """Build an update operation, recording the values we expect to replace.

    The "expect" values are checked again just before the change is sent, so
    a proposal can never overwrite something that changed after it was made.

    Args:
        step: Position of this operation within its proposal (1-based).
        account: The account as it is now.
        changes: {field: new value}.

    Returns:
        The operation dict.
    """
    return {
        "step": step,
        "action": "update",
        "account_id": account["account_id"],
        "account_name": account["name"],
        "set": changes,
        "expect": {name: account.get(name) for name in changes},
    }


def _website_fields(location: Location, parent_id: str, note: str) -> dict:
    """Build the fields for a brand-new account from a website community.

    Args:
        location: The website community.
        parent_id: Account id of the parent company (Bellhaven).
        note: Free-text note explaining why the account was created.

    Returns:
        Writable account fields.
    """
    care_types = [config.CARE_TYPE_MAP[o] for o in location.care_offerings if o in config.CARE_TYPE_MAP]
    return {
        "name": location.name,
        "parent_id": parent_id,
        "billing_street": location.street,
        "billing_city": location.city,
        "billing_state": location.state,
        "billing_zip": location.zip,
        "care_type": care_types[0] if care_types else "",
        "status": "Active",
        "phone": location.phone,
        "note": note,
    }


def _detail_changes(location: Location, account: dict) -> dict:
    """Work out which account details disagree with the website.

    Formatting differences ("Ln" vs "Lane") are not differences. Phone
    numbers are never proposed for change: the CRM number may be a billing
    line, so phones are used as evidence only.

    Args:
        location: The website community.
        account: The matched CRM account.

    Returns:
        {field: website value} for each real difference (possibly empty).
    """
    changes: dict[str, str] = {}
    if account.get("name", "").strip() != location.name:
        changes["name"] = location.name
    if norm_street(account.get("billing_street", "")) != norm_street(location.street):
        changes["billing_street"] = location.street
    if account.get("billing_city", "").strip().lower() != location.city.lower():
        changes["billing_city"] = location.city
    if account.get("billing_zip", "") != location.zip:
        changes["billing_zip"] = location.zip
    care_types = [config.CARE_TYPE_MAP[o] for o in location.care_offerings if o in config.CARE_TYPE_MAP]
    if care_types and account.get("care_type") not in care_types:
        changes["care_type"] = care_types[0]
    return changes


def _describe(changes: dict, account: dict) -> str:
    """Render field changes as readable text: name "A" -> "B"; zip ..."""
    labels = {"name": "name", "billing_street": "street", "billing_city": "city",
              "billing_zip": "zip", "care_type": "care type", "parent_id": "owner"}
    return "; ".join(
        f'{labels.get(name, name)} "{account.get(name, "")}" -> "{value}"'
        for name, value in changes.items() if name != "parent_id"
    )


def classify(locations: list[Location], accounts: list[dict], contacts: list[dict]) -> Result:
    """Compare the website with the CRM and propose changes.

    Args:
        locations: Communities scraped from the website.
        accounts: Every CRM account.
        contacts: Every CRM contact.

    Returns:
        A Result holding the scores, per-community report and proposals.

    Raises:
        ValueError: if the Bellhaven parent account cannot be found.
    """
    by_id = {a["account_id"]: a for a in accounts}
    bellhaven = next((a for a in accounts if a["name"] == config.BELLHAVEN_PARENT_NAME), None)
    if bellhaven is None:
        raise ValueError(f"Parent account {config.BELLHAVEN_PARENT_NAME!r} not found in the CRM.")
    bellhaven_id = bellhaven["account_id"]

    # Parent-company accounts are never candidates: they are owners, not facilities.
    parent_ids = {a["parent_id"] for a in accounts if a.get("parent_id")}
    def is_parent(a: dict) -> bool:
        return a["account_id"] in parent_ids or a["name"].endswith("(Parent Account)")

    # Accounts already retired by an earlier decision are history, not
    # candidates: an old account preserved by the billing rule, or a copy
    # already marked as a duplicate. Skipping them is what makes re-runs quiet.
    def is_superseded(a: dict) -> bool:
        return bool(a.get("chow_current_account") or a.get("duplicate_of_account"))

    candidates = [a for a in accounts if not is_parent(a) and not is_superseded(a)]
    contact_count = {aid: len(names) for aid, names in contacts_by_account(contacts).items()}

    scores = score_all(locations, candidates, contacts)
    score_of = {(s.slug, s.account_id): s for s in scores}

    # An account belongs to at most one community: the one it scores highest
    # against (only scores of 50+ count as belonging).
    owner_of: dict[str, Score] = {}
    for s in scores:
        if s.band in (BAND_MATCH, BAND_PROBABLE):
            best = owner_of.get(s.account_id)
            if best is None or s.total > best.total:
                owner_of[s.account_id] = s

    proposals: list[Proposal] = []
    communities: list[dict] = []

    def add(kind: str, title: str, summary: str, confidence: str, slug: str,
            account_id: str, evidence: dict, operations: list[dict]) -> str:
        """Register a proposal and return its key."""
        key = proposal_key(kind, slug, account_id, operations)
        proposals.append(Proposal(key, kind, title, summary, confidence, slug,
                                  account_id, evidence, operations))
        return key

    for location in locations:
        mine = [s for s in owner_of.values() if s.slug == location.slug]
        matches = sorted((s for s in mine if s.band == BAND_MATCH), key=lambda s: -s.total)
        probable = sorted((s for s in mine if s.band == BAND_PROBABLE), key=lambda s: -s.total)
        lookalikes = sorted(
            (s for s in scores if s.slug == location.slug and s.band == BAND_LOOKALIKE),
            key=lambda s: -s.total)
        # Probable matches only stand in when there is no solid match.
        linked = matches or probable[:1]
        if matches:
            lookalikes = probable + lookalikes
        else:
            lookalikes = probable[1:] + lookalikes

        website = asdict(location)
        lookalike_evidence = [_account_evidence(by_id[s.account_id], s, "lookalike") for s in lookalikes]
        row = {
            "slug": location.slug, "name": location.name,
            "city": location.city, "state": location.state,
            "groups": [], "reason": "", "account_id": "", "score": None,
            "proposal_keys": [],
            "candidates": [
                {"account_id": s.account_id, "name": by_id[s.account_id]["name"],
                 "parent_name": by_id[s.account_id].get("parent_name", ""),
                 "score": s.total, "band": s.band, "parts": s.parts}
                for s in linked + lookalikes
            ],
        }

        # ---- No account at all: propose creating one ----------------------
        if not linked:
            note = f"Created by Bellhaven ownership sync from website listing {location.url}."
            ops = [{"step": 1, "action": "create", "set": _website_fields(location, bellhaven_id, note)}]
            seen = ", ".join(f'"{e["name"]}" ({e["billing_city"]}, score {e["score"]})' for e in lookalike_evidence)
            row["groups"].append("new_account")
            row["reason"] = ("No CRM account scores 50 or more for this community."
                             + (f" Lookalikes considered and left alone: {seen}." if seen else ""))
            row["proposal_keys"].append(add(
                KIND_CREATE, f"Create account: {location.name}",
                f"{location.name} ({location.city}, {location.state}) is on the website but has no "
                f"CRM account. Create one under Bellhaven." + (f" Lookalikes left alone: {seen}." if seen else ""),
                "medium" if lookalike_evidence else "high", location.slug, "",
                {"website": website, "accounts": lookalike_evidence,
                 "reasons": ["No account in the same state scores 50 or more."]},
                ops))
            communities.append(row)
            continue

        # ---- Choose which account to keep ---------------------------------
        # Preference order: already under Bellhaven, has billing history, has
        # contacts, has any owner, highest score; account id breaks ties so
        # the choice is the same on every run.
        def keep_rank(s: Score):
            a = by_id[s.account_id]
            return (
                a.get("parent_id") != bellhaven_id,
                not (a.get("lifetime_revenue") or 0) > 0,
                -contact_count.get(a["account_id"], 0),
                not a.get("parent_id"),
                -s.total,
                a["account_id"],
            )
        linked = sorted(linked, key=keep_rank)
        keep_score = linked[0]
        keep = by_id[keep_score.account_id]
        row["account_id"] = keep["account_id"]
        row["score"] = keep_score.total
        confidence = _confidence(keep_score.total)

        changes = _detail_changes(location, keep)
        wrong_owner = keep.get("parent_id") != bellhaven_id
        keep_evidence = _account_evidence(keep, keep_score, "match")
        billing = {"lifetime_revenue": keep.get("lifetime_revenue"),
                   "outstanding_ar": keep.get("outstanding_ar")}
        owner_now = keep.get("parent_name") or "no owner"

        if wrong_owner and needs_chow(keep):
            # ---- Billing rule: preserve the old account -------------------
            note = (f"Created by Bellhaven ownership sync. Change of ownership from account "
                    f"{keep['account_id']} ({owner_now}), which is preserved for billing.")
            ops = [
                {"step": 1, "action": "create", "set": _website_fields(location, bellhaven_id, note)},
                _update_op(2, keep, {"chow_current_account": NEW_ACCOUNT_REF}),
            ]
            row["groups"].append("needs_fix")
            row["reason"] = (f'Matched "{keep["name"]}" (score {keep_score.total}) under {owner_now}. '
                             f"It has revenue {keep['lifetime_revenue']:,} and outstanding AR "
                             f"{keep['outstanding_ar']:,}, so the billing rule applies.")
            row["proposal_keys"].append(add(
                KIND_CHOW, f"Change of ownership: {location.name}",
                f'"{keep["name"]}" is listed under {owner_now} but is now a Bellhaven community. '
                f"It has revenue history ({keep['lifetime_revenue']:,}) and money still owed "
                f"({keep['outstanding_ar']:,}), so the old account is left untouched. A new account "
                f"is created under Bellhaven and the old one is pointed at it.",
                confidence, location.slug, keep["account_id"],
                {"website": website, "accounts": [keep_evidence] + lookalike_evidence,
                 "billing": billing,
                 "sop": "Revenue history AND outstanding AR above zero: preserve the old account, "
                        "create a new one, set chow_current_account on the old one.",
                 "reasons": [f"Same facility (score {keep_score.total}).",
                             f"Owner in CRM is {owner_now}, not Bellhaven."]},
                ops))
        elif wrong_owner:
            # ---- Safe to move directly ------------------------------------
            set_fields = {"parent_id": bellhaven_id, **changes}
            why_safe = ("no revenue history" if not (keep.get("lifetime_revenue") or 0) > 0
                        else "revenue history but nothing owed")
            extra = _describe(changes, keep)
            row["groups"].append("needs_fix")
            row["reason"] = (f'Matched "{keep["name"]}" (score {keep_score.total}) under {owner_now}; '
                             f"{why_safe}, so it can be moved directly.")
            row["proposal_keys"].append(add(
                KIND_REPARENT, f"Move under Bellhaven: {location.name}",
                f'"{keep["name"]}" is listed under {owner_now} but is now a Bellhaven community. '
                f"It has {why_safe}, so the existing account is moved under Bellhaven directly."
                + (f" Also: {extra}." if extra else ""),
                confidence, location.slug, keep["account_id"],
                {"website": website, "accounts": [keep_evidence] + lookalike_evidence,
                 "billing": billing,
                 "sop": f"Billing rule checked: {why_safe}, so re-parent the existing account directly.",
                 "reasons": [f"Same facility (score {keep_score.total}).",
                             f"Owner in CRM is {owner_now}, not Bellhaven."]},
                [_update_op(1, keep, set_fields)]))
        elif changes:
            # ---- Right owner, details differ ------------------------------
            only_street = set(changes) == {"billing_street"}
            kind = KIND_ADDRESS if only_street else KIND_UPDATE
            label = KIND_LABELS[kind]
            text = _describe(changes, keep)
            caution = ""
            if "billing_street" in changes and keep.get("billing_street", "").upper().startswith("PO BOX"):
                caution = (" The CRM holds a PO Box, which can be a valid billing address; "
                           "consider rejecting if billing mail goes there.")
            row["groups"].append("needs_fix")
            row["reason"] = f'Matched "{keep["name"]}" (score {keep_score.total}); differs: {text}.'
            row["proposal_keys"].append(add(
                kind, f"{label}: {location.name}",
                f"The CRM account matches this community but differs from the website: {text}.{caution}",
                "low" if (only_street or keep_score.band == BAND_PROBABLE) else confidence,
                location.slug, keep["account_id"],
                {"website": website, "accounts": [keep_evidence] + lookalike_evidence,
                 "reasons": [f"Same facility (score {keep_score.total}).",
                             "Owner is already Bellhaven."]},
                [_update_op(1, keep, changes)]))
        else:
            row["groups"].append("confident_match")
            row["reason"] = (f'Matched "{keep["name"]}" (score {keep_score.total}), already under '
                             f"Bellhaven with matching details.")

        # ---- Extra copies are duplicates ----------------------------------
        for dup_score in linked[1:]:
            dup = by_id[dup_score.account_id]
            note = f"Duplicate of account {keep['account_id']} ({location.name})."
            if dup.get("note"):
                note = f"{dup['note']} | {note}"
            set_fields = {"status": "Inactive", "duplicate_of_account": keep["account_id"], "note": note}
            keep_why = ("it is already under Bellhaven" if keep.get("parent_id") == bellhaven_id
                        else "no copy is under Bellhaven, so the tie-break rule chose it "
                             "(billing history, then contacts, then having an owner, then score)")
            row["groups"].append("duplicates")
            row["proposal_keys"].append(add(
                KIND_DUPLICATE, f'Mark duplicate: {dup["name"]}',
                f'"{dup["name"]}" ({dup.get("parent_name") or "no owner"}) is at the same address as '
                f'"{keep["name"]}" and is the same facility as {location.name}. Keep '
                f'"{keep["name"]}" because {keep_why}. Mark this copy Inactive and point it at the kept account.',
                "high" if keep.get("parent_id") == bellhaven_id else "medium",
                location.slug, dup["account_id"],
                {"website": website,
                 "accounts": [_account_evidence(dup, dup_score, "duplicate"),
                              _account_evidence(keep, keep_score, "keep")]
                             + [_account_evidence(by_id[s.account_id], s, "duplicate")
                                for s in linked[1:] if s.account_id != dup["account_id"]],
                 "reasons": [f"Same facility as the kept account (score {dup_score.total}).",
                             f"Kept account chosen because {keep_why}."]},
                [_update_op(1, dup, set_fields)]))
        if len(linked) > 1 and "duplicates" in row["groups"]:
            row["reason"] += f" {len(linked) - 1} duplicate cop{'y' if len(linked) == 2 else 'ies'} found."
        communities.append(row)

    # ---- Bellhaven accounts that no community claimed ---------------------
    off_website: list[dict] = []
    for account in candidates:
        if account.get("parent_id") != bellhaven_id or account["account_id"] in owner_of:
            continue
        # Is there another account at the very same address under a different owner?
        successor = next((
            other for other in candidates
            if other["account_id"] != account["account_id"]
            and other.get("parent_id") != bellhaven_id
            and other["account_id"] not in owner_of
            and other.get("billing_state") == account.get("billing_state")
            and other.get("billing_zip") == account.get("billing_zip")
            and norm_street(other.get("billing_street", "")) == norm_street(account.get("billing_street", ""))
            and norm_street(account.get("billing_street", ""))
        ), None)
        subject = _account_evidence(account, None, "subject")
        billing = {"lifetime_revenue": account.get("lifetime_revenue"),
                   "outstanding_ar": account.get("outstanding_ar")}
        report = {"account_id": account["account_id"], "name": account["name"],
                  "group": "", "reason": "", "proposal_keys": []}

        if successor is not None and needs_chow(account):
            new_owner = successor.get("parent_name") or "another owner"
            report["group"] = "sold"
            report["reason"] = (f'Not on the website. "{successor["name"]}" ({new_owner}) is at the '
                                f"same address. Billing rule applies, so only the pointer is set.")
            report["proposal_keys"].append(add(
                KIND_CHOW_LINK, f'Sold to another owner: {account["name"]}',
                f'"{account["name"]}" is under Bellhaven but no longer on the Bellhaven website. '
                f'"{successor["name"]}" under {new_owner} is at the same address, so the facility '
                f"appears to have changed hands. This account has revenue history "
                f"({account['lifetime_revenue']:,}) and money still owed ({account['outstanding_ar']:,}), "
                f"so it is left as it is and pointed at the new owner's account.",
                "medium", "", account["account_id"],
                {"accounts": [subject, _account_evidence(successor, None, "successor")],
                 "billing": billing,
                 "sop": "Revenue history AND outstanding AR above zero: do not re-parent. The new "
                        "owner's account already exists, so only chow_current_account is set.",
                 "reasons": ["No website community matches this account.",
                             "Another owner's account exists at the same address."]},
                [_update_op(1, account, {"chow_current_account": successor["account_id"]})]))
        elif successor is not None:
            new_owner = successor.get("parent_name") or "another owner"
            note = f"Duplicate of account {successor['account_id']} ({successor['name']}); facility no longer listed by Bellhaven."
            report["group"] = "sold"
            report["reason"] = (f'Not on the website. "{successor["name"]}" ({new_owner}) is at the '
                                f"same address; nothing owed, so this copy is retired as a duplicate.")
            report["proposal_keys"].append(add(
                KIND_DUPLICATE, f'Mark duplicate: {account["name"]}',
                f'"{account["name"]}" is under Bellhaven but no longer on the Bellhaven website, and '
                f'"{successor["name"]}" under {new_owner} is at the same address. Nothing is owed on '
                f"this account, so moving it would only create a second copy. Mark it Inactive and "
                f"point it at the new owner's account.",
                "medium", "", account["account_id"],
                {"accounts": [subject, _account_evidence(successor, None, "keep")],
                 "billing": billing,
                 "reasons": ["No website community matches this account.",
                             "Another owner's account exists at the same address."]},
                [_update_op(1, account, {"status": "Inactive",
                                         "duplicate_of_account": successor["account_id"],
                                         "note": note})]))
        elif account.get("status") == "Active":
            note = ("No longer listed on the Bellhaven website (found by the daily ownership sync). "
                    "Ownership needs confirming: may have been sold or closed.")
            if account.get("note"):
                note = f"{account['note']} | {note}"
            report["group"] = "off_website"
            report["reason"] = "Under Bellhaven in the CRM but not on the website; no successor account found."
            report["proposal_keys"].append(add(
                KIND_OFF_WEBSITE, f'No longer on website: {account["name"]}',
                f'"{account["name"]}" sits under Bellhaven in the CRM but is not on the Bellhaven '
                f"website, and no other owner's account exists at its address. We cannot tell whether "
                f"it was sold or closed, so flag it for a person to confirm rather than guess.",
                "medium", "", account["account_id"],
                {"accounts": [subject], "billing": billing,
                 "reasons": ["No website community scores 50 or more against this account.",
                             "No other account shares its address."]},
                [_update_op(1, account, {"status": "Needs Review", "note": note})]))
        else:
            report["group"] = "off_website_already_flagged"
            report["reason"] = f"Not on the website; already marked {account.get('status')}, nothing to do."
        off_website.append(report)

    return Result(scores, communities, off_website, proposals)


def planned_requests(proposal: Proposal) -> list[dict]:
    """List the exact CRM requests a proposal would send, without sending them.

    Used for the dry run, so a person can check every request before any is
    made for real.

    Args:
        proposal: The proposal to describe.

    Returns:
        One dict per request: {"method", "path", "body"}.
    """
    requests_out = []
    for op in proposal.operations:
        if op["action"] == "create":
            requests_out.append({"method": "POST", "path": "/accounts", "body": op["set"]})
        else:
            requests_out.append({"method": "PATCH", "path": f"/accounts/{op['account_id']}",
                                 "body": op["set"]})
    return requests_out
