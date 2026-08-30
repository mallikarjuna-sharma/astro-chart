"""Tests for the D3 (Drekkana) self-effort/courage evidence layer:
  - jyotish.astro.compute_d3_drekkana_sign / compute_d3_drekkana_chart
    (in-house D3 construction, following the exact D2/D7 addition pattern)
  - Business_Prediction.business_determination.house_evidence
    ._d3_drekkana_house_occupancy_from_divisional_charts /
    _d3_native_house_evidence (scoped narrowly to H3, mirroring
    _d7_native_house_evidence's H7-only scope)
  - significators.py wiring of D3 corroboration into the H3-lord evidence
  - contradictions.py's "strong H3 weak H2" check being tempered/
    aggravated by D3

Uses the same duck-typed minimal stand-in payload approach as
test_d2_hora.py._D2Payload -- only the attributes each function under
test actually reads are set.
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from jyotish.astro import compute_d3_drekkana_sign, compute_d3_drekkana_chart
from Business_Prediction.business_determination.house_evidence import (
    _d3_drekkana_house_occupancy_from_divisional_charts,
    _d3_native_house_evidence,
)
from Business_Prediction.business_determination.significators import (
    score_business_significators,
)
from Business_Prediction.business_determination.contradictions import (
    _contradiction_penalties,
)


class _D3Payload:
    def __init__(self, house_lords=None, planet_house=None, planet_dignities=None,
                 divisional_charts=None, sav_points_houses=None, darakaraka=""):
        self.dob = "1990-05-15"
        self.house_lords = house_lords or {}
        self.planet_house = planet_house or {}
        self.planet_dignities = planet_dignities or {}
        self.divisional_charts = divisional_charts or {}
        self.sav_points_houses = sav_points_houses or {}
        self.darakaraka = darakaraka


# ---------------------------------------------------------------------------
# jyotish.astro.compute_d3_drekkana_sign / compute_d3_drekkana_chart
# ---------------------------------------------------------------------------

def test_d3_sign_decanate_boundaries():
    # Aries: 1st decanate (0-10) = Aries itself.
    assert compute_d3_drekkana_sign("Aries", 5) == "Aries"
    # 2nd decanate (10-20) = 5th sign inclusive from Aries = Leo.
    assert compute_d3_drekkana_sign("Aries", 15) == "Leo"
    # 3rd decanate (20-30) = 9th sign inclusive from Aries = Sagittarius.
    assert compute_d3_drekkana_sign("Aries", 25) == "Sagittarius"


def test_d3_sign_wraps_across_zodiac():
    # Taurus 3rd decanate -> 9th sign inclusive from Taurus = Capricorn.
    assert compute_d3_drekkana_sign("Taurus", 25) == "Capricorn"
    # Unknown sign -> empty string, graceful.
    assert compute_d3_drekkana_sign("NotASign", 5) == ""


def test_d3_chart_shape_matches_d7_pattern():
    planets_d1 = {
        "Sun": {"sign": "Aries", "degree": 25.0},
        "Mars": {"sign": "Cancer", "degree": 5.0},
    }
    chart = compute_d3_drekkana_chart(planets_d1, lagna_sign="Aries", lagna_degree=5.0)
    assert chart["Lagna"] == {"sign": "Aries"}
    assert chart["Sun"] == {"sign": "Sagittarius"}
    assert chart["Mars"] == {"sign": "Cancer"}

    # No lagna_sign supplied -> no "Lagna" key, mirrors compute_d2_hora_chart.
    chart_no_lagna = compute_d3_drekkana_chart(planets_d1)
    assert "Lagna" not in chart_no_lagna


# ---------------------------------------------------------------------------
# house_evidence._d3_native_house_evidence
# ---------------------------------------------------------------------------

_H3_HOUSE_LORDS = {
    "1": "Jupiter", "2": "Saturn", "3": "Mars", "4": "Jupiter",
    "5": "Sun", "6": "Venus", "7": "Mars", "8": "Venus",
    "9": "Mercury", "10": "Mercury", "11": "Moon", "12": "Moon",
}


def test_d3_corroborates_confirms_h3_promise():
    # H3 lord Mars placed in D3-H1 (kendra) from an Aries D3-Lagna.
    payload = _D3Payload(
        house_lords=_H3_HOUSE_LORDS,
        divisional_charts={"D3_drekkana": {"Lagna": "Aries", "Mars": "Aries"}},
    )
    results = _d3_native_house_evidence(payload)
    assert results, "expected D3-native evidence to be produced"
    net = sum(w for w, _ in results)
    assert net > 0
    assert any("D3-native" in n and "confirms" in n for _, n in results)


def test_d3_contradicts_weakens_h3_promise():
    # H3 lord Mars placed in D3-H6 (dusthana) from an Aries D3-Lagna.
    payload = _D3Payload(
        house_lords=_H3_HOUSE_LORDS,
        divisional_charts={"D3_drekkana": {"Lagna": "Aries", "Mars": "Virgo"}},
    )
    results = _d3_native_house_evidence(payload)
    assert results, "expected D3-native evidence to be produced"
    net = sum(w for w, _ in results)
    assert net < 0
    assert any("D3-native" in n and "weakens" in n for _, n in results)


def test_d3_missing_data_graceful_degradation():
    # No divisional_charts at all -> no D3 evidence, empty list (not an
    # exception), so callers fall back cleanly to D1-only H3 evidence.
    payload = _D3Payload(house_lords=_H3_HOUSE_LORDS)
    assert _d3_native_house_evidence(payload) == []

    # divisional_charts present but no "Lagna" key (insufficient data) ->
    # also gracefully empty.
    payload2 = _D3Payload(
        house_lords=_H3_HOUSE_LORDS,
        divisional_charts={"D3_drekkana": {"Mars": "Aries"}},
    )
    assert _d3_native_house_evidence(payload2) == []

    # No house_lords -> also empty, even with D3 occupancy present.
    payload3 = _D3Payload(
        divisional_charts={"D3_drekkana": {"Lagna": "Aries", "Mars": "Aries"}},
    )
    assert _d3_native_house_evidence(payload3) == []


# ---------------------------------------------------------------------------
# significators.py wiring
# ---------------------------------------------------------------------------

def test_significators_incorporates_d3_evidence():
    payload = _D3Payload(
        house_lords=_H3_HOUSE_LORDS,
        planet_house={"Mars": 3, "Jupiter": 1, "Saturn": 11, "Venus": 7,
                      "Mercury": 10, "Moon": 4, "Sun": 5},
        divisional_charts={"D3_drekkana": {"Lagna": "Aries", "Mars": "Aries"}},
    )
    result = score_business_significators(payload)
    notes = " | ".join(result["signals"])
    assert "D3-native" in notes, "expected D3 corroboration to surface in significator signals"


# ---------------------------------------------------------------------------
# contradictions.py "strong H3 weak H2" check tempered/aggravated by D3
# ---------------------------------------------------------------------------

_H3_H2_HOUSE_LORDS = {
    "1": "Jupiter", "2": "Saturn", "3": "Mars", "4": "Jupiter",
    "5": "Sun", "6": "Venus", "7": "Mars", "8": "Venus",
    "9": "Mercury", "10": "Mercury", "11": "Moon", "12": "Moon",
}


def _base_strong_h3_weak_h2_payload(divisional_charts=None):
    # Mars (H3 lord) in a kendra with strong dignity -> h3_strength >= 0.6.
    # Saturn (H2 lord) in a dusthana with no strong dignity -> h2_strength < 0.35.
    return _D3Payload(
        house_lords=_H3_H2_HOUSE_LORDS,
        planet_house={"Mars": 1, "Saturn": 8, "Jupiter": 4, "Venus": 7,
                      "Mercury": 10, "Moon": 5, "Sun": 5},
        planet_dignities={"Mars": "OWN"},
        divisional_charts=divisional_charts or {},
    )


def test_contradiction_tempered_when_d3_confirms():
    payload = _base_strong_h3_weak_h2_payload(
        divisional_charts={"D3_drekkana": {"Lagna": "Aries", "Mars": "Aries"}},
    )
    significators = {"heuristic_relative_strength_0_100": 60}
    d24_status = {"status": "NO_DATA", "factor": 1.0}
    kp10 = {"status": "NO_DATA"}

    penalties = _contradiction_penalties(payload, significators, d24_status, kp10)
    h3_flags = [p for p in penalties if "H3" in p["note"] and "H2" in p["note"]]
    assert h3_flags, f"expected a strong-H3-weak-H2 flag, got {penalties}"
    assert "tempered" in h3_flags[0]["note"].lower()
    assert h3_flags[0]["weight"] == 3.5


def test_contradiction_aggravated_when_d3_contradicts():
    payload = _base_strong_h3_weak_h2_payload(
        divisional_charts={"D3_drekkana": {"Lagna": "Aries", "Mars": "Virgo"}},
    )
    significators = {"heuristic_relative_strength_0_100": 60}
    d24_status = {"status": "NO_DATA", "factor": 1.0}
    kp10 = {"status": "NO_DATA"}

    penalties = _contradiction_penalties(payload, significators, d24_status, kp10)
    h3_flags = [p for p in penalties if "H3" in p["note"] and "H2" in p["note"]]
    assert h3_flags, f"expected a strong-H3-weak-H2 flag, got {penalties}"
    assert "aggravated" in h3_flags[0]["note"].lower()
    assert h3_flags[0]["weight"] == 6.5


def test_contradiction_unchanged_when_no_d3_data():
    # No divisional_charts at all -> D3 net == 0.0 -> falls back to the
    # original (pre-D3) severity, unchanged from before this feature.
    payload = _base_strong_h3_weak_h2_payload(divisional_charts={})
    significators = {"heuristic_relative_strength_0_100": 60}
    d24_status = {"status": "NO_DATA", "factor": 1.0}
    kp10 = {"status": "NO_DATA"}

    penalties = _contradiction_penalties(payload, significators, d24_status, kp10)
    h3_flags = [p for p in penalties if "H3" in p["note"] and "H2" in p["note"]]
    assert h3_flags, f"expected a strong-H3-weak-H2 flag, got {penalties}"
    assert h3_flags[0]["weight"] == 5
    assert "tempered" not in h3_flags[0]["note"].lower()
    assert "aggravated" not in h3_flags[0]["note"].lower()
