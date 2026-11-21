"""
Talking to the CRM.

Two classes with the SAME methods live here:

    CrmClient  - the real CRM sandbox, over HTTPS.
    LocalCrm   - a stand-in that keeps the accounts in a local JSON file.

Because they look identical to the rest of the code, the whole system
(matching, review app, apply step) can be rehearsed end to end against
LocalCrm with zero risk, then pointed at the real CRM unchanged. That is how
the "smoke test before any real change" rule is met.

The CRM has no delete and no merge, so neither class offers them.
"""

from __future__ import annotations

import copy
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import config

# Fields a caller is allowed to send when creating or updating an account.
# Read-only fields (ids, money, audit stamps) are deliberately left out so a
# bug can never try to overwrite billing figures.
WRITABLE_ACCOUNT_FIELDS: frozenset[str] = frozenset({
    "name", "parent_id", "billing_street", "billing_city", "billing_state",
    "billing_zip", "care_type", "status", "phone", "note",
    "chow_current_account", "duplicate_of_account",
})


class CrmError(RuntimeError):
    """The CRM refused or failed a request.

    Attributes:
        status: HTTP status code (0 if the request never got an answer).
        body: The CRM's reply, decoded if it was JSON.
    """

    def __init__(self, message: str, status: int = 0, body: object = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _check_fields(fields: dict) -> None:
    """Refuse to send anything that is not a known, writable account field.

    Args:
        fields: Field names and values about to be sent.

    Raises:
        ValueError: on an unknown field or an invalid status value.
    """
    unknown = set(fields) - WRITABLE_ACCOUNT_FIELDS
    if unknown:
        raise ValueError(f"Refusing to send non-writable field(s): {sorted(unknown)}")
    if "status" in fields and fields["status"] not in config.VALID_STATUSES:
        raise ValueError(f"Invalid status {fields['status']!r}")


class CrmClient:
    """The real CRM sandbox.

    Args:
        token: Personal API token. Defaults to the one in .env.
        base: API base address.
        session: Optional requests session (tests pass a fake one).
    """

    mode = config.MODE_LIVE

    def __init__(self, token: str | None = None, base: str = config.API_BASE,
                 session: requests.Session | None = None):
        self.base = base.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token or config.load_token()}"

    def _request(self, method: str, path: str, **kwargs) -> object:
        """Send one request and return the decoded JSON reply.

        Args:
            method: "GET", "POST" or "PATCH".
            path: Path under the API base, e.g. "/accounts/001...".
            **kwargs: Passed to requests (params=, json=).

        Returns:
            Decoded JSON body.

        Raises:
            CrmError: on a network failure or any non-2xx answer.
        """
        try:
            response = self.session.request(
                method, self.base + path, timeout=config.HTTP_TIMEOUT, **kwargs
            )
        except requests.RequestException as exc:
            raise CrmError(f"{method} {path} failed: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            body = response.text
        if not response.ok:
            raise CrmError(f"{method} {path} -> HTTP {response.status_code}: {body}",
                           status=response.status_code, body=body)
        return body

    def _list(self, resource: str, params: dict | None = None) -> list[dict]:
        """Download every record of one kind, following pagination.

        Args:
            resource: "accounts" or "contacts".
            params: Optional filters (e.g. {"parent_id": "..."}).

        Returns:
            All matching records.
        """
        records: list[dict] = []
        page = 1
        while True:
            body = self._request("GET", f"/{resource}",
                                 params={**(params or {}), "page": page, "page_size": 200})
            rows = body.get("data", [])
            records.extend(rows)
            if len(records) >= body.get("total", len(records)) or not rows:
                return records
            page += 1

    def me(self) -> dict:
        """Return who the token belongs to ({"candidate": ..., "message": ...})."""
        return self._request("GET", "/me")

    def list_accounts(self, **filters) -> list[dict]:
        """Return all accounts, optionally filtered (q, city, state, zip, street, parent_id)."""
        return self._list("accounts", filters)

    def list_contacts(self, **filters) -> list[dict]:
        """Return all contacts, optionally filtered (account_id, q)."""
        return self._list("contacts", filters)

    def get_account(self, account_id: str) -> dict:
        """Return one account by id. Raises CrmError (404) if it does not exist."""
        return self._request("GET", f"/accounts/{account_id}")

    def create_account(self, fields: dict) -> dict:
        """Create a new account.

        Args:
            fields: Writable account fields for the new account.

        Returns:
            The account as the CRM stored it, including its new account_id.
        """
        _check_fields(fields)
        return self._request("POST", "/accounts", json=fields)

    def update_account(self, account_id: str, fields: dict) -> dict:
        """Change some fields of an existing account.

        Args:
            account_id: Account to change.
            fields: Only the fields that should change.

        Returns:
            The account as the CRM stored it after the change.
        """
        _check_fields(fields)
        return self._request("PATCH", f"/accounts/{account_id}", json=fields)


class LocalCrm:
    """A stand-in CRM kept in one local JSON file, for rehearsals and tests.

    It behaves like the real CRM for everything this project uses: it lists,
    reads, creates and updates accounts, fills in parent_name, stamps
    updated_at, and marks accounts it created.

    Args:
        path: JSON file holding {"accounts": [...], "contacts": [...]}.
            If None, the data is kept in memory only (used by tests).
        accounts: Starting accounts when no file exists yet.
        contacts: Starting contacts when no file exists yet.
    """

    mode = config.MODE_REHEARSAL

    def __init__(self, path: Path | None = None, accounts: list[dict] | None = None,
                 contacts: list[dict] | None = None):
        self.path = path
        if path is not None and path.exists():
            stored = json.loads(path.read_text())
            self.accounts = stored["accounts"]
            self.contacts = stored["contacts"]
        else:
            self.accounts = copy.deepcopy(accounts or [])
            self.contacts = copy.deepcopy(contacts or [])
            self._save()

    @classmethod
    def from_backup(cls, backup_folder: Path, path: Path | None = None) -> "LocalCrm":
        """Build a fresh local CRM from a backup folder.

        Args:
            backup_folder: Folder containing accounts.json and contacts.json.
            path: Where to keep the local copy (None = memory only). An
                existing file at this path is replaced.

        Returns:
            A LocalCrm holding an exact copy of the backup.
        """
        if path is not None and path.exists():
            path.unlink()
        return cls(
            path=path,
            accounts=json.loads((backup_folder / "accounts.json").read_text()),
            contacts=json.loads((backup_folder / "contacts.json").read_text()),
        )

    def _save(self) -> None:
        """Write the current state to the JSON file, if one is in use."""
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(
                {"accounts": self.accounts, "contacts": self.contacts}, indent=2))

    def _find(self, account_id: str) -> dict:
        """Return the stored account dict (not a copy). Raises CrmError 404."""
        for account in self.accounts:
            if account["account_id"] == account_id:
                return account
        raise CrmError(f"GET /accounts/{account_id} -> HTTP 404: Account not found",
                       status=404, body={"detail": "Account not found"})

    def _stamp(self, account: dict) -> None:
        """Refresh the derived fields the real CRM maintains by itself."""
        parent_id = account.get("parent_id") or ""
        account["parent_name"] = self._find(parent_id)["name"] if parent_id else ""
        account["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    def me(self) -> dict:
        """Mimic /me so the app can show whose data it is working on."""
        return {"candidate": "Rehearsal (local copy)", "message": "Local CRM stand-in."}

    def list_accounts(self, **filters) -> list[dict]:
        """Return copies of all accounts, optionally filtered by parent_id."""
        rows = self.accounts
        if filters.get("parent_id"):
            rows = [a for a in rows if a.get("parent_id") == filters["parent_id"]]
        return copy.deepcopy(rows)

    def list_contacts(self, **filters) -> list[dict]:
        """Return copies of all contacts, optionally filtered by account_id."""
        rows = self.contacts
        if filters.get("account_id"):
            rows = [c for c in rows if c.get("account_id") == filters["account_id"]]
        return copy.deepcopy(rows)

    def get_account(self, account_id: str) -> dict:
        """Return a copy of one account. Raises CrmError (404) if missing."""
        return copy.deepcopy(self._find(account_id))

    def create_account(self, fields: dict) -> dict:
        """Create an account with a made-up local id, like the real CRM would.

        Args:
            fields: Writable account fields.

        Returns:
            A copy of the stored account.
        """
        _check_fields(fields)
        if fields.get("parent_id"):
            self._find(fields["parent_id"])  # parent must exist
        account = {
            "account_id": "001LOCAL" + secrets.token_hex(5).upper(),
            "name": "", "parent_id": "", "parent_name": "",
            "billing_street": "", "billing_city": "", "billing_state": "", "billing_zip": "",
            "care_type": "", "status": "Active", "phone": "",
            "lifetime_revenue": 0, "outstanding_ar": 0,
            "chow_current_account": "", "duplicate_of_account": "", "note": "",
            "created_by_candidate": True, "updated_at": "",
        }
        account.update(fields)
        self.accounts.append(account)
        self._stamp(account)
        self._save()
        return copy.deepcopy(account)

    def update_account(self, account_id: str, fields: dict) -> dict:
        """Change fields on an account.

        Args:
            account_id: Account to change.
            fields: Only the fields that should change.

        Returns:
            A copy of the stored account after the change.
        """
        _check_fields(fields)
        account = self._find(account_id)
        for pointer in ("parent_id", "chow_current_account", "duplicate_of_account"):
            if fields.get(pointer):
                self._find(fields[pointer])  # pointed-at account must exist
        account.update(fields)
        self._stamp(account)
        self._save()
        return copy.deepcopy(account)
