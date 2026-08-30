"""v46 audit fix (items 4/5/6, user-directed methodology decisions):
targeted tests for the three additive disclosures added this round --
KP weighting policy exposure, timing-window event-type signals, and the
Jaimini rasi-drishti neutral-treatment policy. None of these change any
existing net_score/label/verdict computation; each is a new, additive,
inspectable field.
"""
from datetime import date

from Business_Prediction.business_determination.timing import (
    KP_WEIGHTING_POLICY,
    _window_event_type_signals,
    _window_event_type_scores,
    _chara_dasha_window_corroboration,
)
from Business_Prediction.business_determination.jaimini import _jaimini_rasi_drishti_evidence
from Business_Prediction.business_determination.sectors import SECTOR_CALIBRATION_BASIS, sector_score


class TestKpWeightingPolicy:
    def test_policy_declares_six_tiers_in_order(self):
        tiers = [t["tier"] for t in KP_WEIGHTING_POLICY["tiers"]]
        assert tiers == [
            "0_D1_FOUNDATIONAL",
            "1_D9_D10_CONFIRM_DENY",
            "2_KP_FINAL_ARBITER",
            "3_JAIMINI",
            "3B_CHARA_DASHA",
            "4_TRANSIT_SHADBALA",
        ]

    def test_only_kp_tier_is_override_capable(self):
        roles = {t["tier"]: t["role"] for t in KP_WEIGHTING_POLICY["tiers"]}
        assert roles["2_KP_FINAL_ARBITER"] == "CONDITIONAL_OVERRIDE"
        assert roles["1_D9_D10_CONFIRM_DENY"] != "CONDITIONAL_OVERRIDE"
        assert roles["3_JAIMINI"] == "ADDITIVE"
        assert roles["4_TRANSIT_SHADBALA"] == "ADDITIVE"


class TestWindowEventTypeSignals:
    def test_house_7_flags_partnering_only(self):
        signals = _window_event_type_signals({7})
        assert signals == {"partnering": True}

    def test_house_1_and_11_flags_starting_and_expanding(self):
        signals = _window_event_type_signals({1, 11})
        assert signals == {"starting_or_launching": True, "expanding_or_scaling": True}

    def test_no_matching_houses_returns_empty_dict(self):
        assert _window_event_type_signals({4, 5}) == {}

    def test_house_8_flags_investing_borrowing_and_exiting(self):
        signals = _window_event_type_signals({8})
        assert signals == {
            "investing_or_capital_deployment": True,
            "borrowing": True,
            "exiting_or_closing": True,
        }


class TestWindowEventTypeScores:
    def test_strong_dignity_ad_lord_scores_positive_on_touched_events(self):
        dignities = {"Jupiter": "EXALTED"}
        scores = _window_event_type_scores("Jupiter", "Saturn", {11}, set(), dignities)
        assert scores == {"expanding_or_scaling": 6.0}

    def test_debilitated_md_lord_scores_negative_on_touched_events(self):
        dignities = {"Saturn": "DEBILITATED"}
        scores = _window_event_type_scores("Jupiter", "Saturn", set(), {7}, dignities)
        assert scores == {"partnering": -6.0}

    def test_both_lords_touching_same_event_sum(self):
        dignities = {"Jupiter": "EXALTED", "Mercury": "EXALTED"}
        scores = _window_event_type_scores("Jupiter", "Mercury", {8}, {6}, dignities)
        # AD lord Jupiter rules H8 (investing/borrowing/exiting event
        # houses), MD lord Mercury rules H6 (borrowing) -- "borrowing" is
        # touched by BOTH, so its score sums to +12; the others only by AD.
        assert scores["borrowing"] == 12.0
        assert scores["investing_or_capital_deployment"] == 6.0
        assert scores["exiting_or_closing"] == 6.0

    def test_untouched_event_absent_not_zero(self):
        dignities = {"Jupiter": "NEUTRAL"}
        scores = _window_event_type_scores("Jupiter", "Saturn", {11}, set(), dignities)
        assert "partnering" not in scores

    def test_neutral_dignity_scores_zero_but_present(self):
        dignities = {"Jupiter": "NEUTRAL"}
        scores = _window_event_type_scores("Jupiter", "Saturn", {11}, set(), dignities)
        assert scores["expanding_or_scaling"] == 0.0


