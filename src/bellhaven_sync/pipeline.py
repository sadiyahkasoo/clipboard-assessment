"""
The daily job: scrape -> snapshot the CRM -> match -> propose.

This job only READS the website and the CRM. It never changes the CRM; it
only fills the review queue. Changes happen later, one approval at a time,
in the review app.

Every run writes a dated folder of trace files so each step can be re-traced:

    <runs>/<timestamp>/
        01_scrape/pages/*.html      every page exactly as downloaded
        01_scrape/locations.json    the communities read from those pages
        01_scrape/report.json       where each was found; counts the site claims
        02_crm/accounts.json        the CRM as it was at this moment
        02_crm/contacts.json
        03_matching/scores.csv      every pair score with its six-part breakdown
        03_matching/communities.json  the group each community fell into, and why
        03_matching/off_website.json  Bellhaven accounts with no community
        04_proposals/proposals.json   the proposed changes with evidence
        04_proposals/planned_requests.md  the exact CRM requests they would send
        summary.json                counts for the whole run

Run it with:
    PYTHONPATH=src python -m bellhaven_sync.pipeline --mode rehearsal
    PYTHONPATH=src python -m bellhaven_sync.pipeline --mode live
Add --print-plan to print the exact requests that WOULD be sent (dry run).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import audit_db, classify, config, scraper
from .crm_client import CrmClient, LocalCrm


def get_client(mode: str):
    """Return the CRM client for a mode.

    Args:
        mode: "live" for the real CRM, "rehearsal" for the local copy.

    Returns:
        A CrmClient or LocalCrm.

    Raises:
        FileNotFoundError: in rehearsal mode if the local copy has not been
            created yet (run `python -m bellhaven_sync.rehearsal reset`).
    """
    if mode == config.MODE_LIVE:
        return CrmClient()
    local = config.paths_for(mode).local_crm
    if not local.exists():
        raise FileNotFoundError(
            "No rehearsal CRM found. Create one with: "
            "PYTHONPATH=src python -m bellhaven_sync.rehearsal reset")
    return LocalCrm(local)


def _write_json(path: Path, payload: object) -> None:
    """Write a JSON trace file, creating its folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _write_scores(path: Path, result: classify.Result, accounts: list[dict]) -> None:
    """Save every pair score as CSV (the matching trace).

    Pairs in different states always score 0 and are left out to keep the
    file readable; everything in the same state is listed.

    Args:
        path: Destination CSV.
        result: The classification result holding the scores.
        accounts: CRM accounts, to show names next to ids.
    """
    names = {a["account_id"]: a for a in accounts}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["community_slug", "account_id", "account_name", "account_owner", "total",
                         "band", "street", "zip", "city", "name", "phone", "admin", "notes"])
        for s in sorted(result.scores, key=lambda s: (s.slug, -s.total)):
            if s.notes == ["different state"]:
                continue
            account = names[s.account_id]
            writer.writerow([s.slug, s.account_id, account["name"], account.get("parent_name", ""),
                             s.total, s.band, s.parts["street"], s.parts["zip"], s.parts["city"],
                             s.parts["name"], s.parts["phone"], s.parts["admin"], "; ".join(s.notes)])


def plan_text(proposals: list[classify.Proposal]) -> str:
    """Render the exact requests the proposals would send, as readable text.

    This is the dry run: it shows every request without sending any.

    Args:
        proposals: Proposals to describe.

    Returns:
        Markdown text listing each proposal and its requests.
    """
    lines = ["# Planned CRM requests (dry run - nothing has been sent)", "",
             f"{len(proposals)} proposals. Each request below is sent only after a reviewer approves it.", ""]
    for number, p in enumerate(proposals, 1):
        lines += [f"## {number}. {p.title}", "",
                  f"- Kind: {classify.KIND_LABELS[p.kind]}  |  Confidence: {p.confidence}",
                  f"- Why: {p.summary}", ""]
        for req in classify.planned_requests(p):
            lines += [f"    {req['method']} {req['path']}",
                      f"    {json.dumps(req['body'])}", ""]
    return "\n".join(lines)


