"""Tests for the text tidying used before comparing."""

from bellhaven_sync.normalize import (norm_name, norm_phone, norm_street,
                                      similarity, zip_is_swapped)


def test_street_abbreviations_are_the_same_street():
    assert norm_street("210 Orchard Ln") == norm_street("210 Orchard Lane")
    assert norm_street("4850 NW Sylvania Ave") == norm_street("4850 Northwest Sylvania Avenue")
    assert norm_street("199 Barks Rd W") == norm_street("199 Barks Road West")
    assert norm_street("3313 Wilmington Pk") == norm_street("3313 Wilmington Pike")


def test_different_streets_stay_different():
    assert norm_street("PO Box 517") != norm_street("3156 W Prospect Rd")


def test_name_variants_are_the_same_name():
    assert norm_name("Bellhaven Rehab and Nursing of Grove City") == \
        norm_name("Bellhaven Rehabilitation & Nursing of Grove City")
    assert norm_name("Bellhaven Health Care Center of Ashland") == \
        norm_name("Bellhaven Healthcare Centre of Ashland")
    assert norm_name("Arbors at Bellhaven Dayton") == norm_name("The Arbors at Bellhaven - Dayton")


def test_phone_is_digits_only():
    assert norm_phone("(614) 250-9447") == "6142509447"


def test_similarity_of_empty_strings_is_zero():
    """Missing data must never look like a match."""
    assert similarity("", "") == 0.0
    assert similarity("abc", "abc") == 1.0


def test_zip_swap_detection():
    assert zip_is_swapped("45626", "45662")
    assert not zip_is_swapped("45626", "45626")     # identical is not a swap
    assert not zip_is_swapped("45626", "45627")     # one digit off is not a swap
    assert not zip_is_swapped("45626", "44280")
