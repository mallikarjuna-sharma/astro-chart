"""Tests for Business_Prediction.business_determination.legal_risk
(discrete named legal-dispute/litigation-risk detection layer).

Uses the same duck-typed minimal stand-in payload approach as
test_yogas.py's _YogaPayload -- only house_lords, planet_house,
planet_dignities (and optionally active_transit_flags) are required.
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_determination.legal_risk import detect_legal_dispute_risk


class _LegalRiskPayload:
    def __init__(self, house_lords, planet_house, planet_dignities=None, active_transit_flags=None):
        self.dob = "1990-05-15"
        self.house_lords = house_lords
        self.planet_house = planet_house
        self.planet_dignities = planet_dignities or {}
        self.active_transit_flags = active_transit_flags or []


class _MissingDataPayload:
    """No house_lords / planet_house at all."""
    pass


def test_mars_saturn_7th_house_combination_flags_litigation_risk():
    # Mars and Saturn conjunct in house 7 (contracts/other party).
    house_lords = {
        "1": "Mercury", "2": "Venus", "3": "Mars", "4": "Moon",
        "5": "Sun", "6": "Mercury", "7": "Venus", "8": "Mars",
        "9": "Jupiter", "10": "Saturn", "11": "Saturn", "12": "Jupiter",
    }
    planet_house = {
        "Mars": 7, "Saturn": 7, "Venus": 1, "Mercury": 1,
        "Moon": 4, "Sun": 5, "Jupiter": 9, "Rahu": 3, "Ketu": 9,
    }
    dignities = {"Mars": "OWN", "Saturn": "OWN"}
    payload = _LegalRiskPayload(house_lords, planet_house, dignities)

    risks = detect_legal_dispute_risk(payload)
    ms = [r for r in risks if r["risk_type"] == "LITIGATION_RISK" and
          set(r["planets_involved"]) == {"Mars", "Saturn"}]
    assert ms, f"expected a Mars-Saturn litigation risk, got {risks}"
    assert ms[0]["confidence_tier"] == "STRONG"
    assert 7 in ms[0]["houses_involved"]
    assert ms[0]["relation" if "relation" in ms[0] else "risk_type"]  # sanity: dict has expected fields
    assert "effect" in ms[0] and "detail" in ms[0]

    # 7th lord (Venus) is also afflicted since Venus sits in H1 with
    # Mercury -- not by Mars/Saturn -- so no contract-dispute flag from
    # that check specifically here; but the 6th-lord/7th-lord check may or
    # may not fire depending on house_lords -- not asserted either way.


def test_rahu_ketu_on_6_7_12_axis_flags_litigation_risk():
    # Rahu placed in house 7 (partnership/contracts), Ketu in house 1
    # (opposite axis, not itself 6/7/12, but Rahu alone on H7 qualifies).
    house_lords = {
        "1": "Mercury", "2": "Venus", "3": "Mars", "4": "Moon",
        "5": "Sun", "6": "Mercury", "7": "Venus", "8": "Mars",
        "9": "Jupiter", "10": "Saturn", "11": "Saturn", "12": "Jupiter",
    }
    planet_house = {
        "Rahu": 7, "Ketu": 1, "Venus": 4, "Mercury": 4,
        "Mars": 3, "Moon": 4, "Sun": 5, "Jupiter": 9, "Saturn": 10,
    }
    dignities = {}
    payload = _LegalRiskPayload(house_lords, planet_house, dignities,
                                 active_transit_flags=["RAHU_KETU_AXIS_MAJOR_CHANGE"])

    risks = detect_legal_dispute_risk(payload)
    rk = [r for r in risks if r["risk_type"] == "LITIGATION_RISK" and "Rahu" in r["planets_involved"]]
    assert rk, f"expected a Rahu-Ketu axis litigation risk, got {risks}"
    assert 7 in rk[0]["houses_involved"]
    assert "RAHU_KETU_AXIS_MAJOR_CHANGE" in rk[0]["detail"]


def test_clean_chart_returns_empty_list_no_error():
    # No malefics on 6/7/8/12, no Mars-Saturn combination, no 6th/7th lord
    # exchange, 7th lord unafflicted.
    house_lords = {
        "1": "Jupiter", "2": "Saturn", "3": "Saturn", "4": "Jupiter",
        "5": "Mars", "6": "Venus", "7": "Mercury", "8": "Moon",
        "9": "Sun", "10": "Sun", "11": "Mercury", "12": "Mars",
    }
    planet_house = {
        "Jupiter": 1, "Saturn": 2, "Mars": 5, "Venus": 6,
        "Mercury": 11, "Moon": 8, "Sun": 9, "Rahu": 4, "Ketu": 10,
    }
    dignities = {}
    payload = _LegalRiskPayload(house_lords, planet_house, dignities)

    risks = detect_legal_dispute_risk(payload)
    assert risks == []


def test_missing_data_payload_returns_empty_list_no_error():
    payload = _MissingDataPayload()
    risks = detect_legal_dispute_risk(payload)
    assert risks == []

    # Also verify passing None outright doesn't raise.
    risks_none = detect_legal_dispute_risk(None)
    assert risks_none == []
