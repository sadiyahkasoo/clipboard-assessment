"""
The review app: a small local website where a person approves or rejects
each proposed CRM change.

One running app serves two modes, and the mode is part of every page address:

    /rehearsal/...    a local copy of the CRM. Safe to practise on. Also
                      holds the Smoke test page (tests, rehearsal, dry run).
    /production/...   the real CRM. Approvals here make real changes.

Putting the mode in the address (rather than remembering it in the
background) means a page can never act in the wrong mode: an Approve button
on a /rehearsal/ page can only ever post to /rehearsal/, even if another tab
has since switched to production. Each mode has its own CRM connection, its
own audit trail and its own proposal queue; they share nothing.

Pages (under either mode):
    /                   review queue (proposals grouped by kind)
    /proposal/<id>      one proposal: what would change, the evidence, and
                        the Approve / Reject buttons
    /communities        every website community and how it was classified
    /audit              the audit trail of decisions and CRM changes
    /smoke              (rehearsal only) smoke test and dry run

Rules the app enforces:
    * A change is sent to the CRM only from the Approve button, and only
      through apply.apply_proposal, which itself demands an approving review.
    * Every decision and every CRM request is written to the audit trail.
    * A banner on every page says which mode it is in.

Start it with:
    PYTHONPATH=src python -m bellhaven_sync.review_app
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from flask import (Blueprint, Flask, abort, flash, g, redirect, render_template,
                   request, url_for)

from .. import apply as apply_step
from .. import audit_db, classify, config
from ..normalize import norm_phone, norm_street

# Friendly names for CRM fields, used wherever a field is shown to a person.
FIELD_LABELS: dict[str, str] = {
    "name": "Name", "parent_id": "Owner (parent company)", "billing_street": "Street",
    "billing_city": "City", "billing_state": "State", "billing_zip": "Zip",
    "care_type": "Care type", "status": "Status", "phone": "Phone", "note": "Note",
    "chow_current_account": "CHOW pointer (current account)",
    "duplicate_of_account": "Duplicate of",
    "lifetime_revenue": "Lifetime revenue", "outstanding_ar": "Outstanding AR",
}

# Fields whose value is another account's id; shown with that account's name.
POINTER_FIELDS = ("parent_id", "chow_current_account", "duplicate_of_account")

# Queue tabs: tab name -> proposal states it shows.
TABS: dict[str, tuple[str, ...]] = {
    "pending": (audit_db.STATE_PENDING,),
    "approved": (audit_db.STATE_APPLIED, audit_db.STATE_APPROVED, audit_db.STATE_FAILED),
    "rejected": (audit_db.STATE_REJECTED,),
    "all": (),
}

# Word used in page addresses and on screen -> internal mode name.
# People say "production"; the code and data files call the same thing "live".
MODE_OF_SLUG: dict[str, str] = {"rehearsal": config.MODE_REHEARSAL, "production": config.MODE_LIVE}
SLUG_OF_MODE: dict[str, str] = {mode: slug for slug, mode in MODE_OF_SLUG.items()}


@dataclass
class ModeContext:
    """Everything one mode needs: its CRM, its audit trail and its export file.

    Attributes:
        mode: Internal mode name ("rehearsal" or "live").
        client: CRM client (LocalCrm for rehearsal, CrmClient for production).
        db: That mode's audit trail.
        export_csv: Where the readable audit export is written.
        reviewer: Name recorded against decisions made in this mode.
        names: Cache of account id -> name, so id fields can be shown readably.
        managed: True when the app created this context itself from the
            standard files (so it may rebuild it); False when a test supplied it.
    """

    mode: str
    client: object
    db: audit_db.AuditDb
    export_csv: Path
    reviewer: str = ""
    names: dict[str, str] = field(default_factory=dict)
    managed: bool = True

    def refresh_names(self) -> None:
        """Reload the id -> name lookup from the CRM (a read-only call)."""
        self.names = {a["account_id"]: a["name"] for a in self.client.list_accounts()}


def create_app(default_mode: str = config.MODE_REHEARSAL, contexts: dict | None = None,
               allow_production: bool = True, dry_run_db: Path | None = None) -> Flask:
    """Build the review app.

    Args:
        default_mode: Mode the bare address "/" opens ("rehearsal" or "live").
        contexts: Optional ready-made contexts, used by tests:
            {mode: {"client": ..., "db": ..., "export_csv": ...}}.
            Modes not listed are built from the standard files on first use.
        allow_production: If False, the production mode is switched off
            entirely for this run of the app (a guard for practice sessions).
        dry_run_db: Audit database whose waiting proposals are listed as the
            dry run on the Smoke test page. Defaults to the production one.

    Returns:
        The configured Flask application.
    """
    from .. import pipeline, rehearsal   # imported here to avoid circular imports

    app = Flask(__name__)
    app.secret_key = secrets.token_hex(16)   # only signs the one-line flash messages
    dry_run_db = dry_run_db or config.paths_for(config.MODE_LIVE).audit_db

    supplied = contexts or {}
    cache: dict[str, ModeContext] = {}
    # Result of the last "Run automated tests" click on the Smoke test page.
    test_run: dict = {}

    def context_for(mode: str) -> ModeContext:
        """Return the context for a mode, building it the first time it is needed.

        Production is only connected to when someone actually opens a
        production page, so a rehearsal-only session never touches the real CRM.

        Args:
            mode: Internal mode name.

        Returns:
            The mode's context.
        """
        if mode in cache:
            return cache[mode]
        if mode in supplied:
            given = supplied[mode]
            ctx = ModeContext(mode, given["client"], given["db"], given["export_csv"], managed=False)
        else:
            paths = config.paths_for(mode)
            if mode == config.MODE_REHEARSAL and not paths.local_crm.exists():
                rehearsal.reset()          # first use: build the local copy from the backup
            ctx = ModeContext(mode, pipeline.get_client(mode), audit_db.AuditDb(paths.audit_db),
                              paths.export_csv)
        ctx.reviewer = ctx.client.me().get("candidate", "")
        ctx.refresh_names()
        cache[mode] = ctx
        return ctx

    # ---------------------------------------------------------------- helpers

    def show(field_name: str, value) -> str:
        """Render a field value for people: ids become "Name (id)", blanks "(empty)"."""
        if value in (None, ""):
            return "(empty)"
        if value == classify.NEW_ACCOUNT_REF:
            return "the new account created in step 1"
        if field_name in POINTER_FIELDS:
            return f"{g.ctx.names.get(value, 'unknown account')} ({value})"
        if field_name in ("lifetime_revenue", "outstanding_ar"):
            return f"{value:,}"
        return str(value)

    def differs(field_name: str, crm_value, website_value) -> bool:
        """Tell whether a CRM value really differs from the website value.

        Uses the same tidying as the matcher, so "Dr" vs "Drive" is not
        flagged. Names are compared as typed apart from capital letters,
        because the tool does propose fixing small name differences.

        Args:
            field_name: CRM field name.
            crm_value: Value held in the CRM.
            website_value: Value shown on the website.

        Returns:
            True if the cell should be highlighted as different.
        """
        crm_value, website_value = crm_value or "", website_value or ""
        if field_name == "billing_street":
            return norm_street(crm_value) != norm_street(website_value)
        if field_name == "phone":
            return norm_phone(crm_value) != norm_phone(website_value)
        return crm_value.strip().lower() != website_value.strip().lower()

    def as_proposal(item: dict) -> classify.Proposal:
        """Turn a stored proposal row back into a classify.Proposal."""
        return classify.Proposal(item["key"], item["kind"], item["title"], item["summary"],
                                 item["confidence"], item["location_slug"], item["account_id"],
                                 item["evidence"], item["operations"])

    # ------------------------------------------------------- mode in the URL

    bp = Blueprint("review", __name__, url_prefix="/<mode_slug>")

    @bp.url_value_preprocessor
    def read_mode(_endpoint, values) -> None:
        """Take the mode word out of the address and remember it for this request."""
        g.mode_slug = values.pop("mode_slug")

    @bp.url_defaults
    def keep_mode(_endpoint, values) -> None:
        """Make every link built on a page stay in that page's mode."""
        if "mode_slug" not in values and "mode_slug" in g:
            values["mode_slug"] = g.mode_slug

    @bp.before_request
    def load_context():
        """Check the mode in the address and connect to that mode's CRM and audit trail."""
        if g.mode_slug not in MODE_OF_SLUG:
            abort(404)
        mode = MODE_OF_SLUG[g.mode_slug]
        if mode == config.MODE_LIVE and not allow_production:
            flash("Production mode is switched off for this session (started with --rehearsal-only).", "warning")
            return redirect(url_for("review.queue", mode_slug="rehearsal"))
        try:
            g.ctx = context_for(mode)
        except Exception as exc:   # e.g. no token, or the CRM cannot be reached
            if mode == config.MODE_LIVE:
                flash(f"Could not connect to the real CRM: {exc}", "danger")
                return redirect(url_for("review.queue", mode_slug="rehearsal"))
            raise
        return None

    @bp.context_processor
    def inject_globals() -> dict:
        """Make the mode, counts and helpers available to every template."""
        counts = g.ctx.db.state_counts()
        return {
            "mode": g.ctx.mode,
            "mode_slug": g.mode_slug,
            "allow_production": allow_production,
            "reviewer": g.ctx.reviewer,
            "counts": {
                "pending": counts.get(audit_db.STATE_PENDING, 0),
                "approved": sum(counts.get(s, 0) for s in TABS["approved"]),
                "rejected": counts.get(audit_db.STATE_REJECTED, 0),
                "failed": counts.get(audit_db.STATE_FAILED, 0),
            },
            "kind_labels": classify.KIND_LABELS,
            "field_label": lambda f: FIELD_LABELS.get(f, f),
            "show": show,
            "differs": differs,
            "pretty": lambda obj: json.dumps(obj, indent=2),
            "compact": lambda obj: json.dumps(obj, ensure_ascii=False),
        }

    @app.get("/")
    def home():
        """The bare address opens the default mode's review queue."""
        return redirect(url_for("review.queue", mode_slug=SLUG_OF_MODE[default_mode]))

    # ------------------------------------------------------------ main pages

    @bp.get("/")
    def queue():
        """Review queue: proposals for the chosen tab, grouped by kind."""
        tab = request.args.get("tab", "pending")
        if tab not in TABS:
            abort(404)
        db = g.ctx.db
        proposals = [p for p in db.list_proposals()
                     if (not TABS[tab] or p["state"] in TABS[tab])
                     and (tab != "all" or p["state"] != audit_db.STATE_WITHDRAWN)]
        groups: dict[str, list[dict]] = {}
        for kind in classify.KIND_LABELS:       # fixed, sensible display order
            members = [p for p in proposals if p["kind"] == kind]
            if members:
                groups[kind] = members
        runs = db.list_runs()
        return render_template("queue.html", tab=tab, groups=groups, total=len(proposals),
                               last_run=dict(runs[0]) if runs else None)

    @bp.get("/proposal/<int:proposal_id>")
    def proposal(proposal_id: int):
        """One proposal with its evidence, decision form and change history."""
        db = g.ctx.db
        item = db.get_proposal(proposal_id)
        if item is None:
            abort(404)
        return render_template(
            "proposal.html", p=item, review=db.review_for(proposal_id),
            changes=db.changes_for(proposal_id),
            requests=classify.planned_requests(as_proposal(item)),
            site_base=config.SITE_BASE)

    def _apply(proposal_id: int) -> None:
        """Send an approved proposal to this mode's CRM and report the outcome on screen."""
        ctx = g.ctx
        where = "the real CRM" if ctx.mode == config.MODE_LIVE else "the rehearsal copy"
        try:
            done = apply_step.apply_proposal(ctx.db, ctx.client, proposal_id)
            flash(f"Approved and written to {where}: {done}", "success")
        except apply_step.ApplyError as exc:
            flash(f"Approved, but the change to {where} failed: {exc}", "danger")
        ctx.refresh_names()
        ctx.db.export_csv(ctx.export_csv)

    @bp.post("/proposal/<int:proposal_id>/approve")
    def approve(proposal_id: int):
        """Record an approval, then write the change to this mode's CRM."""
        ctx = g.ctx
        try:
            ctx.db.add_review(proposal_id, "approved", request.form.get("reason", ""), ctx.reviewer, ctx.mode)
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("review.proposal", proposal_id=proposal_id))
        _apply(proposal_id)
        return redirect(url_for("review.proposal", proposal_id=proposal_id))

    @bp.post("/proposal/<int:proposal_id>/reject")
    def reject(proposal_id: int):
        """Record a rejection. Nothing is sent to the CRM."""
        ctx = g.ctx
        try:
            ctx.db.add_review(proposal_id, "rejected", request.form.get("reason", ""), ctx.reviewer, ctx.mode)
            flash("Rejected. Nothing was sent to the CRM, and this will not be proposed again.", "secondary")
        except ValueError as exc:
            flash(str(exc), "warning")
        ctx.db.export_csv(ctx.export_csv)
        return redirect(url_for("review.proposal", proposal_id=proposal_id))

    @bp.post("/proposal/<int:proposal_id>/retry")
    def retry(proposal_id: int):
        """Retry a failed, already-approved proposal. Finished steps are not repeated."""
        _apply(proposal_id)
        return redirect(url_for("review.proposal", proposal_id=proposal_id))

    @bp.get("/communities")
    def communities():
        """Every website community from the latest run and how it was classified."""
        db = g.ctx.db
        rows, off, run = [], [], None
        for candidate in db.list_runs():
            folder = Path(candidate["run_dir"] or "")
            if candidate["status"] == "ok" and (folder / "03_matching" / "communities.json").exists():
                run = dict(candidate)
                rows = json.loads((folder / "03_matching" / "communities.json").read_text())
                off = json.loads((folder / "03_matching" / "off_website.json").read_text())
                break
        by_key = {p["key"]: p for p in db.list_proposals()}
        return render_template("communities.html", rows=rows, off=off, run=run, by_key=by_key)

    @bp.get("/audit")
    def audit():
        """The audit trail: every decision and every CRM request, newest first."""
        return render_template("audit.html", events=g.ctx.db.history(),
                               runs=[dict(r) for r in g.ctx.db.list_runs()],
                               export_path=str(g.ctx.export_csv))

    # ------------------------------------------- smoke test (rehearsal only)

    def _rehearsal_only():
        """Send production visitors to the rehearsal Smoke test page instead."""
        if g.ctx.mode != config.MODE_REHEARSAL:
            return redirect(url_for("review.smoke", mode_slug="rehearsal"))
        return None

    def _dry_run() -> dict:
        """Read the dry run: the requests production WOULD send, without sending.

        This only opens the production audit database file. It makes no
        network call and does not connect to the real CRM.

        Returns:
            {"available": bool, "run": last run row or None,
             "items": [{"proposal": ..., "requests": [...]}], "request_count": int}
        """
        if not Path(dry_run_db).exists():
            return {"available": False, "run": None, "items": [], "request_count": 0}
        source = audit_db.AuditDb(dry_run_db)
        runs = source.list_runs()
        items = [{"proposal": p, "requests": classify.planned_requests(as_proposal(p))}
                 for p in source.list_proposals(audit_db.STATE_PENDING)]
        decided = sum(n for state, n in source.state_counts().items()
                      if state not in (audit_db.STATE_PENDING, audit_db.STATE_WITHDRAWN))
        source.conn.close()
        return {"available": bool(runs), "run": dict(runs[0]) if runs else None, "items": items,
                "request_count": sum(len(i["requests"]) for i in items), "decided": decided}

    @bp.get("/smoke")
    def smoke():
        """Smoke test page: automated tests, the rehearsal, and the dry run."""
        moved = _rehearsal_only()
        if moved:
            return moved
        return render_template("smoke.html", test_run=test_run, dry=_dry_run(),
                               history_count=len(g.ctx.db.history()), managed=g.ctx.managed)

    @bp.post("/smoke/tests")
    def smoke_tests():
        """Run the automated tests (offline, saved data only) and show the result."""
        moved = _rehearsal_only()
        if moved:
            return moved
        env = {**os.environ, "PYTHONPATH": str(config.ROOT / "src")}
        try:
            done = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
                                  cwd=config.ROOT, env=env, capture_output=True, text=True, timeout=180)
            lines = (done.stdout + done.stderr).strip().splitlines()
            test_run.update(ok=done.returncode == 0, summary=lines[-1] if lines else "no output",
                            output="\n".join(lines[-25:]))
        except subprocess.TimeoutExpired:
            test_run.update(ok=False, summary="Tests did not finish within 3 minutes.", output="")
        test_run["when"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        flash(f"Automated tests: {test_run['summary']}", "success" if test_run["ok"] else "danger")
        return redirect(url_for("review.smoke"))

    @bp.post("/smoke/reset")
    def smoke_reset():
        """Wipe the rehearsal, rebuild the local CRM from the backup, and refill the queue."""
        moved = _rehearsal_only()
        if moved:
            return moved
        if not g.ctx.managed:
            abort(400)
        g.ctx.db.conn.close()
        cache.pop(config.MODE_REHEARSAL, None)
        rehearsal.reset()
        try:
            summary = pipeline.run(config.MODE_REHEARSAL)
            flash("Rehearsal reset. Local CRM rebuilt from the backup and the queue refilled: "
                  f"{summary.get('proposals', {}).get('new', 0)} proposals waiting.", "success")
        except Exception as exc:
            flash(f"Rehearsal reset, but refilling the queue failed: {exc}", "danger")
        return redirect(url_for("review.smoke"))

    @bp.post("/smoke/dry-run")
    def smoke_dry_run():
        """Refresh the dry run: read the website and the real CRM, write nothing."""
        moved = _rehearsal_only()
        if moved:
            return moved
        if not allow_production:
            flash("The dry run reads the real CRM, which is switched off for this session.", "warning")
            return redirect(url_for("review.smoke"))
        try:
            summary = pipeline.run(config.MODE_LIVE)
            counts = summary.get("proposals", {})
            flash("Dry run refreshed (read-only; nothing was sent). "
                  f"{counts.get('total', 0)} proposals found, {counts.get('new', 0)} new, "
                  f"{counts.get('suppressed', 0)} already decided.", "success")
        except Exception as exc:
            flash(f"Dry run failed: {exc}", "danger")
        return redirect(url_for("review.smoke"))

    app.register_blueprint(bp)
    return app
