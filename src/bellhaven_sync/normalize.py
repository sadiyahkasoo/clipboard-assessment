"""
Text tidying used before comparing website data with CRM data.

People type the same thing many ways: "210 Orchard Ln" and "210 Orchard
Lane", "Rehab and Nursing" and "Rehabilitation & Nursing". None of those are
real differences, so we reduce both sides to one standard spelling before
comparing. Nothing here changes what is stored anywhere; these functions only
produce comparison keys.

Standard library only.
"""

from __future__ import annotations

import difflib
import re

# Street-word abbreviations -> full word. Applied word by word.
STREET_WORDS: dict[str, str] = {
    "st": "street", "ave": "avenue", "av": "avenue", "rd": "road", "dr": "drive",
    "ln": "lane", "blvd": "boulevard", "pk": "pike", "pkwy": "parkway",
    "ct": "court", "hwy": "highway", "cir": "circle", "pl": "place", "ter": "terrace",
    "n": "north", "s": "south", "e": "east", "w": "west",
    "nw": "northwest", "ne": "northeast", "sw": "southwest", "se": "southeast",
}

# Spelling variants inside facility names -> one standard word.
NAME_WORDS: dict[str, str] = {
    "rehab": "rehabilitation",
    "centre": "center",
    "&": "and",
}

# Words that carry no identifying information in a facility name here.
# "bellhaven" is in nearly every name, so it cannot tell two facilities apart.
NAME_STOP_WORDS: frozenset[str] = frozenset({"the", "of", "at", "and", "bellhaven"})


def norm_street(street: str) -> str:
    """Reduce a street address to a comparison key.

    Lower-cases, drops punctuation and expands abbreviations, so
    "4850 NW Sylvania Ave" and "4850 Northwest Sylvania Avenue" give the
    same key.

    Args:
        street: Street line as written.

    Returns:
        The tidied key ("" for an empty input).
    """
    words = re.sub(r"[^a-z0-9 ]", "", (street or "").lower()).split()
    return " ".join(STREET_WORDS.get(word, word) for word in words)


def norm_name(name: str) -> str:
    """Reduce a facility name to a comparison key.

    Lower-cases, standardises spelling variants, removes filler words and
    sorts the remaining words. Sorting means word order does not matter
    ("Arbors at Bellhaven Dayton" vs "The Arbors at Bellhaven - Dayton").

    Args:
        name: Facility name as written.

    Returns:
        The tidied key.
    """
    text = (name or "").lower().replace("health care", "healthcare")
    text = re.sub(r"[^a-z0-9& ]", " ", text)
    words = (NAME_WORDS.get(word, word) for word in text.split())
    return " ".join(sorted(word for word in words if word not in NAME_STOP_WORDS))


def norm_phone(phone: str) -> str:
    """Reduce a phone number to its digits.

    Args:
        phone: Phone number in any format.

    Returns:
        Digits only, e.g. "6142509447".
    """
    return re.sub(r"\D", "", phone or "")


def norm_person(name: str) -> str:
    """Reduce a person's name to a comparison key (lower-case, single spaces).

    Args:
        name: Person's name.

    Returns:
        The tidied key.
    """
    return " ".join((name or "").lower().split())


def similarity(a: str, b: str) -> float:
    """Measure how alike two strings are, from 0.0 (nothing shared) to 1.0.

    Uses Python's built-in sequence matcher (roughly: share of characters
    that line up). Two empty strings count as no similarity, so missing data
    never looks like a match.

    Args:
        a: First string (already tidied).
        b: Second string (already tidied).

    Returns:
        Similarity ratio between 0.0 and 1.0.
    """
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def zip_is_swapped(a: str, b: str) -> bool:
    """Tell whether two zip codes differ only by two digits changing places.

    "45626" vs "45662" is a classic typing slip, not a different town.

    Args:
        a: First zip code.
        b: Second zip code.

    Returns:
        True if the zips are the same length, differ in exactly two
        positions, and those two digits are swapped.
    """
    if len(a) != len(b) or a == b:
        return False
    differing = [i for i in range(len(a)) if a[i] != b[i]]
    if len(differing) != 2:
        return False
    i, j = differing
    return a[i] == b[j] and a[j] == b[i]
