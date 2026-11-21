"""
The audit trail: a local SQLite database recording what was proposed, what a
reviewer decided, and exactly what was changed in the CRM as a result.

Four tables:

    runs         one row per pipeline run (daily job)
    proposals    one row per proposed change, with its current state
    reviews      one row per approve / reject decision      (append-only)
    crm_changes  one row per request sent to the CRM        (append-only)

"Append-only" is enforced by the database itself: triggers reject any
attempt to edit or delete a review or a CRM change. So the history of who
decided what, and what was sent, cannot be rewritten by a bug or by hand.
(A proposal's `state` column does move forward - pending, approved, applied -
but the evidence of every step lives in the two locked tables.)

Every crm_changes row must reference a review, so there can be no CRM change
without an approval behind it.

This is also the memory that makes re-runs safe: a proposal whose key
already has a decision is never raised again.

Standard library only (sqlite3 ships with Python).
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Proposal states.
STATE_PENDING = "pending"      # waiting for a reviewer
STATE_APPROVED = "approved"    # approved, change not yet (fully) sent
STATE_APPLIED = "applied"      # approved and confirmed in the CRM
STATE_REJECTED = "rejected"    # reviewer said no
STATE_FAILED = "failed"        # approved, but sending to the CRM failed (can be retried)
STATE_WITHDRAWN = "withdrawn"  # no longer suggested by the latest run, never decided

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    mode             TEXT NOT NULL,          -- rehearsal | live
    status           TEXT NOT NULL,          -- running | ok | aborted | error
    locations_count  INTEGER,
    accounts_count   INTEGER,
    proposals_total  INTEGER,                -- proposals this run produced
    proposals_new    INTEGER,                -- of those, how many were new
    proposals_suppressed INTEGER,            -- already decided, so not raised again
    run_dir          TEXT,                   -- folder holding this run's trace files
    message          TEXT
);

CREATE TABLE IF NOT EXISTS proposals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT NOT NULL UNIQUE,    -- fingerprint of what would change
    kind            TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    confidence      TEXT NOT NULL,
    location_slug   TEXT NOT NULL DEFAULT '',
    account_id      TEXT NOT NULL DEFAULT '',
    evidence_json   TEXT NOT NULL,
    operations_json TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'pending',
    first_seen_run  INTEGER REFERENCES runs(id),
    last_seen_run   INTEGER REFERENCES runs(id),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id  INTEGER NOT NULL UNIQUE REFERENCES proposals(id),  -- one decision per proposal
    decision     TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reason       TEXT NOT NULL DEFAULT '',
    reviewer     TEXT NOT NULL DEFAULT '',
    mode         TEXT NOT NULL,
    decided_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crm_changes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id        INTEGER NOT NULL REFERENCES reviews(id),   -- the approval that authorised it
    proposal_id      INTEGER NOT NULL REFERENCES proposals(id),
    step             INTEGER NOT NULL,       -- position within the proposal's operations
    method           TEXT NOT NULL,          -- POST | PATCH
    path             TEXT NOT NULL,          -- e.g. /accounts/001...
    account_id       TEXT NOT NULL DEFAULT '',  -- account changed or created
    request_json     TEXT NOT NULL,          -- exact body sent
    before_json      TEXT,                   -- whole account before (NULL for a create)
    after_json       TEXT,                   -- whole account read back afterwards
    fields_json      TEXT,                   -- {field: [before, after]} for changed fields
    response_status  TEXT NOT NULL DEFAULT '',
    response_json    TEXT,
    success          INTEGER NOT NULL,       -- 1 = sent and confirmed by read-back
    verified         INTEGER NOT NULL DEFAULT 0,
    error            TEXT NOT NULL DEFAULT '',
    mode             TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

-- Lock the two history tables: rows may be added, never changed or removed.
CREATE TRIGGER IF NOT EXISTS reviews_no_update BEFORE UPDATE ON reviews
BEGIN SELECT RAISE(ABORT, 'reviews are append-only'); END;
CREATE TRIGGER IF NOT EXISTS reviews_no_delete BEFORE DELETE ON reviews
BEGIN SELECT RAISE(ABORT, 'reviews are append-only'); END;
CREATE TRIGGER IF NOT EXISTS crm_changes_no_update BEFORE UPDATE ON crm_changes
BEGIN SELECT RAISE(ABORT, 'crm_changes are append-only'); END;
CREATE TRIGGER IF NOT EXISTS crm_changes_no_delete BEFORE DELETE ON crm_changes
BEGIN SELECT RAISE(ABORT, 'crm_changes are append-only'); END;
"""


