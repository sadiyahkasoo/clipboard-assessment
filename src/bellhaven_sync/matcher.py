"""
Step 3a: score how likely a website community and a CRM account are the
same facility.

Every (community, account) pair in the same state gets a score from 0 to 100
made of six independent pieces of evidence. The score falls into a band:

    65+    match      - same facility
    50-64  probable   - probably the same; a reviewer decides
    30-49  lookalike  - shown as evidence only, never changed
    <30    unrelated  - ignored

The reasoning behind the weights and cut-offs is in
docs/03-matching-explained.md. This module only measures; deciding what to
DO about a match happens in classify.py.

Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .normalize import (norm_name, norm_person, norm_phone, norm_street,
                        similarity, zip_is_swapped)
from .scraper import Location

BAND_MATCH = "match"
BAND_PROBABLE = "probable"
BAND_LOOKALIKE = "lookalike"
BAND_UNRELATED = "unrelated"


@dataclass
class Score:
    """The result of comparing one community with one account.

    Attributes:
        slug: Community slug.
        account_id: CRM account id.
        total: Sum of the parts, 0-100.
        band: "match", "probable", "lookalike" or "unrelated".
        parts: Points per piece of evidence, e.g. {"street": 40, "zip": 15, ...}.
        notes: Short plain-language remarks explaining notable parts.
    """

    slug: str
    account_id: str
    total: int
    band: str
    parts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def band_for(total: int) -> str:
    """Translate a total score into its band name.

    Args:
        total: Score from 0 to 100.

    Returns:
        One of the BAND_* constants.
    """
    if total >= config.THRESHOLD_MATCH:
        return BAND_MATCH
    if total >= config.THRESHOLD_PROBABLE:
        return BAND_PROBABLE
    if total >= config.THRESHOLD_LOOKALIKE:
        return BAND_LOOKALIKE
    return BAND_UNRELATED


def score_pair(location: Location, account: dict, contact_names: set[str]) -> Score:
    """Score one community against one CRM account.

    Args:
        location: The website community.
        account: The CRM account (a dict as returned by the API).
        contact_names: Tidied names of the contacts on this account
            (see normalize.norm_person).

    Returns:
        A Score. Accounts in a different state (or with no state, such as
        parent-company accounts) score 0: a facility cannot change state.
    """
    parts = {"street": 0, "zip": 0, "city": 0, "name": 0, "phone": 0, "admin": 0}
    notes: list[str] = []

    # Hard gate: different state means different facility, whatever the name.
    if not account.get("billing_state") or account["billing_state"] != location.state:
        return Score(location.slug, account["account_id"], 0, BAND_UNRELATED, parts,
                     ["different state"])

    # Street: the strongest clue, because buildings do not move.
    street_ratio = similarity(norm_street(location.street), norm_street(account.get("billing_street", "")))
    if street_ratio == 1.0:
        parts["street"] = config.WEIGHT_STREET_EXACT
    elif street_ratio >= config.STREET_CLOSE_RATIO:
        parts["street"] = config.WEIGHT_STREET_CLOSE
        notes.append("street nearly the same (possible typo)")

    # Zip: exact, or a two-digit swap which we treat as a typo.
    account_zip = account.get("billing_zip", "")
    if account_zip == location.zip:
        parts["zip"] = config.WEIGHT_ZIP_EXACT
    elif zip_is_swapped(account_zip, location.zip):
        parts["zip"] = config.WEIGHT_ZIP_SWAPPED
        notes.append("zip differs by two swapped digits (likely typo)")

    if account.get("billing_city", "").strip().lower() == location.city.strip().lower():
        parts["city"] = config.WEIGHT_CITY

    # Name: scaled by similarity, because rebrands change names.
    name_ratio = similarity(norm_name(location.name), norm_name(account.get("name", "")))
    parts["name"] = round(config.WEIGHT_NAME_MAX * name_ratio)

    phone = norm_phone(location.phone)
    if phone and phone == norm_phone(account.get("phone", "")):
        parts["phone"] = config.WEIGHT_PHONE

    if location.administrator and norm_person(location.administrator) in contact_names:
        parts["admin"] = config.WEIGHT_ADMIN

    total = sum(parts.values())
    return Score(location.slug, account["account_id"], total, band_for(total), parts, notes)


def contacts_by_account(contacts: list[dict]) -> dict[str, set[str]]:
    """Group active contact names by the account they belong to.

    Args:
        contacts: CRM contacts.

    Returns:
        {account_id: {tidied contact name, ...}}.
    """
    grouped: dict[str, set[str]] = {}
    for contact in contacts:
        grouped.setdefault(contact["account_id"], set()).add(norm_person(contact["name"]))
    return grouped


def score_all(locations: list[Location], accounts: list[dict],
              contacts: list[dict]) -> list[Score]:
    """Score every community against every candidate account.

    Args:
        locations: Website communities.
        accounts: Candidate CRM accounts (callers pass facility accounts
            only; parent-company accounts have no address and score 0).
        contacts: CRM contacts.

    Returns:
        One Score per (community, account) pair, in input order. This full
        list is saved on every run so each decision can be re-traced.
    """
    names = contacts_by_account(contacts)
    return [
        score_pair(location, account, names.get(account["account_id"], set()))
        for location in locations
        for account in accounts
    ]
