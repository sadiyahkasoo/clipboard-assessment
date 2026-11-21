"""
Step 1: back up the whole CRM to local files.

This is the very first thing run in the exercise (rule 1). It only READS from
the CRM. It deliberately uses nothing but the Python standard library so it
can run before any outside library is installed.

What it saves, in data/backups/<timestamp>/:
    accounts.json   every account, exactly as the CRM returned it
    contacts.json   every contact, exactly as the CRM returned it
    manifest.json   when the backup was taken, how many records, and a
                    checksum of each file so later tampering is detectable

Run it with:
    PYTHONPATH=src python -m bellhaven_sync.backup
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config

# How many records to request per page. The CRM caps this at 200.
PAGE_SIZE = 200


def _get_json(path: str, token: str) -> dict:
    """Send one authenticated GET request to the CRM and decode the JSON.

    Args:
        path: API path beginning with "/", e.g. "/accounts?page=1".
        token: Personal API token, sent as a Bearer token.

    Returns:
        The decoded JSON body as a dict.
    """
    request = urllib.request.Request(
        config.API_BASE + path,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=config.HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_all(resource: str, token: str) -> list[dict]:
    """Download every record of one kind, following pagination to the end.

    The CRM answers list requests as {"data": [...], "page", "page_size",
    "total"}. We keep asking for the next page until we hold `total` records.

    Args:
        resource: "accounts" or "contacts".
        token: Personal API token.

    Returns:
        A list of every record of that kind.

    Raises:
        RuntimeError: if the CRM stops returning rows before `total` is reached.
    """
    records: list[dict] = []
    page = 1
    while True:
        body = _get_json(f"/{resource}?page={page}&page_size={PAGE_SIZE}", token)
        rows = body.get("data", [])
        records.extend(rows)
        total = body.get("total", len(records))
        if len(records) >= total:
            return records
        if not rows:
            raise RuntimeError(
                f"CRM returned an empty page {page} of {resource} "
                f"after {len(records)} of {total} records."
            )
        page += 1


def _write_json(path: Path, payload: object) -> str:
    """Write JSON to a file and return its SHA-256 checksum.

    Args:
        path: Destination file.
        payload: Any JSON-serialisable object.

    Returns:
        Hex SHA-256 digest of the bytes written.
    """
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def run_backup(backup_root: Path | None = None, token: str | None = None) -> Path:
    """Take a full backup of accounts and contacts.

    Args:
        backup_root: Folder to create the timestamped backup folder in.
            Defaults to data/backups/.
        token: API token. Defaults to the one in .env.

    Returns:
        The folder the backup was written to.
    """
    backup_root = backup_root or config.BACKUP_DIR
    token = token or config.load_token()

    taken_at = datetime.now(timezone.utc)
    folder = backup_root / taken_at.strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=False)

    # /me confirms the token works and tells us whose sandbox this is.
    who = _get_json("/me", token)
    accounts = fetch_all("accounts", token)
    contacts = fetch_all("contacts", token)

    manifest = {
        "taken_at_utc": taken_at.isoformat(timespec="seconds"),
        "api_base": config.API_BASE,
        "sandbox_owner": who.get("candidate"),
        "accounts": {
            "count": len(accounts),
            "sha256": _write_json(folder / "accounts.json", accounts),
        },
        "contacts": {
            "count": len(contacts),
            "sha256": _write_json(folder / "contacts.json", contacts),
        },
    }
    _write_json(folder / "manifest.json", manifest)
    return folder


def original_backup(backup_root: Path | None = None) -> Path:
    """Return the oldest backup folder, i.e. the untouched original CRM.

    The first backup is the one taken before any change was made, so it is
    the reference point for rehearsals and for the final before/after check.

    Args:
        backup_root: Folder holding the timestamped backups.

    Returns:
        Path of the earliest backup folder.

    Raises:
        FileNotFoundError: if no backup has been taken yet.
    """
    backup_root = backup_root or config.BACKUP_DIR
    folders = sorted(p for p in backup_root.glob("*") if (p / "manifest.json").exists())
    if not folders:
        raise FileNotFoundError("No backup found. Run the backup step first.")
    return folders[0]


if __name__ == "__main__":
    out = run_backup()
    summary = json.loads((out / "manifest.json").read_text())
    print(f"Backup saved to {out}")
    print(f"  accounts: {summary['accounts']['count']}")
    print(f"  contacts: {summary['contacts']['count']}")
    print(f"  sandbox owner: {summary['sandbox_owner']}")