class TestCharaDashaWindowCorroboration:
    def test_strong_dignity_overlap_adds_small_bonus(self):
        # Aries' lord Mars sits in Aries (own sign, STRONG_DIGNITY here via
        # dignities dict), and the calendar entry fully overlaps the window.
        calendar = [{"sign": "Aries", "start": "2020-01-01", "end": "2025-01-01", "antardashas": []}]
        dignities = {"Mars": "OWN"}
        net, notes = _chara_dasha_window_corroboration(
            calendar, date(2021, 1, 1), date(2022, 1, 1), {}, dignities,
        )
        assert net == 3.0
        assert notes and "Aries" in notes[0]

    def test_debilitated_overlap_gives_mild_caution(self):
        calendar = [{"sign": "Cancer", "start": "2020-01-01", "end": "2025-01-01", "antardashas": []}]
        dignities = {"Moon": "DEBILITATED"}
        net, notes = _chara_dasha_window_corroboration(
            calendar, date(2021, 1, 1), date(2022, 1, 1), {}, dignities,
        )
        assert net == -3.0

    def test_no_overlap_gives_zero(self):
        calendar = [{"sign": "Aries", "start": "2030-01-01", "end": "2035-01-01", "antardashas": []}]
        dignities = {"Mars": "OWN"}
        net, notes = _chara_dasha_window_corroboration(
            calendar, date(2021, 1, 1), date(2022, 1, 1), {}, dignities,
        )
        assert net == 0.0 and notes == []

    def test_prefers_the_more_specific_antardasha_over_mahadasha(self):
        calendar = [{
            "sign": "Aries",
            "start": "2020-01-01",
            "end": "2025-01-01",
            "antardashas": [
                {"sign": "Taurus", "start": "2020-01-01", "end": "2021-06-01"},
                {"sign": "Gemini", "start": "2021-06-01", "end": "2025-01-01"},
            ],
        }]
        # Window falls almost entirely inside the Gemini antardasha.
        dignities = {"Mercury": "EXALTED"}
        net, notes = _chara_dasha_window_corroboration(
            calendar, date(2021, 7, 1), date(2022, 7, 1), {}, dignities,
        )
        assert net == 3.0
        assert "Gemini" in notes[0]


class TestJaiminiNeutralPolicy:
    def test_neutral_planet_logged_not_silently_dropped(self):
        # Leo casts rasi drishti onto Aries (H7 sign for Aries lagna) per
        # the classical movable/fixed rule -- verified directly against
        # Stream_Determination.stream_scoring._rasi_drishti_targets.
        class FakePayload:
            lagna_sign = "Aries"
            planet_signs = {"Mars": "Leo"}
            house_lords = {}
            planet_dignities = {}
            planet_house = {}

        # Monkeypatch the benefic/malefic split to exclude Mars from BOTH
        # sets, directly exercising the NEUTRAL branch regardless of this
        # repo's real classification of Mars.
        import Business_Prediction.business_determination.jaimini as jaimini_mod

        original = jaimini_mod._effective_benefic_malefic_sets
        jaimini_mod._effective_benefic_malefic_sets = lambda payload: (set(), set())
        try:
            net, notes = _jaimini_rasi_drishti_evidence(FakePayload(), reference_house=7)
        finally:
            jaimini_mod._effective_benefic_malefic_sets = original

        assert net == 0.0
        assert len(notes) == 1 and "NEUTRAL" in notes[0]


class TestSectorCalibrationBasis:
    def test_calibration_basis_declares_not_fit_to_outcome_data(self):
        assert SECTOR_CALIBRATION_BASIS["calibrated_against_outcome_data"] is False
        names = {c["name"] for c in SECTOR_CALIBRATION_BASIS["components"]}
        assert "archetype_component_blend_weight" in names
        assert "per_sector_archetype_weights" in names

    def test_sector_score_result_carries_calibration_basis(self):
        class FakePayload:
            planet_dignities = {}
            planet_house = {}
            house_lords = {}
            planet_signs = {}

        result = sector_score(FakePayload(), {}, "trading_commerce")
        assert result["calibration_basis"] is SECTOR_CALIBRATION_BASIS