def _now() -> str:
    """Current UTC time as text, e.g. 2026-11-21T20:31:50Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AuditDb:
    """Access to the audit trail database.

    Args:
        path: SQLite file to open (created, with its tables, if missing).
            Pass ":memory:" for a throwaway database in tests.
    """

    def __init__(self, path: Path | str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the Flask app may serve requests on
        # different threads; each call below is a short, complete transaction.
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ runs

    def start_run(self, mode: str, run_dir: str = "") -> int:
        """Record that a pipeline run has started.

        Args:
            mode: "rehearsal" or "live".
            run_dir: Folder where this run's trace files are written.

        Returns:
            The new run's id.
        """
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, mode, status, run_dir) VALUES (?, ?, 'running', ?)",
            (_now(), mode, run_dir))
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, status: str, message: str = "", **counts) -> None:
        """Record how a pipeline run ended.

        Args:
            run_id: Run to close.
            status: "ok", "aborted" or "error".
            message: Human-readable outcome.
            **counts: Any of locations_count, accounts_count, proposals_total,
                proposals_new, proposals_suppressed.
        """
        allowed = ("locations_count", "accounts_count", "proposals_total",
                   "proposals_new", "proposals_suppressed")
        sets = ", ".join(f"{name} = ?" for name in allowed if name in counts)
        values = [counts[name] for name in allowed if name in counts]
        self.conn.execute(
            f"UPDATE runs SET finished_at = ?, status = ?, message = ?{', ' + sets if sets else ''} WHERE id = ?",
            [_now(), status, message, *values, run_id])
        self.conn.commit()

    def last_ok_location_count(self) -> int | None:
        """Return how many communities the last successful run found (or None)."""
        row = self.conn.execute(
            "SELECT locations_count FROM runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1").fetchone()
        return row["locations_count"] if row else None

    def list_runs(self) -> list[sqlite3.Row]:
        """Return all runs, newest first."""
        return self.conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()

    # ------------------------------------------------------------- proposals

    def upsert_proposals(self, run_id: int, proposals: list) -> dict:
        """Store this run's proposals without ever duplicating or re-raising one.

        For each proposal, by its key:
            never seen          -> stored as pending ("new")
            seen, still pending -> evidence refreshed, stays pending
            seen, withdrawn     -> made pending again (the finding came back)
            seen, decided       -> left alone ("suppressed": not raised again)
        Pending proposals that this run no longer produced are marked
        withdrawn (the CRM or website changed so they no longer apply).

        Args:
            run_id: The current run.
            proposals: classify.Proposal objects from this run.

        Returns:
            Counts: {"total", "new", "refreshed", "suppressed", "withdrawn"}.
        """
        counts = {"total": len(proposals), "new": 0, "refreshed": 0, "suppressed": 0, "withdrawn": 0}
        now = _now()
        keys = set()
        for p in proposals:
            keys.add(p.key)
            row = self.conn.execute("SELECT id, state FROM proposals WHERE key = ?", (p.key,)).fetchone()
            evidence, operations = json.dumps(p.evidence), json.dumps(p.operations)
            if row is None:
                self.conn.execute(
                    "INSERT INTO proposals (key, kind, title, summary, confidence, location_slug, "
                    "account_id, evidence_json, operations_json, state, first_seen_run, last_seen_run, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (p.key, p.kind, p.title, p.summary, p.confidence, p.slug, p.account_id,
                     evidence, operations, STATE_PENDING, run_id, run_id, now, now))
                counts["new"] += 1
            elif row["state"] in (STATE_PENDING, STATE_WITHDRAWN):
                self.conn.execute(
                    "UPDATE proposals SET title=?, summary=?, confidence=?, evidence_json=?, "
                    "operations_json=?, state=?, last_seen_run=?, updated_at=? WHERE id=?",
                    (p.title, p.summary, p.confidence, evidence, operations, STATE_PENDING,
                     run_id, now, row["id"]))
                counts["refreshed"] += 1
            else:
                # Already approved, rejected, applied or failed: do not ask again.
                self.conn.execute("UPDATE proposals SET last_seen_run=? WHERE id=?", (run_id, row["id"]))
                counts["suppressed"] += 1
        # Withdraw pending proposals the latest run no longer makes.
        for row in self.conn.execute("SELECT id, key FROM proposals WHERE state = ?", (STATE_PENDING,)).fetchall():
            if row["key"] not in keys:
                self.conn.execute("UPDATE proposals SET state=?, updated_at=? WHERE id=?",
                                  (STATE_WITHDRAWN, now, row["id"]))
                counts["withdrawn"] += 1
        self.conn.commit()
        return counts

    def get_proposal(self, proposal_id: int) -> dict | None:
        """Return one proposal as a dict with evidence and operations decoded.

        Args:
            proposal_id: Proposal id.

        Returns:
            The proposal, or None if there is no such id.
        """
        row = self.conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        return self._decode(row) if row else None

    def list_proposals(self, state: str | None = None) -> list[dict]:
        """Return proposals, optionally only those in one state.

        Args:
            state: A STATE_* value, or None for all.

        Returns:
            Proposals ordered by id (the order they were found).
        """
        if state:
            rows = self.conn.execute("SELECT * FROM proposals WHERE state = ? ORDER BY id", (state,))
        else:
            rows = self.conn.execute("SELECT * FROM proposals ORDER BY id")
        return [self._decode(row) for row in rows.fetchall()]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        """Turn a proposals row into a dict, decoding its JSON columns."""
        item = dict(row)
        item["evidence"] = json.loads(item.pop("evidence_json"))
        item["operations"] = json.loads(item.pop("operations_json"))
        return item

    def set_state(self, proposal_id: int, state: str) -> None:
        """Move a proposal to a new state."""
        self.conn.execute("UPDATE proposals SET state=?, updated_at=? WHERE id=?",
                          (state, _now(), proposal_id))
        self.conn.commit()

    def state_counts(self) -> dict[str, int]:
        """Return how many proposals are in each state."""
        rows = self.conn.execute("SELECT state, COUNT(*) AS n FROM proposals GROUP BY state").fetchall()
        return {row["state"]: row["n"] for row in rows}

    # --------------------------------------------------------------- reviews

    def add_review(self, proposal_id: int, decision: str, reason: str, reviewer: str, mode: str) -> int:
        """Record a reviewer's decision and move the proposal's state.

        Args:
            proposal_id: Proposal being decided. Must still be pending.
            decision: "approved" or "rejected".
            reason: Optional free-text reason.
            reviewer: Who decided.
            mode: "rehearsal" or "live".

        Returns:
            The new review's id.

        Raises:
            ValueError: if the proposal does not exist or is not pending
                (a proposal can only be decided once).
        """
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"No proposal {proposal_id}")
        if proposal["state"] != STATE_PENDING:
            raise ValueError(f"Proposal {proposal_id} is {proposal['state']}, not pending")
        cur = self.conn.execute(
            "INSERT INTO reviews (proposal_id, decision, reason, reviewer, mode, decided_at) "
            "VALUES (?,?,?,?,?,?)",
            (proposal_id, decision, reason.strip(), reviewer, mode, _now()))
        self.conn.execute("UPDATE proposals SET state=?, updated_at=? WHERE id=?",
                          (STATE_APPROVED if decision == "approved" else STATE_REJECTED, _now(), proposal_id))
        self.conn.commit()
        return cur.lastrowid

    def review_for(self, proposal_id: int) -> dict | None:
        """Return the review of a proposal, or None if it is undecided."""
        row = self.conn.execute("SELECT * FROM reviews WHERE proposal_id = ?", (proposal_id,)).fetchone()
        return dict(row) if row else None

    # ----------------------------------------------------------- crm changes

    def add_change(self, *, review_id: int, proposal_id: int, step: int, method: str, path: str,
                   account_id: str, request: dict, before: dict | None, after: dict | None,
                   response_status: str, response: object, success: bool, verified: bool,
                   error: str, mode: str) -> int:
        """Record one request sent (or attempted) to the CRM.

        Args:
            review_id: The approval that authorised this request.
            proposal_id: Proposal it belongs to.
            step: Which operation of the proposal this was.
            method: "POST" or "PATCH".
            path: API path used.
            account_id: Account changed, or the new account's id for a create.
            request: Exact body sent.
            before: Whole account before the change (None for a create).
            after: Whole account read back after the change (None on failure).
            response_status: "ok" or the HTTP status / error class.
            response: The CRM's reply.
            success: True only if the request worked AND read-back confirmed it.
            verified: True if the read-back showed the intended values.
            error: Error text when it did not succeed.
            mode: "rehearsal" or "live".

        Returns:
            The new change row's id.
        """
        fields = None
        if after is not None:
            fields = {name: [(before or {}).get(name), after.get(name)] for name in request}
        cur = self.conn.execute(
            "INSERT INTO crm_changes (review_id, proposal_id, step, method, path, account_id, "
            "request_json, before_json, after_json, fields_json, response_status, response_json, "
            "success, verified, error, mode, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (review_id, proposal_id, step, method, path, account_id, json.dumps(request),
             json.dumps(before) if before is not None else None,
             json.dumps(after) if after is not None else None,
             json.dumps(fields) if fields is not None else None,
             response_status, json.dumps(response, default=str), int(success), int(verified),
             error, mode, _now()))
        self.conn.commit()
        return cur.lastrowid

    def successful_change(self, proposal_id: int, step: int) -> dict | None:
        """Return the successful change already recorded for a proposal step.

        Used when retrying a part-finished proposal, so a step that already
        landed (especially an account creation) is never sent twice.

        Args:
            proposal_id: Proposal id.
            step: Operation step number.

        Returns:
            The change row as a dict, or None.
        """
        row = self.conn.execute(
            "SELECT * FROM crm_changes WHERE proposal_id = ? AND step = ? AND success = 1 "
            "ORDER BY id LIMIT 1", (proposal_id, step)).fetchone()
        return dict(row) if row else None

    def changes_for(self, proposal_id: int) -> list[dict]:
        """Return every CRM request recorded for a proposal, oldest first."""
        rows = self.conn.execute(
            "SELECT * FROM crm_changes WHERE proposal_id = ? ORDER BY id", (proposal_id,)).fetchall()
        return [self._decode_change(row) for row in rows]

    @staticmethod
    def _decode_change(row: sqlite3.Row) -> dict:
        """Turn a crm_changes row into a dict with its JSON columns decoded."""
        item = dict(row)
        for column in ("request_json", "before_json", "after_json", "fields_json", "response_json"):
            raw = item.pop(column)
            item[column[:-5]] = json.loads(raw) if raw else None
        return item

    # ---------------------------------------------------------------- history

    def history(self) -> list[dict]:
        """Return the full audit trail, newest first, as flat rows.

        Each row is either a review decision or a CRM request, joined to its
        proposal, ready for the Audit page and the CSV export.

        Returns:
            Dicts with keys: when, event, proposal_id, title, kind, decision,
            reason, reviewer, method, path, account_id, fields, success,
            error, review_id, change_id, mode.
        """
        events: list[dict] = []
        for row in self.conn.execute(
                "SELECT r.*, p.title, p.kind FROM reviews r JOIN proposals p ON p.id = r.proposal_id").fetchall():
            events.append({
                "when": row["decided_at"], "event": "review", "proposal_id": row["proposal_id"],
                "title": row["title"], "kind": row["kind"], "decision": row["decision"],
                "reason": row["reason"], "reviewer": row["reviewer"], "method": "", "path": "",
                "account_id": "", "fields": None, "success": None, "error": "",
                "review_id": row["id"], "change_id": None, "mode": row["mode"], "_order": (row["decided_at"], 0, row["id"]),
            })
        for row in self.conn.execute(
                "SELECT c.*, p.title, p.kind FROM crm_changes c JOIN proposals p ON p.id = c.proposal_id").fetchall():
            events.append({
                "when": row["created_at"], "event": "crm_change", "proposal_id": row["proposal_id"],
                "title": row["title"], "kind": row["kind"], "decision": "", "reason": "",
                "reviewer": "", "method": row["method"], "path": row["path"],
                "account_id": row["account_id"],
                "fields": json.loads(row["fields_json"]) if row["fields_json"] else None,
                "success": bool(row["success"]), "error": row["error"],
                "review_id": row["review_id"], "change_id": row["id"], "mode": row["mode"],
                "_order": (row["created_at"], 1, row["id"]),
            })
        events.sort(key=lambda e: e.pop("_order"), reverse=True)
        return events

    def export_csv(self, path: Path) -> Path:
        """Write the audit trail to a CSV file people can read without tools.

        Args:
            path: Destination file (its folder is created if needed).

        Returns:
            The path written.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = ["when", "event", "mode", "proposal_id", "kind", "title", "decision", "reason",
                   "reviewer", "review_id", "change_id", "method", "path", "account_id",
                   "fields_before_after", "success", "error"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for event in reversed(self.history()):   # oldest first reads like a story
                event["fields_before_after"] = json.dumps(event.pop("fields")) if event["fields"] else ""
                event["success"] = "" if event["success"] is None else ("yes" if event["success"] else "no")
                writer.writerow({name: event.get(name, "") for name in columns})
        return path