def run(mode: str, client=None, fetch: Callable[[str], str] | None = None,
        db: audit_db.AuditDb | None = None, runs_dir: Path | None = None) -> dict:
    """Run the read-only daily job once.

    Args:
        mode: "rehearsal" or "live" - decides which CRM, audit trail and
            trace folder are used.
        client: CRM client override (tests pass a LocalCrm).
        fetch: Website fetch function override (tests pass saved pages).
        db: Audit trail override (tests pass an in-memory database).
        runs_dir: Trace folder override.

    Returns:
        A summary dict: status, counts, and where the trace was written.
    """
    paths = config.paths_for(mode)
    client = client or get_client(mode)
    fetch = fetch or scraper.http_fetcher()
    db = db or audit_db.AuditDb(paths.audit_db)
    runs_dir = runs_dir or paths.runs_dir

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = runs_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = db.start_run(mode, str(run_dir))
    summary: dict = {"run_id": run_id, "mode": mode, "started_at": stamp, "run_dir": str(run_dir)}

    try:
        # ---- 1. Scrape the website ---------------------------------------
        locations, scrape_report = scraper.crawl(fetch, run_dir / "01_scrape")
        summary["locations"] = len(locations)

        # Safety stop: a sudden drop in communities means the site is probably
        # broken. Carrying on would wrongly flag accounts as "not on website".
        previous = db.last_ok_location_count()
        if previous and len(locations) < previous * config.MIN_SCRAPE_SHARE:
            message = (f"Scrape found {len(locations)} communities but the last good run found "
                       f"{previous}. Stopping without proposing anything.")
            db.finish_run(run_id, "aborted", message, locations_count=len(locations))
            summary.update(status="aborted", message=message)
            _write_json(run_dir / "summary.json", summary)
            return summary

        # ---- 2. Snapshot the CRM (read-only) -----------------------------
        accounts = client.list_accounts()
        contacts = client.list_contacts()
        _write_json(run_dir / "02_crm" / "accounts.json", accounts)
        _write_json(run_dir / "02_crm" / "contacts.json", contacts)
        summary["accounts"] = len(accounts)

        # ---- 3. Match and classify ---------------------------------------
        result = classify.classify(locations, accounts, contacts)
        _write_scores(run_dir / "03_matching" / "scores.csv", result, accounts)
        _write_json(run_dir / "03_matching" / "communities.json", result.communities)
        _write_json(run_dir / "03_matching" / "off_website.json", result.off_website)

        # ---- 4. Save proposals and the dry-run plan ----------------------
        _write_json(run_dir / "04_proposals" / "proposals.json", [asdict(p) for p in result.proposals])
        (run_dir / "04_proposals" / "planned_requests.md").write_text(plan_text(result.proposals), encoding="utf-8")

        # ---- 5. Store in the audit trail without re-raising decided items -
        counts = db.upsert_proposals(run_id, result.proposals)
        groups: dict[str, int] = {}
        for row in result.communities:
            for group in row["groups"]:
                groups[group] = groups.get(group, 0) + 1
        summary.update(status="ok", proposals=counts, community_groups=groups,
                       off_website=len(result.off_website),
                       only_outside_directory=scrape_report["only_outside_directory"])
        db.finish_run(run_id, "ok",
                      f"{counts['new']} new, {counts['suppressed']} already decided",
                      locations_count=len(locations), accounts_count=len(accounts),
                      proposals_total=counts["total"], proposals_new=counts["new"],
                      proposals_suppressed=counts["suppressed"])
    except Exception as exc:  # record the failure, then let it surface
        db.finish_run(run_id, "error", f"{type(exc).__name__}: {exc}")
        summary.update(status="error", message=f"{type(exc).__name__}: {exc}")
        _write_json(run_dir / "summary.json", summary)
        raise

    _write_json(run_dir / "summary.json", summary)
    summary["_proposals"] = result.proposals   # for --print-plan; not saved
    return summary


def log_line(summary: dict) -> str:
    """Format one line for the daily log.

    Args:
        summary: The dict returned by `run`.

    Returns:
        A single line of text.
    """
    counts = summary.get("proposals", {})
    return (f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} "
            f"mode={summary['mode']} run={summary.get('run_id')} status={summary.get('status')} "
            f"communities={summary.get('locations', '-')} accounts={summary.get('accounts', '-')} "
            f"proposals_found={counts.get('total', '-')} new={counts.get('new', '-')} "
            f"already_decided={counts.get('suppressed', '-')} withdrawn={counts.get('withdrawn', '-')} "
            f"{summary.get('message', '')}").rstrip()


def _append_log(mode: str, line: str) -> None:
    """Add one line to the run log for a mode.

    Live runs log to logs/daily.log (the record that the daily schedule
    fired). Rehearsal runs log inside data/rehearsal/ so practice runs never
    clutter the real log.

    Args:
        mode: "rehearsal" or "live".
        line: The line to append.
    """
    if mode == config.MODE_LIVE:
        log_file = config.LOG_DIR / "daily.log"
    else:
        log_file = config.paths_for(mode).local_crm.parent / "daily.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a") as handle:
        handle.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for the daily job.

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        Process exit code: 0 on success, 1 if the run aborted or failed.
    """
    parser = argparse.ArgumentParser(description="Bellhaven ownership sync: read-only daily job.")
    parser.add_argument("--mode", choices=[config.MODE_REHEARSAL, config.MODE_LIVE],
                        default=config.MODE_REHEARSAL,
                        help="rehearsal = local copy of the CRM (default); live = the real CRM")
    parser.add_argument("--print-plan", action="store_true",
                        help="print the exact CRM requests the proposals WOULD send (dry run)")
    args = parser.parse_args(argv)

    try:
        summary = run(args.mode)
    except Exception as exc:
        line = (f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} mode={args.mode} "
                f"status=error {type(exc).__name__}: {exc}")
        _append_log(args.mode, line)
        print(line, file=sys.stderr)
        return 1

    proposals = summary.pop("_proposals", [])
    line = log_line(summary)
    _append_log(args.mode, line)
    print(line)
    print(f"Trace written to {summary['run_dir']}")
    if args.print_plan:
        print()
        print(plan_text(proposals))
    return 0 if summary.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
