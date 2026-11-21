"""
Step 4: send an APPROVED proposal to the CRM, safely.

This is the only module that changes the CRM, and it can only be reached
through an approval: `apply_proposal` needs the id of an approving review and
refuses to run without one.

For every operation in a proposal it:
    1. skips it if the audit trail shows it already succeeded (safe retries -
       an account is never created twice);
    2. for an update, re-reads the account and checks the values it is about
       to replace are still what the proposal saw (no overwriting something
       that changed in the meantime);
    3. sends the request;
    4. reads the account back and confirms the new values landed;
    5. records all of it in the audit trail - request, before, after, reply.

If any operation fails, it stops, marks the proposal "failed" and leaves the
remaining operations unsent. The reviewer can retry; finished steps are not
repeated.
"""

from __future__ import annotations

from . import audit_db
from .classify import NEW_ACCOUNT_REF
from .crm_client import CrmError


class ApplyError(RuntimeError):
    """An approved proposal could not be (fully) applied."""


def _find_existing_created(client, fields: dict) -> dict | None:
    """Look for an account this tool already created with these details.

    Guards against a lost reply: if a create request reached the CRM but we
    never saw the answer, a retry must adopt that account rather than create
    a second one (accounts cannot be deleted).

    Args:
        client: CRM client (real or local).
        fields: The fields the create would send.

    Returns:
        The existing account, or None.
    """
    for account in client.list_accounts(parent_id=fields.get("parent_id", "")):
        if (account.get("created_by_candidate")
                and account.get("name") == fields.get("name")
                and account.get("billing_zip") == fields.get("billing_zip")
                and account.get("parent_id") == fields.get("parent_id")
                and not account.get("duplicate_of_account")):
            return account
    return None


def apply_proposal(db: audit_db.AuditDb, client, proposal_id: int) -> str:
    """Send an approved proposal's operations to the CRM and verify them.

    Args:
        db: The audit trail.
        client: CRM client to write to (CrmClient for live, LocalCrm for
            rehearsal). Its `mode` attribute is recorded with every change.
        proposal_id: The proposal to apply.

    Returns:
        A short human-readable description of what was done.

    Raises:
        ApplyError: if the proposal has no approving review, is in the wrong
            state, or an operation fails. On failure the proposal is marked
            "failed" and the failed request is recorded in the audit trail.
    """
    proposal = db.get_proposal(proposal_id)
    if proposal is None:
        raise ApplyError(f"No proposal {proposal_id}")
    review = db.review_for(proposal_id)
    # The central safety rule: nothing is written without an approval.
    if review is None or review["decision"] != "approved":
        raise ApplyError(f"Proposal {proposal_id} has not been approved; nothing was sent.")
    if proposal["state"] not in (audit_db.STATE_APPROVED, audit_db.STATE_FAILED):
        raise ApplyError(f"Proposal {proposal_id} is {proposal['state']}; nothing to apply.")

    new_account_id: str | None = None   # id produced by this proposal's create step
    done: list[str] = []

    for op in proposal["operations"]:
        step = op["step"]

        # 1. Already done on an earlier attempt? Reuse its result and move on.
        earlier = db.successful_change(proposal_id, step)
        if earlier is not None:
            if op["action"] == "create":
                new_account_id = earlier["account_id"]
            done.append(f"step {step} already applied")
            continue

        # Fill in the placeholder for "the account created earlier in this proposal".
        fields = dict(op["set"])
        for name, value in fields.items():
            if value == NEW_ACCOUNT_REF:
                if not new_account_id:
                    raise ApplyError("Operation refers to a new account that was not created.")
                fields[name] = new_account_id

        method = "POST" if op["action"] == "create" else "PATCH"
        path = "/accounts" if op["action"] == "create" else f"/accounts/{op['account_id']}"
        before: dict | None = None
        after: dict | None = None
        response: object = None
        account_id = op.get("account_id", "")

        try:
            if op["action"] == "create":
                existing = _find_existing_created(client, fields)
                if existing is not None:
                    # A previous attempt created it but the reply was lost.
                    response = {"adopted_existing_account": existing["account_id"]}
                    account_id = existing["account_id"]
                else:
                    response = client.create_account(fields)
                    account_id = response["account_id"]
                new_account_id = account_id
            else:
                # 2. Staleness check against the values the proposal saw.
                before = client.get_account(account_id)
                stale = {name: (expected, before.get(name))
                         for name, expected in op.get("expect", {}).items()
                         if before.get(name) != expected}
                if stale:
                    raise ApplyError(
                        "The account changed since this proposal was made "
                        f"(expected vs now: {stale}). Re-run the pipeline for a fresh proposal.")
                response = client.update_account(account_id, fields)

            # 4. Read back and confirm every intended value landed.
            after = client.get_account(account_id)
            wrong = {name: after.get(name) for name, value in fields.items() if after.get(name) != value}
            if wrong:
                raise ApplyError(f"CRM accepted the request but read-back differs: {wrong}")
        except (CrmError, ApplyError, KeyError) as exc:
            status = str(getattr(exc, "status", "") or type(exc).__name__)
            db.add_change(
                review_id=review["id"], proposal_id=proposal_id, step=step, method=method, path=path,
                account_id=account_id, request=fields, before=before, after=after,
                response_status=status, response=getattr(exc, "body", None) or response,
                success=False, verified=False, error=str(exc), mode=client.mode)
            db.set_state(proposal_id, audit_db.STATE_FAILED)
            raise ApplyError(f"Step {step} ({method} {path}) failed: {exc}") from exc

        # 5. Record the successful, verified change.
        db.add_change(
            review_id=review["id"], proposal_id=proposal_id, step=step, method=method, path=path,
            account_id=account_id, request=fields, before=before, after=after,
            response_status="ok", response=response, success=True, verified=True,
            error="", mode=client.mode)
        done.append(f"{method} {path if method == 'PATCH' else '/accounts -> ' + account_id}")

    db.set_state(proposal_id, audit_db.STATE_APPLIED)
    return "; ".join(done)
