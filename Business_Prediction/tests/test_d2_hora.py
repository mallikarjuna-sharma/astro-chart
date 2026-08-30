"""Tests for the D2 (Hora) wealth-flow evidence layer:
  - jyotish.astro.compute_d2_hora_sign / compute_d2_hora_chart (in-house
    D2 construction, since D2 was previously not computed anywhere in the
    repo)
  - Business_Prediction.business_determination.house_evidence
    ._d2_hora_positions_from_payload / _d2_native_house_evidence
  - the wealth-flow-caution contradiction check added to contradictions.py

Uses the same duck-typed minimal stand-in payload approach as
test_legal_risk.py's _LegalRiskPayload -- only the attributes each
function under test actually reads are set.
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from jyotish.astro import compute_d2_hora_sign, compute_d2_hora_chart
from Business_Prediction.business_determination.house_evidence import (
    _d2_hora_positions_from_payload,
    _d2_native_house_evidence,
)
from Business_Prediction.business_determination.contradictions import _contradiction_penalties


class _D2Payload:
    def __init__(self, house_lords=None, planet_house=None, planet_dignities=None,
                 divisional_charts=None, planets_d1=None):
        self.dob = "1990-05-15"
        self.house_lords = house_lords or {}
        self.planet_house = planet_house or {}
        self.planet_dignities = planet_dignities or {}
        self.divisional_charts = divisional_charts or {}
        self.planets_d1 = planets_d1 or {}


# ---------------------------------------------------------------------------
# jyotish.astro.compute_d2_hora_sign / compute_d2_hora_chart
# ---------------------------------------------------------------------------

def test_odd_sign_first_half_is_sun_hora_leo():
    # Aries (odd) 0-15deg -> Leo (Sun's Hora).
    assert compute_d2_hora_sign("Aries", 5.0) == "Leo"


def test_odd_sign_second_half_is_moon_hora_cancer():
    # Aries (odd) 15-30deg -> Cancer (Moon's Hora).
    assert compute_d2_hora_sign("Aries", 20.0) == "Cancer"


def test_even_sign_first_half_is_moon_hora_cancer():
    # Taurus (even) 0-15deg -> Cancer (Moon's Hora), reversed vs odd signs.
    assert compute_d2_hora_sign("Taurus", 5.0) == "Cancer"


def test_even_sign_second_half_is_sun_hora_leo():
    # Taurus (even) 15-30deg -> Leo (Sun's Hora).
    assert compute_d2_hora_sign("Taurus", 20.0) == "Leo"


def test_boundary_degree_15_is_second_half():
    assert compute_d2_hora_sign("Aries", 15.0) == "Cancer"


def test_unknown_sign_returns_empty_string():
    assert compute_d2_hora_sign("NotASign", 10.0) == ""


def test_compute_d2_hora_chart_builds_flat_planet_signs():
    planets_d1 = {
        "Sun": {"sign": "Aries", "degree": 5.0},      # -> Leo
        "Moon": {"sign": "Aries", "degree": 20.0},     # -> Cancer
        "Mercury": {"sign": "Taurus"},                  # missing degree -> skipped
    }
    chart = compute_d2_hora_chart(planets_d1)
    assert chart["Sun"]["sign"] == "Leo"
    assert chart["Moon"]["sign"] == "Cancer"
    assert "Mercury" not in chart
    assert "Lagna" not in chart  # no lagna_sign passed


# ---------------------------------------------------------------------------
# house_evidence._d2_hora_positions_from_payload
# ---------------------------------------------------------------------------

def test_positions_prefer_upstream_divisional_charts():
    payload = _D2Payload(
        divisional_charts={"D2_hora": {"Jupiter": "Cancer", "Venus": "Leo"}},
        planets_d1={"Jupiter": {"sign": "Gemini", "degree": 10.0}},  # would differ if computed
    )
    positions = _d2_hora_positions_from_payload(payload)
    assert positions["Jupiter"] == "Cancer"
    assert positions["Venus"] == "Leo"


def test_positions_fall_back_to_in_house_computation_when_no_upstream_d2():
    payload = _D2Payload(
        planets_d1={
            "Jupiter": {"sign": "Cancer", "degree": 5.0},  # even sign, first half -> Cancer
            "Venus": {"sign": "Cancer", "degree": 20.0},    # even sign, second half -> Leo
        },
    )
    positions = _d2_hora_positions_from_payload(payload)
    assert positions["Jupiter"] == "Cancer"
    assert positions["Venus"] == "Leo"


def test_positions_missing_data_graceful_degradation():
    payload = _D2Payload()  # no divisional_charts, no planets_d1
    assert _d2_hora_positions_from_payload(payload) == {}


# ---------------------------------------------------------------------------
# house_evidence._d2_native_house_evidence
# ---------------------------------------------------------------------------

_H2_H11_HOUSE_LORDS = {
    "1": "Mercury", "2": "Venus", "3": "Mars", "4": "Moon",
    "5": "Sun", "6": "Mercury", "7": "Venus", "8": "Mars",
    "9": "Jupiter", "10": "Saturn", "11": "Saturn", "12": "Jupiter",
}


def test_h2_lord_in_moon_hora_is_favorable():
    payload = _D2Payload(
        house_lords=_H2_H11_HOUSE_LORDS,
        divisional_charts={"D2_hora": {"Venus": "Cancer"}},  # H2 lord = Venus
    )
    results = _d2_native_house_evidence(payload)
    matches = [n for w, n in results if "H2" in n and w > 0]
    assert matches, f"expected a positive H2/Moon-Hora finding, got {results}"
    assert "Moon's Hora" in matches[0]


def test_h11_lord_in_sun_hora_is_cautionary():
    payload = _D2Payload(
        house_lords=_H2_H11_HOUSE_LORDS,
        divisional_charts={"D2_hora": {"Saturn": "Leo"}},  # H11 lord = Saturn
    )
    results = _d2_native_house_evidence(payload)
    matches = [(w, n) for w, n in results if "H11" in n]
    assert matches, f"expected an H11 finding, got {results}"
    weight, note = matches[0]
    assert weight < 0
    assert "Sun's Hora" in note


def test_wealth_significators_jupiter_venus_moon_scored():
    payload = _D2Payload(
        house_lords=_H2_H11_HOUSE_LORDS,
        divisional_charts={"D2_hora": {"Jupiter": "Cancer", "Venus": "Leo", "Moon": "Cancer"}},
    )
    results = _d2_native_house_evidence(payload)
    notes = " | ".join(n for _, n in results)
    assert "Jupiter" in notes and "Venus" in notes and "Moon" in notes


def test_missing_data_graceful_degradation_returns_empty_list():
    # No divisional_charts, no planets_d1 -> no D2 positions at all.
    payload = _D2Payload(house_lords=_H2_H11_HOUSE_LORDS)
    assert _d2_native_house_evidence(payload) == []

    # No house_lords -> also empty, even with D2 positions present.
    payload2 = _D2Payload(divisional_charts={"D2_hora": {"Venus": "Cancer"}})
    assert _d2_native_house_evidence(payload2) == []


# ---------------------------------------------------------------------------
# contradictions.py wealth-flow-caution check
# ---------------------------------------------------------------------------

def test_wealth_flow_caution_contradiction_fires_on_sun_hora_dominance():
    # H2 lord (Venus) placed in a kendra/trikona with strong dignity so
    # _house_lord_strength(payload, 2) >= 0.6 (a strong D1 wealth promise),
    # but D2 shows Venus in Sun's Hora (Leo) -> negative D2 net.
    house_lords = dict(_H2_H11_HOUSE_LORDS)
    planet_house = {"Venus": 1, "Saturn": 11, "Mercury": 1, "Mars": 3,
                     "Moon": 4, "Sun": 5, "Jupiter": 9}
    dignities = {"Venus": "OWN"}
    payload = _D2Payload(
        house_lords=house_lords,
        planet_house=planet_house,
        planet_dignities=dignities,
        divisional_charts={"D2_hora": {"Venus": "Leo", "Saturn": "Leo"}},
    )
    significators = {"heuristic_relative_strength_0_100": 70}
    d24_status = {"status": "NO_DATA", "factor": 1.0}
    kp10 = {"status": "NO_DATA"}

    penalties = _contradiction_penalties(payload, significators, d24_status, kp10)
    wealth_flags = [p for p in penalties if "Wealth flow caution" in p["note"]]
    assert wealth_flags, f"expected a wealth-flow-caution contradiction, got {penalties}"
    assert wealth_flags[0]["mode"] == "business"


def test_wealth_flow_caution_does_not_fire_when_no_d2_data():
    house_lords = dict(_H2_H11_HOUSE_LORDS)
    planet_house = {"Venus": 1, "Saturn": 11, "Mercury": 1}
    dignities = {"Venus": "OWN"}
    payload = _D2Payload(house_lords=house_lords, planet_house=planet_house,
                          planet_dignities=dignities)  # no divisional_charts/planets_d1
    significators = {"heuristic_relative_strength_0_100": 70}
    d24_status = {"status": "NO_DATA", "factor": 1.0}
    kp10 = {"status": "NO_DATA"}

    penalties = _contradiction_penalties(payload, significators, d24_status, kp10)
    wealth_flags = [p for p in penalties if "Wealth flow caution" in p["note"]]
    assert not wealth_flags
