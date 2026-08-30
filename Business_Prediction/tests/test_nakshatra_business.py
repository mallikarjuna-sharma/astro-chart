"""Tests for the Janma Nakshatra (birth-star) business-aptitude evidence
layer (Business_Prediction/business_determination/nakshatra_business.py).
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_determination.nakshatra_business import (
    janma_nakshatra_business_evidence,
    NAKSHATRA_BUSINESS_TABLE,
)
from Business_Prediction.business_determination.significators import (
    score_business_significators,
)


class _NakPayload:
    def __init__(self, moon_nakshatra="", house_lords=None, planet_house=None):
        self.moon_nakshatra = moon_nakshatra
        self.house_lords = house_lords or {}
        self.planet_house = planet_house or {}
        self.planet_dignities = {}
        self.sav_points_houses = {}
        self.darakaraka = ""


def test_pushya_native_shows_positive_citation():
    payload = _NakPayload(moon_nakshatra="Pushya")
    results = janma_nakshatra_business_evidence(payload)
    assert len(results) == 1
    rec = results[0]
    assert rec["polarity"] == "POSITIVE"
    assert rec["weight"] > 0
    assert "Pushya" in rec["detail"]
    assert "trade" in rec["effect"].lower() or "commerce" in rec["effect"].lower()


def test_nakshatra_not_in_table_shows_no_citation_gracefully():
    # Ardra has no well-established classical business citation on file --
    # this should be a graceful empty result, not an error.
    payload = _NakPayload(moon_nakshatra="Ardra")
    assert janma_nakshatra_business_evidence(payload) == []


def test_missing_moon_nakshatra_degrades_gracefully():
    payload = _NakPayload(moon_nakshatra="")
    assert janma_nakshatra_business_evidence(payload) == []

    # No attribute at all.
    class _NoNak:
        pass
    assert janma_nakshatra_business_evidence(_NoNak()) == []

    # None value.
    payload_none = _NakPayload(moon_nakshatra=None)
    assert janma_nakshatra_business_evidence(payload_none) == []


def test_all_table_weights_are_modest():
    for nak, entry in NAKSHATRA_BUSINESS_TABLE.items():
        assert 1.0 <= abs(entry["weight"]) <= 2.0, f"{nak} weight out of modest range: {entry['weight']}"


def test_evidence_weight_does_not_dominate_significator_score():
    # Build a payload with no other business evidence at all (empty
    # house_lords/planet_house), so the ONLY ledger entry should be the
    # nakshatra one -- confirms this minor technique never swamps the
    # ledger even when it is the sole contributor.
    payload = _NakPayload(moon_nakshatra="Pushya")
    result = score_business_significators(payload)
    evidence = result.get("evidence") if isinstance(result, dict) else None
    # score_business_significators may return the ledger under a different
    # key depending on version; fall back to scanning for our marker note.
    if evidence is None:
        # search all list-valued entries for our citation
        for v in result.values() if isinstance(result, dict) else []:
            if isinstance(v, list) and any(
                isinstance(it, dict) and it.get("note", "").find("Pushya") >= 0 for it in v
            ):
                evidence = v
                break
    assert evidence is not None, f"could not locate evidence ledger in {result.keys() if isinstance(result, dict) else result}"
    nak_entries = [e for e in evidence if "Pushya" in e.get("note", "")]
    assert nak_entries, f"expected a Pushya citation in the ledger, got {evidence}"
    assert abs(nak_entries[0]["weight"]) <= 2.0
