"""Tests for match scoring and the score bands (cut-offs)."""

from bellhaven_sync import config, matcher


def _score(result, slug_part, account_name):
    """Return the Score for a community (by slug fragment) and account name."""
    return next(s for s in result.scores
                if slug_part in s.slug and s.account_id == account_name)


def _id(accounts, name, city=None):
    """Return the id of the account with this name (and city, if given)."""
    hits = [a for a in accounts if a["name"] == name and (city is None or a["billing_city"] == city)]
    assert len(hits) == 1
    return hits[0]["account_id"]


def test_weights_add_up_to_100():
    total = (config.WEIGHT_STREET_EXACT + config.WEIGHT_ZIP_EXACT + config.WEIGHT_CITY
             + config.WEIGHT_NAME_MAX + config.WEIGHT_PHONE + config.WEIGHT_ADMIN)
    assert total == 100


def test_same_address_alone_reaches_the_match_cutoff():
    """Street + zip + city = 65: the same building is the same facility."""
    assert config.WEIGHT_STREET_EXACT + config.WEIGHT_ZIP_EXACT + config.WEIGHT_CITY == config.THRESHOLD_MATCH


def test_bands():
    assert matcher.band_for(65) == matcher.BAND_MATCH
    assert matcher.band_for(64) == matcher.BAND_PROBABLE
    assert matcher.band_for(50) == matcher.BAND_PROBABLE
    assert matcher.band_for(49) == matcher.BAND_LOOKALIKE
    assert matcher.band_for(30) == matcher.BAND_LOOKALIKE
    assert matcher.band_for(29) == matcher.BAND_UNRELATED


def test_perfect_match_scores_100(result, accounts):
    s = _score(result, "bellhaven-of-maplewood", _id(accounts, "Bellhaven of Maplewood"))
    assert s.total == 100 and s.band == matcher.BAND_MATCH


def test_renamed_facility_still_matches_on_address(result, accounts):
    """A rebrand changes the name, not the building."""
    s = _score(result, "willow-creek", _id(accounts, "Sunny Acres Retirement Home"))
    assert s.band == matcher.BAND_MATCH and s.parts["street"] == 40 and s.parts["name"] < 10


def test_po_box_account_is_only_probable(result, accounts):
    """Everything matches except the street, so a person should decide."""
    s = _score(result, "ashtabula", _id(accounts, "Bellhaven of Ashtabula"))
    assert s.total == 60 and s.band == matcher.BAND_PROBABLE and s.parts["street"] == 0


def test_lookalikes_never_reach_probable(result, accounts):
    """Same town and a similar name, but a different building."""
    union = _score(result, "union-square", _id(accounts, "Union Square Senior Living"))
    maple = _score(result, "bellhaven-of-maplewood", _id(accounts, "Maplewood Senior Care Center"))
    assert union.band == matcher.BAND_LOOKALIKE and maple.band == matcher.BAND_LOOKALIKE


def test_same_name_in_another_state_scores_zero(result, accounts):
    """'Amberly Manor' in Colorado is not 'Amberly Manor' in Hudson, Ohio."""
    s = _score(result, "amberly-manor", _id(accounts, "Amberly Manor"))
    assert s.total == 0


def test_swapped_zip_gets_partial_credit(result, accounts):
    s = _score(result, "portsmouth", _id(accounts, "Bellhaven of Portsmouth"))
    assert s.parts["zip"] == config.WEIGHT_ZIP_SWAPPED and s.band == matcher.BAND_MATCH


def test_score_gaps_keep_cutoffs_away_from_any_real_pair(result):
    """No pair sits near a cut-off: the bands are separated by empty gaps."""
    totals = [s.total for s in result.scores]
    assert not [t for t in totals if 39 <= t <= 59]   # gap around the 50 cut-off
    assert not [t for t in totals if 61 <= t <= 70]   # gap around the 65 cut-off
    assert not [t for t in totals if 20 <= t <= 34]   # gap around the 30 cut-off
