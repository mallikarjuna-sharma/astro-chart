"""Tests for Business_Prediction.business_determination.yogas
(discrete named-yoga detection layer).

Uses the same duck-typed minimal stand-in payload approach as
test_business_engine.py's _FakePayload / test_synastry.py's
_SynastryPayload -- only house_lords, planet_house, planet_dignities are
required by yogas.py.
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_engine import compute_business_prediction
from Business_Prediction.business_determination.yogas import detect_business_yogas


class _YogaPayload:
    def __init__(self, house_lords, planet_house, planet_dignities=None):
        self.dob = "1990-05-15"
        self.house_lords = house_lords
        self.planet_house = planet_house
        self.planet_dignities = planet_dignities or {}
        self.sav_points_houses = {"10": 32, "11": 33}
        self.darakaraka = "Saturn"
        self.planet_signs = {"Moon": "Aries", "Sun": "Aries"}
        self.dasha_sequence = [{"lord": "Mercury", "start_age": 0, "end_age": 90}]


def test_clear_raja_yoga_detected():
    # H1 (kendra) lord = Mars, H5 (trikona) lord = Sun, both placed
    # together in house 10 (conjunction) -- classical kendra-trikona
    # Raja Yoga, both planets exalted for a STRONG tier.
    house_lords = {
        "1": "Mars", "2": "Venus", "3": "Mercury", "4": "Moon",
        "5": "Sun", "6": "Mercury", "7": "Venus", "8": "Mars",
        "9": "Jupiter", "10": "Saturn", "11": "Saturn", "12": "Jupiter",
    }
    planet_house = {
        "Mars": 10, "Sun": 10, "Venus": 7, "Mercury": 6,
        "Moon": 4, "Jupiter": 9, "Saturn": 11, "Rahu": 3, "Ketu": 9,
    }
    dignities = {"Mars": "EXALTED", "Sun": "EXALTED"}
    payload = _YogaPayload(house_lords, planet_house, dignities)

    yogas = detect_business_yogas(payload)
    raja = [y for y in yogas if y["yoga_name"] == "Raja Yoga"]
    assert raja, f"expected a Raja Yoga, got {yogas}"
    assert raja[0]["confidence_tier"] == "STRONG"
    assert raja[0]["relation"] == "CONJUNCTION"
    assert set(raja[0]["houses_involved"]) == {1, 5}


def test_clear_dhana_yoga_detected():
    # H2 lord = Jupiter, H11 lord = Venus, mutual 7th-house aspect
    # (six houses apart): Jupiter in house 2, Venus in house 8.
    house_lords = {
        "1": "Mercury", "2": "Jupiter", "3": "Mars", "4": "Moon",
        "5": "Sun", "6": "Mercury", "7": "Mercury", "8": "Mars",
        "9": "Jupiter", "10": "Saturn", "11": "Venus", "12": "Jupiter",
    }
    planet_house = {
        "Jupiter": 2, "Venus": 8, "Mercury": 1, "Mars": 3,
        "Moon": 4, "Sun": 5, "Saturn": 10, "Rahu": 6, "Ketu": 12,
    }
    dignities = {"Jupiter": "OWN", "Venus": "OWN"}
    payload = _YogaPayload(house_lords, planet_house, dignities)

    yogas = detect_business_yogas(payload)
    dhana = [y for y in yogas if y["yoga_name"] == "Dhana Yoga"]
    assert dhana, f"expected a Dhana Yoga, got {yogas}"
    assert dhana[0]["relation"] == "MUTUAL_ASPECT"
    assert set(dhana[0]["houses_involved"]) == {2, 11}


def test_mercury_saturn_rahu_business_combination_detected():
    # Mercury and Rahu conjunct in house 11 (a business-relevant house).
    house_lords = {
        "1": "Mercury", "2": "Venus", "3": "Mars", "4": "Moon",
        "5": "Sun", "6": "Mercury", "7": "Venus", "8": "Mars",
        "9": "Jupiter", "10": "Saturn", "11": "Saturn", "12": "Jupiter",
    }
    planet_house = {
        "Mercury": 11, "Rahu": 11, "Saturn": 6, "Venus": 7,
        "Mars": 3, "Moon": 4, "Sun": 5, "Jupiter": 9, "Ketu": 5,
    }
    dignities = {"Mercury": "OWN"}
    payload = _YogaPayload(house_lords, planet_house, dignities)

    yogas = detect_business_yogas(payload)
    msr = [y for y in yogas if y["yoga_name"] == "Mercury-Saturn-Rahu Business Combination"]
    assert msr, f"expected an MSR combination, got {yogas}"
    assert msr[0]["relation"] == "CONJUNCTION"
    assert 11 in msr[0]["houses_involved"]


def test_chart_with_no_yogas_returns_empty_list_gracefully():
    # Deliberately engineered so no kendra/trikona lord pair, no
    # wealth-house (2/11 vs 2/5/9/11) lord pair, and no Mercury/Saturn/Rahu
    # pair land in conjunction, mutual (6-apart) aspect, or exchange.
    house_lords = {
        "1": "Mars", "2": "Venus", "3": "Mercury", "4": "Moon",
        "5": "Jupiter", "6": "Mercury", "7": "Venus", "8": "Mars",
        "9": "Jupiter", "10": "Saturn", "11": "Saturn", "12": "Jupiter",
    }
    planet_house = {
        "Mars": 2, "Venus": 12, "Mercury": 8, "Moon": 6,
        "Jupiter": 4, "Saturn": 3, "Rahu": 1, "Ketu": 7, "Sun": 5,
    }
    payload = _YogaPayload(house_lords, planet_house, {})

    yogas = detect_business_yogas(payload)
    assert isinstance(yogas, list)
    assert yogas == []


def test_same_bhava_house_but_different_sign_is_not_conjunction():
    # Regression test for a real-chart audit finding (Mallikarjun Sharma,
    # Sagittarius lagna): the Raja Yoga detector previously claimed
    # "H7 (kendra) lord (Mercury, OWN) conjunct H9 (trikona) lord (Sun,
    # DEBILITATED)" -- internally impossible, since a genuine same-sign
    # conjunction (yuti) requires both planets in the SAME rashi, but
    # Mercury-OWN requires Gemini/Virgo while Sun-DEBILITATED requires
    # Libra. The bug: payload.planet_house (bhava/cuspal house numbers,
    # per jyotish/engine_io.py's Bhava Chalit default) can put two
    # planets in the same HOUSE NUMBER while they sit in different SIGNS
    # -- a cuspal-boundary artifact, not a real conjunction. This
    # reproduces that exact scenario: Mercury (H7 lord) and Sun (H9 lord)
    # both land in bhava house 10, but Mercury sits in Gemini (its own
    # sign) and Sun sits in Libra (its debilitation sign) -- two signs
    # that cannot be the same rashi. detect_business_yogas() must not
    # emit a Raja Yoga CONJUNCTION for this H7/H9 pair.
    house_lords = {
        "1": "Jupiter", "2": "Saturn", "3": "Saturn", "4": "Jupiter",
        "5": "Mars", "6": "Venus", "7": "Mercury", "8": "Venus",
        "9": "Sun", "10": "Mercury", "11": "Saturn", "12": "Jupiter",
    }
    planet_house = {
        "Mercury": 10, "Sun": 10, "Mars": 3, "Moon": 4,
        "Venus": 8, "Saturn": 2, "Jupiter": 1, "Rahu": 6, "Ketu": 12,
    }
    dignities = {"Mercury": "OWN", "Sun": "DEBILITATED"}
    payload = _YogaPayload(house_lords, planet_house, dignities)
    payload.planet_signs = {"Mercury": "Gemini", "Sun": "Libra", "Moon": "Aries"}

    yogas = detect_business_yogas(payload)
    raja_h7_h9 = [
        y for y in yogas
        if y["yoga_name"] == "Raja Yoga" and set(y["houses_involved"]) == {7, 9}
    ]
    assert not raja_h7_h9, (
        f"expected no CONJUNCTION Raja Yoga for H7/H9 (same bhava-house, "
        f"different sign, mutually-exclusive dignities), got {raja_h7_h9}"
    )
    # Confirm no yoga anywhere carries this exact contradictory pairing.
    for y in yogas:
        if set(y.get("planets_involved", [])) == {"Mercury", "Sun"} and y["relation"] == "CONJUNCTION":
            raise AssertionError(f"contradictory CONJUNCTION emitted: {y}")


def test_missing_chart_data_returns_empty_list_not_error():
    class _EmptyPayload:
        pass

    yogas = detect_business_yogas(_EmptyPayload())
    assert yogas == []


def test_detect_business_yogas_wired_into_compute_business_prediction():
    house_lords = {
        "1": "Mars", "2": "Venus", "3": "Mercury", "4": "Moon",
        "5": "Sun", "6": "Mercury", "7": "Venus", "8": "Mars",
        "9": "Jupiter", "10": "Saturn", "11": "Saturn", "12": "Jupiter",
    }
    planet_house = {
        "Mars": 10, "Sun": 10, "Venus": 7, "Mercury": 6,
        "Moon": 4, "Jupiter": 9, "Saturn": 11, "Rahu": 3, "Ketu": 9,
    }
    dignities = {"Mars": "EXALTED", "Sun": "EXALTED"}
    payload = _YogaPayload(house_lords, planet_house, dignities)

    result = compute_business_prediction(payload)
    assert "detected_yogas" in result
    assert isinstance(result["detected_yogas"], list)
