"""Tests for the dedicated foreign/cross-border business viability check
bundle (Business_Prediction/business_determination/foreign_business.py).
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_determination.foreign_business import (
    foreign_business_viability_evidence,
)
from Business_Prediction.business_determination.sectors import sector_score
from jyotish.d10_archetypes import ARCHETYPE_NAMES


class _ForeignPayload:
    def __init__(self, house_lords=None, planet_house=None, planet_dignities=None):
        self.house_lords = house_lords or {}
        self.planet_house = planet_house or {}
        self.planet_dignities = planet_dignities or {}
        self.planets_d1 = {}
        self.sav_points_houses = {}
        self.darakaraka = ""


def test_strong_12th_9th_lord_and_well_placed_rahu_is_positive():
    # 12th lord Jupiter exalted/kendra-trikona placed; 9th lord Venus
    # kendra placed; Rahu in H7 (business-relevant AND foreign-connection
    # house) with Rahu conjunct the 9th lord.
    payload = _ForeignPayload(
        house_lords={"12": "Jupiter", "9": "Venus", "1": "Mars"},
        planet_house={"Jupiter": 1, "Venus": 7, "Rahu": 7},
        planet_dignities={"Jupiter": "EXALTED", "Venus": "OWN", "Rahu": ""},
    )
    results = foreign_business_viability_evidence(payload)
    assert results, "expected at least one citation for a strong foreign-business chart"
    assert all(r["polarity"] in ("POSITIVE", "NEGATIVE") for r in results)
    assert any(r["polarity"] == "POSITIVE" for r in results)
    assert not any(r["polarity"] == "NEGATIVE" for r in results)
    # weights stay in the modest-to-moderate range this bundle promises
    for r in results:
        assert abs(r["weight"]) <= 6.0


def test_afflicted_12th_lord_shows_caution_not_silently_dropped():
    payload = _ForeignPayload(
        house_lords={"12": "Saturn", "9": "Mars"},
        planet_house={"Saturn": 8, "Mars": 6},
        planet_dignities={"Saturn": "DEBILITATED", "Mars": "NEUTRAL"},
    )
    results = foreign_business_viability_evidence(payload)
    negative = [r for r in results if r["polarity"] == "NEGATIVE"]
    assert negative, f"expected a caution citation for a debilitated 12th lord, got {results}"
    assert "12" in negative[0]["note"]
    assert "foreign" in negative[0]["note"].lower() or "cross-border" in negative[0]["note"].lower()


def test_no_notable_foreign_indicators_returns_minimal_or_empty():
    # Neutral placements everywhere, Rahu in a house unrelated to foreign
    # connections or business relevance (H4) -- nothing notable to cite.
    # House 2 is neither kendra/trikona, upachaya, nor dusthana -> a
    # genuinely "unremarkable" (base=0.45, below the >=0.6 positive
    # threshold and not a dusthana-affliction case) lord placement for
    # both the 12th and 9th lord; Rahu in H4 is neither business-relevant
    # nor a foreign-connection house, and shares no house/aspect with
    # either lord -- nothing here should be notable.
    payload = _ForeignPayload(
        house_lords={"12": "Mercury", "9": "Moon"},
        planet_house={"Mercury": 2, "Moon": 2, "Rahu": 4},
        planet_dignities={"Mercury": "NEUTRAL", "Moon": "NEUTRAL", "Rahu": "NEUTRAL"},
    )
    results = foreign_business_viability_evidence(payload)
    assert results == []  # nothing notable -> graceful empty result, not a pile-on


def test_missing_data_degrades_gracefully():
    class _Empty:
        pass
    assert foreign_business_viability_evidence(_Empty()) == []

    payload = _ForeignPayload()  # empty house_lords/planet_house
    assert foreign_business_viability_evidence(payload) == []


# --- D4 (Chaturthamsha) corroboration of the 12th lord (item 35) ---

def test_d4_corroboration_positive_when_12th_lord_exalted_in_d4():
    # Jupiter (12th lord) at Cancer 1deg -> D4 sign = Cancer (see
    # jyotish.astro.compute_d4_chaturthamsha_sign), where Jupiter is
    # EXALTED -- a genuine D4 corroboration.
    payload = _ForeignPayload(
        house_lords={"12": "Jupiter"},
        planet_house={"Jupiter": 1},
        planet_dignities={"Jupiter": "NEUTRAL"},
    )
    payload.planets_d1 = {"Jupiter": {"sign": "Cancer", "degree": 1.0}}
    results = foreign_business_viability_evidence(payload)
    d4_results = [r for r in results if r["source"] == "foreign_business_d4"]
    assert len(d4_results) == 1
    assert d4_results[0]["polarity"] == "POSITIVE"
    assert "EXALTED" in d4_results[0]["note"]
    assert "modern extension" in d4_results[0]["note"].lower()


def test_d4_corroboration_negative_when_12th_lord_debilitated_in_d4():
    # Jupiter (12th lord) at Capricorn 1deg -> D4 sign = Capricorn, where
    # Jupiter is DEBILITATED.
    payload = _ForeignPayload(
        house_lords={"12": "Jupiter"},
        planet_house={"Jupiter": 1},
        planet_dignities={"Jupiter": "NEUTRAL"},
    )
    payload.planets_d1 = {"Jupiter": {"sign": "Capricorn", "degree": 1.0}}
    results = foreign_business_viability_evidence(payload)
    d4_results = [r for r in results if r["source"] == "foreign_business_d4"]
    assert len(d4_results) == 1
    assert d4_results[0]["polarity"] == "NEGATIVE"
    assert "DEBILITATED" in d4_results[0]["note"]


def test_d4_corroboration_absent_without_planets_d1():
    payload = _ForeignPayload(
        house_lords={"12": "Jupiter"},
        planet_house={"Jupiter": 1},
        planet_dignities={"Jupiter": "NEUTRAL"},
    )
    # planets_d1 defaults to {} on _ForeignPayload -- no D4 data derivable.
    results = foreign_business_viability_evidence(payload)
    assert not any(r["source"] == "foreign_business_d4" for r in results)


def test_sector_score_folds_in_foreign_business_bonus_for_import_export():
    payload = _ForeignPayload(
        house_lords={"12": "Jupiter", "9": "Venus", "7": "Mercury"},
        planet_house={"Jupiter": 1, "Venus": 7, "Rahu": 7, "Mercury": 1},
        planet_dignities={"Jupiter": "EXALTED", "Venus": "OWN", "Rahu": "", "Mercury": "OWN"},
    )
    vector = {name: 50.0 for name in ARCHETYPE_NAMES}
    row = sector_score(payload, vector, "import_export_foreign_trade")
    assert "foreign_business_bonus" in row
    assert "foreign_business_notes" in row
    assert row["foreign_business_bonus"] != 0.0
    assert row["foreign_business_notes"], "expected notes to accompany a nonzero bonus"


def test_sector_score_does_not_fold_foreign_bonus_into_unrelated_sector():
    payload = _ForeignPayload(
        house_lords={"12": "Jupiter", "9": "Venus"},
        planet_house={"Jupiter": 1, "Venus": 7, "Rahu": 7},
        planet_dignities={"Jupiter": "EXALTED", "Venus": "OWN", "Rahu": ""},
    )
    vector = {name: 50.0 for name in ARCHETYPE_NAMES}
    row = sector_score(payload, vector, "trading_commerce")
    assert row["foreign_business_bonus"] == 0.0
    assert row["foreign_business_notes"] == []
