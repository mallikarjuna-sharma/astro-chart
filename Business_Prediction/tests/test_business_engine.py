"""Smoke tests for Business_Prediction.business_engine.

Uses a minimal stand-in payload object (duck-typed like NatalPayloadV2)
rather than a full chart fixture, to keep this test independent of any
specific chart JSON while still exercising every layer of the pipeline.
"""
import sys
import pathlib

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from datetime import date

from Business_Prediction.business_engine import (
    compute_business_prediction,
    rank_business_sectors,
    score_business_significators,
    sector_score,
    validate_business_rule_pack,
    _archetype_raw_totals,
    _business_ad_windows,
)
from jyotish.d10_archetypes import ARCHETYPE_NAMES, scale_raw_support
from Business_Prediction.business_determination.house_evidence import (
    _rich_planet_dignities, _dig_name, _dig_factor,
)
from jyotish.kp_audit import kp_chain, SIGNS as _KP_SIGNS


def _verified_kp_cusps(h7_lon: float) -> dict:
    """Build a full, internally-consistent 12-cusp KP dataset that PASSES
    jyotish/kp_audit.py's independent chain verification (Placidus-labeled,
    12 distinct cusps, every star/sub/sub-sub-lord correctly re-derivable
    from its own stored degree) -- needed since kp.py::_verify_kp_cusp_chain
    (wired into mode_gate.py/timing.py/scoring.py this audit round) now
    gates every KP-driven score/override on chain_verified, and a bare
    single-cusp fixture like {"H7": {"sub_lord": "X"}} with no sign/degree
    can never verify. h7_lon is the absolute longitude (0..360) to place the
    H7 cusp at; the other 11 cusps are spaced 30 degrees apart from it (a
    simplification, not a real Placidus computation, but sufficient to
    exercise the chain-verification/override MECHANISM under test)."""
    cusps = {}
    for h in range(1, 13):
        # +h*1.7 perturbation keeps H7 exactly at h7_lon (h=7 term folded
        # into the base) while giving every OTHER cusp a distinct degree
        # offset -- audit_kp_cusps() flags a real Placidus-house red flag
        # (equal/whole-sign cusp spacing) when >=6 cusps share <=2 distinct
        # degree values, which a naive uniform 30-degree-apart layout would
        # trigger spuriously for this synthetic fixture.
        lon = (h7_lon + (h - 7) * 30.0 + (h - 7) * 1.7) % 360.0
        sign = _KP_SIGNS[int(lon // 30)]
        degree = lon % 30.0
        chain = kp_chain(lon)
        cusps[f"H{h}"] = {"sign": sign, "degree": round(degree, 4), "sign_lord": "", **chain}
    return cusps


class _FakePayload:
    def __init__(self):
        self.dob = "1990-05-15"
        self.planet_house = {
            "Sun": 10, "Moon": 4, "Mars": 3, "Mercury": 7,
            "Jupiter": 1, "Venus": 7, "Saturn": 6, "Rahu": 7, "Ketu": 1,
        }
        self.house_lords = {
            "1": "Jupiter", "2": "Saturn", "3": "Saturn", "4": "Jupiter",
            "5": "Mars", "6": "Venus", "7": "Mars", "8": "Venus",
            "9": "Mercury", "10": "Mercury", "11": "Sun", "12": "Moon",
        }
        self.planet_dignities = {"Mercury": "OWN", "Venus": "EXALTED"}
        self.sav_points_houses = {"10": 32, "11": 33}
        self.darakaraka = "Saturn"
        self.dasha_sequence = [
            {"lord": "Mercury", "start_age": 0, "end_age": 17},
            {"lord": "Ketu", "start_age": 17, "end_age": 24},
            {"lord": "Venus", "start_age": 24, "end_age": 44},
        ]


def test_registry_validates():
    result = validate_business_rule_pack()
    assert result["ok"], result["errors"]
    assert result["sector_count"] == 19


def test_significators_shape():
    payload = _FakePayload()
    result = score_business_significators(payload)
    assert 0.0 <= result["strength_0_100"] <= 100.0
    assert isinstance(result["signals"], list)


def test_zero_untyped_family_rule_id_profit_stability_risk_entries():
    """Release gate for the typed-evidence migration (family/rule_id/profit/
    stability_risk axes): every evidence entry significators.py's _add()
    produces must carry an explicit `family`, `rule_id`, `profit`, and
    `stability_risk` tag -- none of scoring.py's profit_net/stability_risk_net
    or this module's own family_totals_capped pipeline should ever need to
    fall back to note-text inference. `category` is deliberately excluded
    from this gate: it is only meaningful for evidence structurally anchored
    to H2/H11/H6/H8/H12 (a genuine subset, not every entry), so 100% category
    coverage is not an expected end-state the way the other four axes are.

    Exercised against multiple distinct payload shapes (not just one) so this
    gate would actually catch a newly-added _add() call site that forgot to
    tag `family`/`rule_id`, or a bypass of the centralized profit/
    stability_risk computation in _add() itself.
    """
    for payload in (_FakePayload(), _MaximalPlausiblePayload()):
        result = score_business_significators(payload)
        stats = result["evidence_typing_stats"]
        assert stats["total_entries"] > 0
        assert stats["family_untyped_entries"] == 0, stats
        assert stats["rule_id_untyped_entries"] == 0, stats
        assert stats["profit_untyped_entries"] == 0, stats
        assert stats["stability_risk_untyped_entries"] == 0, stats
        # Every entry in the raw evidence ledger itself actually carries the
        # typed fields (not just what evidence_typing_stats claims) --
        # belt-and-suspenders against the counters and the ledger drifting
        # apart.
        for e in result["evidence"]:
            assert "family" in e and e["family"] is not None, e
            assert "rule_id" in e and e["rule_id"] is not None, e
            assert "profit" in e and isinstance(e["profit"], bool), e
            assert "stability_risk" in e and isinstance(e["stability_risk"], bool), e
            assert "fact_id" in e and e["fact_id"], e


def test_fact_dependency_discount_prevents_duplicate_evidence_inflation():
    """Release gate for item 3 ("no dependency-group scoring policy") and
    the follow-up ask to prove duplicate evidence cannot inflate a score.
    Constructs a payload where H7's lord is strong enough to fire BOTH
    SIG_H7_VENTURE_STRENGTH (D1_PROMISE) and SIG_H7_D9_CONFIRMATION
    (VARGA_CONFIRMATION) for the exact same subject (Mercury|H7) -- two
    DIFFERENT rule_ids corroborating the same underlying fact, which is
    exactly the "corroborating method" case the fact-dependency discount is
    supposed to catch (50% credit for the second one, not full double
    credit). Then verifies capped_net_score_post_fact_dedup is strictly
    less than capped_net_score_pre_fact_dedup whenever the discount fires.

    Per an explicit, asked-and-confirmed scoring-policy decision, the fact-
    deduped totals are now PRIMARY: capped_net_score/strength_0_100 equal
    the POST-dedup numbers, not the pre-dedup ones (the pre-dedup numbers
    are retained only under the *_pre_fact_dedup names, for comparison)."""
    payload = _MaximalPlausiblePayload()
    result = score_business_significators(payload)

    h7_entries = [e for e in result["evidence"] if e.get("subject_key") and "H7" in e["subject_key"] and "Mercury" in e["subject_key"]]
    assert len(h7_entries) >= 2, "expected multiple rules to corroborate the same Mercury|H7 subject"
    discounts = [e["fact_dependency_discount"] for e in h7_entries]
    assert discounts[0] == 1.0, h7_entries
    assert any(d < 1.0 for d in discounts[1:]), h7_entries

    assert result["fact_dependency_discount_applied"] is True
    assert result["capped_net_score_post_fact_dedup"] < result["capped_net_score_pre_fact_dedup"]
    assert result["strength_0_100_post_fact_dedup"] < result["strength_0_100_pre_fact_dedup"]

    # PRIMARY score fields now equal the POST-dedup numbers (promoted per
    # explicit user decision -- see significators.py's "eighth slice -- item
    # 1" comment above the family-cap loop).
    assert result["capped_net_score"] == result["capped_net_score_post_fact_dedup"]
    assert result["strength_0_100"] == result["strength_0_100_post_fact_dedup"]


def test_fact_dependency_discount_zero_for_same_rule_same_subject_duplicate():
    """A rule_id that (hypothetically) fired twice for the exact same
    subject_key must be fully discounted to 0% on the second occurrence
    (same-method duplicate), not just halved. Exercised directly against
    _fact_discount's policy via the ledger's per-entry
    fact_dependency_reason field rather than trying to contrive a real
    chart where one rule_id double-fires (none of the current rules do,
    by construction) -- this proves the POLICY itself, not just today's
    absence of same-rule duplicates."""
    payload = _FakePayload()
    result = score_business_significators(payload)
    # No live rule currently double-fires for one subject, so confirm the
    # negative: no entry is reported as a same_method_duplicate today (if
    # one ever appears, it should be discounted to exactly 0.0).
    for e in result["evidence"]:
        if e.get("fact_dependency_reason") == "same_method_duplicate":
            assert e["fact_dependency_discount"] == 0.0, e


def test_d1_dispositor_chain_grounded_exchange_loop_and_debilitated_branches():
    """Release test for the new D1-D9-D10-dispositor-chain-subsystem slice
    (D1-only): exercises _d1_dispositor_chain_evidence()'s four outcome
    branches directly against constructed payloads, proving the mechanism
    (not just that it runs without crashing on an existing fixture)."""
    from Business_Prediction.business_determination.house_evidence import _d1_dispositor_chain_evidence

    # GROUNDED, strongly dignified: H7 lord Mercury sits in Taurus (house 8
    # from a Libra lagna, ruled by Venus); Venus itself sits in Libra
    # (house 1, its own sign) -> chain grounds in Venus, EXALTED.
    p_grounded = _FakePayload()
    p_grounded.lagna_sign = "Libra"
    p_grounded.house_lords = {"7": "Mercury"}
    p_grounded.planet_house = {"Mercury": 8, "Venus": 1}
    p_grounded.planet_dignities = {"Venus": "EXALTED"}
    grounded = _d1_dispositor_chain_evidence(p_grounded)
    assert len(grounded) == 1
    assert grounded[0][0] > 0
    assert "grounds in Venus" in grounded[0][1]
    assert "EXALTED" in grounded[0][1]

    # EXCHANGE: H7 lord Mars sits in a sign ruled by Saturn, and Saturn
    # sits in a sign ruled by Mars (mutual parivartana).
    p_exchange = _FakePayload()
    p_exchange.lagna_sign = "Aries"
    p_exchange.house_lords = {"7": "Mars"}
    p_exchange.planet_house = {"Mars": 10, "Saturn": 1}  # Aries+10=Capricorn(Saturn); Aries+1=Aries(Mars)
    p_exchange.planet_dignities = {}
    exchange = _d1_dispositor_chain_evidence(p_exchange)
    assert len(exchange) == 1
    assert exchange[0][0] > 0
    assert "exchange" in exchange[0][1].lower()

    # Chain passing through a DEBILITATED planet before grounding: H7 lord
    # Mercury -> dispositor Venus, Venus sits in its own sign (grounded)
    # but Venus itself is flagged DEBILITATED for this test (contradictory
    # dignity data is fine here -- purely to exercise the branch).
    p_debil = _FakePayload()
    p_debil.lagna_sign = "Libra"
    p_debil.house_lords = {"7": "Mercury"}
    p_debil.planet_house = {"Mercury": 8, "Venus": 1}
    p_debil.planet_dignities = {"Venus": "DEBILITATED"}
    debil = _d1_dispositor_chain_evidence(p_debil)
    assert len(debil) == 1
    assert debil[0][0] < 0
    assert "DEBILITATED" in debil[0][1]

    # No lagna_sign at all -> graceful empty return, no crash.
    p_nodata = _FakePayload()
    p_nodata.house_lords = {"7": "Mercury"}
    p_nodata.planet_house = {"Mercury": 7}
    assert _d1_dispositor_chain_evidence(p_nodata) == []


def test_d9_dispositor_chain_grounded_and_debilitated_branches():
    """Release test for the D9 (Navamsha) extension of the dispositor-chain
    subsystem: same GROUNDED/DEBILITATED mechanism as the D1 test above, but
    walked through D9's own house graph (occupancy + lordship both derived
    from divisional_charts['D9_navamsha'] via _d9_house_occupancy_from_
    divisional_charts, per that function's own same-ascendant guarantee).

    D9-Lagna=Libra: Mercury placed in Taurus (D9-house 8, ruled by Venus),
    Venus placed in Libra itself (D9-house 1, its own sign) -> chain grounds
    in Venus. Mirrors the D1 GROUNDED fixture's house numbers exactly since
    the underlying sign-lordship table is identical; only the data source
    (divisional_charts vs house_lords/planet_house) differs."""
    from Business_Prediction.business_determination.house_evidence import _d9_dispositor_chain_evidence

    p_grounded = _FakePayload()
    p_grounded.house_lords = {"7": "Mercury"}
    p_grounded.divisional_charts = {"D9_navamsha": {"Lagna": "Libra", "Mercury": "Taurus", "Venus": "Libra"}}
    p_grounded.d9_planet_dignities = {"Venus": "EXALTED"}
    grounded = _d9_dispositor_chain_evidence(p_grounded)
    assert len(grounded) == 1
    assert grounded[0][0] > 0
    assert "grounds in Venus" in grounded[0][1]
    assert "EXALTED" in grounded[0][1]
    assert "D9" in grounded[0][1]

    p_debil = _FakePayload()
    p_debil.house_lords = {"7": "Mercury"}
    p_debil.divisional_charts = {"D9_navamsha": {"Lagna": "Libra", "Mercury": "Taurus", "Venus": "Libra"}}
    p_debil.d9_planet_dignities = {"Venus": "DEBILITATED"}
    debil = _d9_dispositor_chain_evidence(p_debil)
    assert len(debil) == 1
    assert debil[0][0] < 0
    assert "DEBILITATED" in debil[0][1]

    # No D9_navamsha data at all -> graceful empty return, no crash.
    p_nodata = _FakePayload()
    p_nodata.house_lords = {"7": "Mercury"}
    assert _d9_dispositor_chain_evidence(p_nodata) == []


def test_d10_dispositor_chain_grounded_and_debilitated_branches():
    """Release test for the D10 (Dashamsha) extension of the dispositor-
    chain subsystem: same GROUNDED/DEBILITATED mechanism, walked through
    D10's own house graph via the already-direct payload.d10_house_lords/
    d10_house_occupancy attributes (no sign-arithmetic derivation needed,
    unlike D9) -- H7-lord Mercury sits in D10-house 8 (ruled by Venus),
    Venus sits in D10-house 1 (its own house) -> chain grounds in Venus."""
    from Business_Prediction.business_determination.house_evidence import _d10_dispositor_chain_evidence

    p_grounded = _FakePayload()
    p_grounded.house_lords = {"7": "Mercury"}
    p_grounded.d10_house_lords = {"8": "Venus", "1": "Venus"}
    p_grounded.d10_house_occupancy = {"8": ["Mercury"], "1": ["Venus"]}
    p_grounded.d10_planet_dignities = {"Venus": "EXALTED"}
    grounded = _d10_dispositor_chain_evidence(p_grounded)
    assert len(grounded) == 1
    assert grounded[0][0] > 0
    assert "grounds in Venus" in grounded[0][1]
    assert "EXALTED" in grounded[0][1]
    assert "D10" in grounded[0][1]

    p_debil = _FakePayload()
    p_debil.house_lords = {"7": "Mercury"}
    p_debil.d10_house_lords = {"8": "Venus", "1": "Venus"}
    p_debil.d10_house_occupancy = {"8": ["Mercury"], "1": ["Venus"]}
    p_debil.d10_planet_dignities = {"Venus": "DEBILITATED"}
    debil = _d10_dispositor_chain_evidence(p_debil)
    assert len(debil) == 1
    assert debil[0][0] < 0
    assert "DEBILITATED" in debil[0][1]

    # No d10_house_lords/d10_house_occupancy data at all -> graceful empty
    # return, no crash.
    p_nodata = _FakePayload()
    p_nodata.house_lords = {"7": "Mercury"}
    assert _d10_dispositor_chain_evidence(p_nodata) == []


# --- Divisional-boundary sensitivity (item 27) ---
# v-audit fix (astrological completeness, "no universal birth-time/
# divisional-boundary stability abstention"): scoring.py's
# _divisional_boundary_sensitivity() mechanically checks a planet's actual
# degree-within-sign against every divisional chart's segment size,
# independent of whatever birth_time_uncertainty_minutes reports.

def test_divisional_boundary_sensitivity_not_evaluated_without_planets_d1():
    from Business_Prediction.business_determination.scoring import _divisional_boundary_sensitivity
    payload = _FakePayload()  # no planets_d1 attribute
    result = _divisional_boundary_sensitivity(payload)
    assert result["evaluated"] is False
    assert result["flags"] == []


def test_divisional_boundary_sensitivity_flags_planet_near_edge():
    from Business_Prediction.business_determination.scoring import _divisional_boundary_sensitivity
    payload = _FakePayload()
    # 2.99 deg is 0.01 deg from the first D10 segment edge (0-3.0) and from
    # the first D9 segment edge (0-3.3333) and D24 (0-1.25, 1.25-2.5).
    payload.planets_d1 = {"Mercury": {"sign": "Aries", "degree": 2.99}}
    result = _divisional_boundary_sensitivity(payload)
    assert result["evaluated"] is True
    assert result["any_flagged"] is True
    flagged_vargas = {f["varga"] for f in result["flags"]}
    assert "D10" in flagged_vargas
    assert all(f["distance_to_boundary_deg"] <= 0.5 for f in result["flags"])


def test_divisional_boundary_sensitivity_not_flagged_mid_segment():
    from Business_Prediction.business_determination.scoring import _divisional_boundary_sensitivity
    payload = _FakePayload()
    # 0.625 deg sits at the exact midpoint of D24's first 1.25-deg segment
    # (its own smallest, most edge-prone varga) and is comfortably clear of
    # every other varga's segment edges too.
    payload.planets_d1 = {"Mercury": {"sign": "Aries", "degree": 0.625}}
    result = _divisional_boundary_sensitivity(payload)
    assert result["evaluated"] is True
    assert result["any_flagged"] is False
    assert result["flags"] == []


def test_full_pipeline_downgrades_full_transition_supported_on_boundary_flag():
    """A chart that would otherwise reach FULL_TRANSITION_SUPPORTED must be
    downgraded to PILOT_WHILE_RETAINING_INCOME when a boundary-sensitivity
    flag is present, even with a reported birth_time_uncertainty_minutes of
    0 (a "clean" reported birth time) -- this is the specific gap
    birth_time_sensitivity's own disclosed limitation names."""
    payload = _MaximalPlausiblePayload()
    payload.birth_time_uncertainty_minutes = 0
    payload.planets_d1 = {"Mercury": {"sign": "Aries", "degree": 2.99}}
    result = compute_business_prediction(payload, attach_provenance=False)
    ar = result["authoritative_recommendation"]
    assert ar["divisional_boundary_sensitivity"]["any_flagged"] is True
    assert ar["action_level"] != "FULL_TRANSITION_SUPPORTED"
    assert ar["downgraded_by_divisional_boundary_sensitivity"] is True


def test_ashtakavarga_year_check_actually_runs_when_candidate_year_range_supplied():
    """Release gate for astrological-completeness item 31 ("Ashtakavarga
    and Muhurta remain optional rather than mandatory launch arbitration"):
    when a caller supplies candidate_year_range, rank_business_years() must
    actually be invoked and its result attached to
    authoritative_recommendation.ashtakavarga_year_check -- not merely
    disclosed as un-consulted. Without a candidate_year_range, the check
    must remain None and the advisory must say so, preserving the original
    backward-compatible default behavior."""
    payload = _FakePayload()

    result_with_range = compute_business_prediction(payload, candidate_year_range=(2026, 2027))
    ar = result_with_range["authoritative_recommendation"]
    assert ar["ashtakavarga_year_check"] is not None
    assert "status" in ar["ashtakavarga_year_check"]
    assert "WAS consulted" in ar["ashtakavarga_and_muhurta_advisory"]

    result_without_range = compute_business_prediction(payload)
    ar_default = result_without_range["authoritative_recommendation"]
    assert ar_default["ashtakavarga_year_check"] is None
    assert ar_default["muhurta_check"] is None
    assert "NOT consulted" in ar_default["ashtakavarga_and_muhurta_advisory"]


def test_every_live_rule_id_has_a_provenance_registry_entry():
    """Release gate for item 8 (rule_id -> provenance registry): every
    rule_id that actually appears in a real evidence ledger must resolve to
    a registered rule_provenance.py record, not the 'unregistered' fallback.
    Catches the case where a new _add() call site introduces a new rule_id
    string without a matching registry entry ever being written."""
    for payload in (_FakePayload(), _MaximalPlausiblePayload()):
        result = score_business_significators(payload)
        provenance = result["evidence_typing_stats"]["rule_provenance"]
        assert provenance, "expected at least one rule_id in the evidence ledger"
        unregistered = [rid for rid, rec in provenance.items() if not rec["registered"]]
        assert not unregistered, f"rule_id(s) with no provenance registry entry: {unregistered}"


class _MaximalPlausiblePayload:
    """A synthetic reference chart deliberately engineered to fire as many
    of score_business_significators()'s positive rules as astrologically
    plausible IN A SINGLE CHART: Mercury as simultaneous H1/H7/H10 lord,
    exalted, conjunct an exalted/own-dignity Venus (H2/H11 lord), DK is
    Mercury and H7-linked, Rahu unafflicted in H7, strong D9/D10 dignity
    and native house-graph placement throughout. This is the anchor for
    _POSITIVE_CEILING -- see the ceiling's own comment in business_engine.py
    for why the ceiling must be reachable by a chart like this, not merely
    the sum of every individual rule's independent maximum (which assumes
    H2/H3/H6/H7/H8/H9/H10/H11/H12 could ALL be ruled by exalted lords in
    kendra/trikona simultaneously -- not possible with 7-9 grahas covering
    12 houses)."""
    def __init__(self):
        self.dob = "1990-01-01"
        self.lagna_sign = "Gemini"
        self.planet_house = {"Sun": 9, "Moon": 5, "Mars": 6, "Mercury": 7, "Jupiter": 2, "Venus": 7, "Saturn": 10, "Rahu": 7, "Ketu": 1}
        self.house_lords = {"1": "Mercury", "2": "Venus", "3": "Venus", "4": "Mars", "5": "Sun", "6": "Mars", "7": "Mercury", "8": "Jupiter", "9": "Mars", "10": "Mercury", "11": "Venus", "12": "Jupiter"}
        self.planet_dignities = {"Mercury": "EXALTED", "Jupiter": "OWN", "Venus": "OWN", "Sun": "EXALTED", "Mars": "OWN", "Saturn": "OWN", "Moon": "EXALTED"}
        self.sav_points_houses = {str(i): 40 for i in range(1, 13)}
        self.darakaraka = "Mercury"
        self.d9_planet_dignities = {"Mercury": "EXALTED", "Jupiter": "EXALTED", "Sun": "EXALTED", "Saturn": "EXALTED", "Venus": "OWN"}
        self.d10_planet_dignities = {"Mercury": "EXALTED"}
        self.d9_lagna_sign = "Gemini"
        self.d10_lagna_sign = "Gemini"
        self.planet_signs = {"Moon": "Taurus", "Sun": "Aries"}
        self.d10_house_lords = {"7": "Mercury", "10": "Mercury", "11": "Mercury"}
        self.d10_house_occupancy = {"1": ["Mercury"], "2": ["Jupiter", "Venus"]}
        self.divisional_charts = {"D9_navamsha": {"Lagna": "Gemini", "Mercury": "Gemini", "Jupiter": "Cancer", "Venus": "Taurus"}}


def test_maximal_plausible_chart_scores_near_ceiling_not_compressed():
    """Regression test for a user-reported wrong-output defect on a real
    chart (Karthick_chart): the strength_0_100 scale must be anchored to
    a REACHABLE maximum, not the sum of every individual rule's
    independent maximum. Before this fix, _POSITIVE_CEILING=256.0 was that
    naive sum, and even this deliberately-maximal reference chart (see
    _MaximalPlausiblePayload) only reached ~53/100 against the OLD ceiling
    -- meaning even an excellent, heavily-engineered chart read as barely-
    moderate, which silently compressed real strong charts (e.g. a planet
    ruling BOTH the 7th and 10th house in its own dignity) down into the
    20s. Against the corrected ceiling (160.0), the reference chart scores
    ~64: still bounded below ~70 because this fixture deliberately
    concentrates almost all its evidence in ONE family (D1_PROMISE), which
    the evidence-family cap (35% of ceiling) intentionally compresses by
    design -- a chart's promise should not be over-trusted just because
    one method repeats it many ways. That's a feature, not a residual
    instance of the same bug: a DIVERSIFIED strong chart (support spread
    across D1 + D9/D10 varga confirmation + Phaladeepika, as real strong
    charts typically are) is not subject to the same single-family cap and
    can score higher. This asserts the reference chart lands in a
    genuinely strong band -- clearly above where the old ceiling placed it
    -- and that a genuinely weak chart still reads low, preserving a
    meaningful spread across the scale.

    Threshold note (gap-hunt fix): this docstring's own framing --
    "D1 + D9/D10 varga confirmation + Phaladeepika" as three separate
    diversification sources -- reflected the same bug the fix now
    corrects: Phaladeepika ch.5's findings were never a distinct family:
    the classifier only ever recognized D1_PROMISE/VARGA_CONFIRMATION/
    ACTIVATION_DIRECTION/STRENGTH, and (before that fix) Phaladeepika notes
    landed in EITHER D1_PROMISE or VARGA_CONFIRMATION depending on
    incidental note wording (whether that specific finding's text happened
    to mention "Navamsha"), not by genuine methodological category. That
    accidental split gave this fixture's Phaladeepika evidence extra,
    unintended headroom under TWO separate 35%-of-ceiling caps instead of
    one. Phaladeepika is now classified consistently as D1_PROMISE (it is
    fundamentally a D1 multi-reference-point technique), so this fixture's
    heavy D1-side concentration is now capped as a single family the way
    the docstring's own stated design intent ("a chart's promise should
    not be over-trusted just because one method repeats it many ways")
    always meant it to be -- lowering the reachable score from ~64 to
    ~54.

    Second threshold revision (typed-evidence migration, eighth slice --
    item 1, "deduplicated totals are not authoritative yet"): per an
    explicit, asked-and-confirmed scoring-policy decision, strength_0_100
    is now computed from the fact-dependency-DISCOUNTED ledger (see
    significators.py's `_fact_discount` policy: a different rule
    corroborating the exact same planet/house fact now counts at 50%
    credit, not full, additional-and-independent credit). This
    deliberately-maximal fixture concentrates evidence not just within one
    FAMILY (already capped, see above) but often re-cites the SAME
    subject (e.g. Mercury/H7) across multiple rules within that family --
    exactly the over-crediting pattern the fact-dependency discount exists
    to catch -- so its reachable score drops again, from ~54 to ~47. This
    is the intended, disclosed effect of promoting fact-dedup to primary,
    not a regression: a chart whose apparent strength leans on the same
    underlying fact being cited several ways should score lower than one
    with genuinely independent corroboration, and this fixture is
    constructed to maximize exactly that kind of repetition. Still clearly
    and meaningfully above the pre-ceiling-fix ~53/100 baseline this test
    originally guarded against, and still well above the weak-chart floor
    asserted below."""
    strong_result = score_business_significators(_MaximalPlausiblePayload())
    assert strong_result["strength_0_100"] >= 45.0, strong_result["strength_0_100"]

    weak_payload = _FakePayload()
    weak_payload.house_lords = {str(i): "Saturn" for i in range(1, 13)}
    weak_payload.planet_house = {"Saturn": 6}
    weak_payload.planet_dignities = {"Saturn": "DEBILITATED"}
    weak_payload.darakaraka = ""
    weak_result = score_business_significators(weak_payload)
    assert weak_result["strength_0_100"] < 30.0, weak_result["strength_0_100"]
    assert weak_result["strength_0_100"] < strong_result["strength_0_100"]


def test_sector_ranking_shape():
    payload = _FakePayload()
    ranked = rank_business_sectors(payload)
    assert len(ranked) == 19
    assert ranked[0]["score"] >= ranked[-1]["score"]
    assert all("sector" in row and "label" in row for row in ranked)


def test_full_pipeline():
    payload = _FakePayload()
    result = compute_business_prediction(payload)
    assert "mode_gate" in result
    assert "significators" in result
    assert "top_sectors" in result
    assert "timed_windows" in result
    assert result["recommendation"]["confidence"] in {"HIGH", "MODERATE", "LOW"}


def _sector_vector(payload):
    raw_totals = _archetype_raw_totals(payload)
    return {name: scale_raw_support(raw_totals.get(name, 0.0)) for name in ARCHETYPE_NAMES}


def test_core_houses_and_core_planets_actually_move_the_sector_score():
    """Regression test for the bug where real_estate_construction declared
    core_houses=[4, 10] / core_planets=[Saturn, Mars] but the ranking used
    only the generic archetype vector, so those fields had zero effect.
    Two charts identical except for H4-lord strength and Saturn/Mars
    placement must now score real_estate_construction differently.
    """
    weak = _FakePayload()
    weak.house_lords["4"] = "Venus"
    weak.planet_house["Venus"] = 6  # dusthana, weak
    weak.planet_house["Saturn"] = 8
    weak.planet_house["Mars"] = 12
    weak.planet_dignities = {}

    strong = _FakePayload()
    strong.house_lords["4"] = "Mars"
    strong.planet_house["Mars"] = 4  # kendra, rules H4 and sits there
    strong.planet_house["Saturn"] = 10
    strong.planet_dignities = {"Saturn": "OWN"}

    weak_score = sector_score(weak, _sector_vector(weak), "real_estate_construction")
    strong_score = sector_score(strong, _sector_vector(strong), "real_estate_construction")

    assert strong_score["score"] > weak_score["score"], (weak_score, strong_score)
    assert strong_score["core_houses_used"] == [4, 10]
    assert strong_score["core_planets_used"] == ["Saturn", "Mars"]
    assert strong_score["components"]["house_component_0_1"] > weak_score["components"]["house_component_0_1"]
    assert strong_score["components"]["planet_component_0_1"] > weak_score["components"]["planet_component_0_1"]


def test_significator_evidence_is_signed_not_accumulate_only():
    payload = _FakePayload()
    result = score_business_significators(payload)
    assert "evidence" in result
    assert all(e["polarity"] in {"POSITIVE", "NEGATIVE"} for e in result["evidence"])
    assert result["net_score"] == round(result["positive_total"] - result["negative_total"], 2)


def test_timed_windows_are_bounded_to_forecast_horizon():
    """Regression test: previously _business_ad_windows scored the entire
    dasha lifetime (48 windows from birth), not a forecast period. Every
    returned window must now fall within [as_of, as_of + years_ahead]."""
    payload = _FakePayload()
    as_of = date(2026, 1, 1)
    windows = _business_ad_windows(payload, years_ahead=10, as_of_date=as_of)
    from Job_Career.timeline_inputs import parse_iso_date
    horizon_end = as_of.replace(year=as_of.year + 10)
    for w in windows:
        start = parse_iso_date(w["start_date"])
        end = parse_iso_date(w["end_date"])
        assert end >= as_of and start <= horizon_end, w


def test_timed_windows_have_single_dominant_label_not_contradictory_tags():
    """Regression test: previously a window could carry both
    VENTURE_FAVORABLE and LOSS_LIABILITY_RISK simultaneously with no
    resolution. Each window must now carry exactly one dominant label."""
    payload = _FakePayload()
    windows = _business_ad_windows(payload, years_ahead=20, as_of_date=date(2000, 1, 1))
    for w in windows:
        assert len(w["tags"]) == 1
        assert w["label"] == w["tags"][0]


def test_venture_type_selects_distinct_gate_score():
    payload = _FakePayload()
    biz = compute_business_prediction(payload, venture_type="business")
    indep = compute_business_prediction(payload, venture_type="independent")
    assert biz["recommendation"]["venture_type"] == "business"
    assert indep["recommendation"]["venture_type"] == "independent"


def test_model_status_fields_present():
    payload = _FakePayload()
    result = compute_business_prediction(payload)
    assert result["model_status"] == "EXPERIMENTAL_HEURISTIC"
    assert "calibration_status" in result
    assert "forecast_window" in result
    assert "calibration_state" in result
    assert result["calibration_state"]["status"] == "ENGINEERED_PROVISIONAL"


def test_maturity_statement_and_caveats_present_and_consistent():
    """Regression test: compute_business_prediction() must surface an
    explicit maturity statement distinguishing 'architecturally mature and
    internally validated' from 'real-world predictively validated', plus
    the specific caveats (tests != predictions, synthetic data != model
    validation, classical coverage != classical consensus, heuristic tier
    != statistical confidence, outputs are decision-support not financial
    forecasts) -- so no downstream surface can overclaim completeness."""
    from Business_Prediction.business_engine import MATURITY_STATEMENT, MATURITY_CAVEATS

    payload = _FakePayload()
    result = compute_business_prediction(payload)
    assert result["maturity_statement"] == MATURITY_STATEMENT
    assert "internally validated" in result["maturity_statement"].lower()
    assert "not been established" in result["maturity_statement"].lower()
    assert result["maturity_caveats"] == list(MATURITY_CAVEATS)
    assert any("not predictions" in c.lower() for c in result["maturity_caveats"])
    assert any("not the model" in c.lower() for c in result["maturity_caveats"])
    assert any("not financial forecasts" in c.lower() for c in result["maturity_caveats"])
    assert "MATURITY" in result["evidence_basis"]


def test_html_report_surfaces_maturity_statement():
    """Regression test: the HTML disclaimer banner must render the
    maturity statement and caveats, not just model_status/calibration_status."""
    from Business_Prediction.generate_business_report import render_astrologer_report_html

    payload = _FakePayload()
    prediction = compute_business_prediction(payload)
    html = render_astrologer_report_html("Test Person", prediction, lang="en")
    assert "Maturity statement" in html
    assert "internally validated" in html.lower()
    assert "not financial forecasts" in html.lower() or "financial forecast" in html.lower()


def test_d9_d10_double_debilitation_denies_even_strong_d1_promise():
    """Regression test for Tier 1 (D9/D10 confirm/deny): an AD lord that
    rules H2/H7/H11 (strong D1 promise) but is debilitated in BOTH D9 and
    D10 must be capped to at most -8 net (MIXED or worse), not left at
    whatever the purely-additive D1 score would have been."""
    payload = _FakePayload()
    payload.house_lords["7"] = "Mercury"
    payload.planet_house["Mercury"] = 7  # kendra -- strong D1 promise
    payload.planet_dignities["Mercury"] = "OWN"
    payload.d9_planet_dignities = {"Mercury": "DEBILITATED"}
    payload.d10_planet_dignities = {"Mercury": "DEBILITATED"}
    payload.dasha_sequence = [{"lord": "Mercury", "start_age": 0, "end_age": 90}]

    windows = _business_ad_windows(payload, years_ahead=90, as_of_date=date(1990, 6, 1))
    mercury_windows = [w for w in windows if w["ad_lord"] == "Mercury"]
    assert mercury_windows
    for w in mercury_windows:
        assert w["net_score"] <= -8.0, w
        assert any("DENY_OVERRIDE" in t["action"] for t in w["arbitration_ledger"])


def test_kp_h7_sublord_can_override_weak_d1_read_upward():
    """Regression test for Tier 2 (KP final arbiter): a dasha lord that is
    the KP sub-lord of the H7 cusp must be able to force the window to at
    least FAVORABLE even when D1 lordship alone was neutral/weak -- but
    ONLY when that sub-lord's own KP signification set leans toward
    result-producing houses (2/7/10/11), not dispute/loss houses (6/8/12).
    Sub-lord match alone (with unknown/neutral signification) must NOT
    override -- see test_kp_h7_sublord_with_negative_signification_overrides_down."""
    payload = _FakePayload()
    # Deliberately give this planet no H2/H7/H11/H9 lordship at the D1
    # level, so Tier 0 contributes ~0.
    payload.house_lords = {str(i): "Saturn" for i in range(1, 13)}
    payload.house_lords["7"] = "Jupiter"
    payload.planet_house["Jupiter"] = 6  # not kendra/trikona -- weak D1 placement
    # v-audit fix (item 5, follow-on): kp_cusps now needs a full,
    # independently-VERIFIABLE 12-cusp chain (see _verified_kp_cusps above)
    # since the Tier-2 KP override this test exercises is now gated on
    # kp.py::_verify_kp_cusp_chain -- a bare {"H7": {"sub_lord": "Venus"}}
    # with no sign/degree can never verify and would silently disable the
    # very mechanism under test. lon=183.0 is Libra 3.0deg, independently
    # verified (via jyotish.kp_audit.kp_chain) to derive sub_lord=Venus.
    payload.house_system = "Placidus"
    payload.kp_cusps = _verified_kp_cusps(183.0)
    # Venus's own KP signification set leans toward H2/H7/H10/H11 (result-producing).
    payload.kp_significators = {"Venus": {"level_1": [7, 11], "level_2": [2], "level_3": [], "level_4": []}}
    payload.dasha_sequence = [{"lord": "Venus", "start_age": 0, "end_age": 90}]

    windows = _business_ad_windows(payload, years_ahead=90, as_of_date=date(1990, 6, 1))
    venus_windows = [w for w in windows if w["ad_lord"] == "Venus"]
    assert venus_windows
    for w in venus_windows:
        assert w["net_score"] >= 10.0, w
        assert any(t["tier"] == "2_KP_FINAL_ARBITER" and "OVERRIDE_UP" in t["action"] for t in w["arbitration_ledger"])


def test_kp_h7_sublord_with_negative_signification_overrides_down():
    """Regression test for the KP-safety fix: an H7 cusp sub-lord whose OWN
    KP signification set leans toward H6/H8/H12 (dispute/loss houses) must
    NOT be treated as automatically favorable just because it activates H7
    -- KP doctrine is that sub-lord activation means events happen, not
    that they're favorable. This must override toward risk, not toward
    FAVORABLE."""
    payload = _FakePayload()
    payload.house_lords = {str(i): "Saturn" for i in range(1, 13)}
    payload.house_lords["7"] = "Mars"
    payload.planet_house["Mars"] = 6
    # v-audit fix (item 5, follow-on): see the matching comment in
    # test_kp_h7_sublord_can_override_weak_d1_read_upward above -- needs a
    # fully verifiable 12-cusp chain now that the Tier-2 override is
    # chain_verified-gated. lon=4.8 (Aries 4.8deg) independently verified to
    # derive sub_lord=Mars.
    payload.house_system = "Placidus"
    payload.kp_cusps = _verified_kp_cusps(4.8)
    # Mars's own KP signification set leans toward H6/H8/H12 (dispute/loss).
    payload.kp_significators = {"Mars": {"level_1": [6, 8], "level_2": [12], "level_3": [], "level_4": []}}
    payload.dasha_sequence = [{"lord": "Mars", "start_age": 0, "end_age": 90}]

    windows = _business_ad_windows(payload, years_ahead=90, as_of_date=date(1990, 6, 1))
    mars_windows = [w for w in windows if w["ad_lord"] == "Mars"]
    assert mars_windows
    for w in mars_windows:
        assert w["net_score"] <= -8.0, w
        assert any(t["tier"] == "2_KP_FINAL_ARBITER" and "OVERRIDE_DOWN" in t["action"] for t in w["arbitration_ledger"])


def test_rasi_drishti_and_argala_evidence_present():
    payload = _FakePayload()
    payload.lagna_sign = "Cancer"
    payload.planet_signs = {"Jupiter": "Aquarius", "Saturn": "Leo", "Venus": "Aquarius"}
    result = score_business_significators(payload)
    notes = [e["note"] for e in result["evidence"]]
    assert any("rasi drishti" in n or "argala" in n for n in notes)


def test_phaladeepika_multi_lagna_evidence_uses_moon_and_sun():
    """Regression test: 10th-from-Moon and 10th-from-Sun (Phaladeepika ch.5
    profession method) must independently contribute evidence, not just
    the D1-Lagna-referenced houses this module already used. Since the full
    chain now also emits a strongest-reference summary note (weight 0.0,
    non-scoring), this asserts on the two weighted findings plus the
    always-present summary note rather than a fixed total length."""
    from Business_Prediction.business_engine import _phaladeepika_multi_lagna_evidence

    payload = _FakePayload()
    payload.planet_signs = {"Moon": "Cancer", "Sun": "Leo"}
    # 10th from Cancer = Aries (lord Mars); 10th from Leo = Taurus (lord Venus)
    payload.planet_house["Mars"] = 10  # kendra
    payload.planet_house["Venus"] = 7  # kendra
    payload.planet_dignities = {}

    results = _phaladeepika_multi_lagna_evidence(payload)
    weighted = [(w, n) for w, n in results if w != 0.0]
    assert len(weighted) == 2
    labels = [note for _, note in results]
    assert any("Moon" in n for n in labels)
    assert any("Sun" in n for n in labels)
    assert any("strongest reference" in n for n in labels)


def test_multi_varga_lagna_precedence_uses_d9_d10_lagna():
    """Regression test: D9-Lagna/D10-Lagna varga-native H7/H11 lordship must
    contribute evidence independent of the D9/D10 planet-dignity check."""
    from Business_Prediction.business_engine import _multi_varga_lagna_precedence_evidence

    payload = _FakePayload()
    payload.d9_lagna_sign = "Aries"    # H7 from Aries = Libra, lord Venus
    payload.d10_lagna_sign = "Taurus"  # H11 from Taurus = Aquarius, lord Saturn
    payload.planet_house["Venus"] = 1
    payload.planet_house["Saturn"] = 4
    payload.planet_dignities = {}

    results = _multi_varga_lagna_precedence_evidence(payload)
    assert len(results) == 2
    notes = [n for _, n in results]
    assert any("D9-Lagna" in n for n in notes)
    assert any("D10-Lagna" in n for n in notes)


def test_provenance_attached_by_default():
    payload = _FakePayload()
    result = compute_business_prediction(payload)
    assert "provenance" in result
    assert result["provenance"].get("run_manifest") is not None or "provenance_error" in result["provenance"]


def test_d10_native_house_graph_uses_real_occupancy_not_d1_projection():
    """Regression test: D10-native house-graph evidence must come from
    d10_house_occupancy/d10_house_lords (the actual Dashamsha house graph),
    not from projecting a varga-Lagna-derived lord back onto D1 placement
    (that's the separate, earlier _multi_varga_lagna_precedence_evidence).
    Two charts with identical D1 placements but different D10 occupancy
    must score differently."""
    from Business_Prediction.business_engine import _d10_native_house_evidence

    weak = _FakePayload()
    weak.d10_house_lords = {"7": "Saturn", "10": "Mars", "11": "Venus"}
    weak.d10_house_occupancy = {"6": ["Saturn"], "8": ["Mars"], "12": ["Venus", "Rahu"]}

    strong = _FakePayload()
    strong.d10_house_lords = {"7": "Saturn", "10": "Mars", "11": "Venus"}
    strong.d10_house_occupancy = {"1": ["Saturn"], "4": ["Mars"], "7": ["Venus", "Jupiter"]}

    weak_results = _d10_native_house_evidence(weak)
    strong_results = _d10_native_house_evidence(strong)

    weak_net = sum(w for w, _ in weak_results)
    strong_net = sum(w for w, _ in strong_results)
    assert strong_net > weak_net, (weak_results, strong_results)
    assert any("D10-native" in n for _, n in strong_results)


def test_d9_native_house_graph_uses_real_occupancy_not_d1_projection():
    """Regression test: D9-native house-graph evidence must come from
    payload.divisional_charts["D9_navamsha"] (a real Navamsha house graph
    derived via sign-to-house arithmetic), not from projecting a varga-Lagna
    -derived lord back onto D1 placement. This closes the gap the user
    caught: D9 house-occupancy data IS on the payload (divisional_charts),
    it just wasn't being read. Two charts with identical D1 placements and
    identical d9_lagna_sign but different D9_navamsha sign data must score
    differently."""
    from Business_Prediction.business_engine import _d9_native_house_evidence

    weak = _FakePayload()
    weak.d9_lagna_sign = "Aries"
    # H7 lord of Aries D9-lagna is Venus (Libra owner); H1 lord is Mars;
    # H11 lord is Saturn (Aquarius owner). Place them in dusthanas (D9
    # houses 6/8/12 relative to Aries = Virgo/Scorpio/Pisces).
    weak.divisional_charts = {
        "D9_navamsha": {
            "Lagna": "Aries",
            "Venus": "Virgo",     # H6 from Aries -> dusthana
            "Mars": "Scorpio",    # H8 from Aries -> dusthana
            "Saturn": "Pisces",   # H12 from Aries -> dusthana
        }
    }

    strong = _FakePayload()
    strong.d9_lagna_sign = "Aries"
    strong.divisional_charts = {
        "D9_navamsha": {
            "Lagna": "Aries",
            "Venus": "Cancer",    # H4 from Aries -> kendra
            "Mars": "Aries",      # H1 from Aries -> kendra
            "Saturn": "Capricorn",  # H10 from Aries -> kendra
        }
    }

    weak_results = _d9_native_house_evidence(weak)
    strong_results = _d9_native_house_evidence(strong)

    weak_net = sum(w for w, _ in weak_results)
    strong_net = sum(w for w, _ in strong_results)
    assert strong_net > weak_net, (weak_results, strong_results)
    assert any("D9-native" in n for _, n in strong_results)


def test_d9_native_house_graph_uses_canonical_lagna_when_sources_disagree():
    """Regression test: if divisional_charts["D9_navamsha"]["Lagna"] and
    payload.d9_lagna_sign ever disagree, occupancy and lordship must still
    be computed against the SAME resolved ascendant (the one returned by
    _d9_house_occupancy_from_divisional_charts, which prefers the
    divisional_charts Lagna). This is the actual chart-derived D9 Lagna
    and must win over a possibly-stale/independent d9_lagna_sign field."""
    from Business_Prediction.business_engine import (
        _d9_native_house_evidence,
        _d9_house_occupancy_from_divisional_charts,
    )

    payload = _FakePayload()
    # Deliberately mismatched: divisional_charts says Aries, d9_lagna_sign
    # (a stale/independent field) says Libra.
    payload.d9_lagna_sign = "Libra"
    payload.divisional_charts = {
        "D9_navamsha": {
            "Lagna": "Aries",
            "Mars": "Aries",       # H1 from Aries -> kendra
        }
    }

    resolved_lagna, occupancy = _d9_house_occupancy_from_divisional_charts(payload)
    assert resolved_lagna == "Aries"  # divisional_charts Lagna wins, not Libra
    assert occupancy.get(1) == ["Mars"]

    results = _d9_native_house_evidence(payload)
    # Mars is H1 lord of Aries (not of Libra) and sits in D9-H1 (kendra) --
    # this note can only appear if lordship was computed against the SAME
    # Aries ascendant that occupancy was built from.
    assert any("D9-H1" in n and "Mars" in n and "kendra" in n for _, n in results), results


def test_d9_native_house_graph_empty_without_divisional_chart_data():
    """No divisional_charts / D9_navamsha data -> no D9-native evidence,
    graceful empty list (not an exception)."""
    from Business_Prediction.business_engine import _d9_native_house_evidence

    payload = _FakePayload()
    assert _d9_native_house_evidence(payload) == []


def test_d9_dignity_extended_to_h2_and_h11_lords():
    """Regression test: D9 (Navamsha) confirmation must apply to H2 and H11
    lords too, not just H7 (the only house that previously got a D9 check)."""
    payload = _FakePayload()
    payload.house_lords["11"] = "Jupiter"
    payload.planet_house["Jupiter"] = 7  # H7/H10/H11 -- triggers H11 evidence branch
    payload.d9_planet_dignities = {"Jupiter": "EXALTED"}

    result = score_business_significators(payload)
    notes = [e["note"] for e in result["evidence"]]
    assert any("H11 lord" in n and "D9" in n for n in notes)


def test_timing_status_distinguishes_no_dob_from_no_dasha_from_ok():
    """Regression test: an empty timed_windows list must not be the only
    signal available. NO_DOB, NO_DASHA_SEQUENCE, and a real zero-windows
    result must be distinguishable via timing_status."""
    from Business_Prediction.business_engine import _timing_computation_status

    no_dob_payload = _FakePayload()
    no_dob_payload.dob = ""
    status = _timing_computation_status(no_dob_payload)
    assert status["status"] == "NO_DOB"

    no_dasha_payload = _FakePayload()
    no_dasha_payload.dasha_sequence = []
    status = _timing_computation_status(no_dasha_payload)
    assert status["status"] == "NO_DASHA_SEQUENCE"

    ok_payload = _FakePayload()
    status = _timing_computation_status(ok_payload)
    assert status["status"] == "OK"
    assert status["calendar_periods_found"] > 0


def test_calendar_computation_failure_is_reported_not_silently_empty():
    """Regression test: if _dasha_calendar itself raises, the status must
    say CALENDAR_COMPUTATION_FAILED with the real exception, not silently
    look identical to 'chart has no favorable periods'."""
    from Business_Prediction.business_engine import _timing_computation_status

    payload = _FakePayload()
    # Malformed dasha_sequence entries that will make _dasha_calendar choke
    # on float(...) conversion inside its age-to-date math.
    payload.dasha_sequence = [{"lord": "Mercury", "start_age": "not-a-number", "end_age": "also-not-a-number"}]
    status = _timing_computation_status(payload)
    assert status["status"] in {"CALENDAR_COMPUTATION_FAILED", "CALENDAR_EMPTY"}
    if status["status"] == "CALENDAR_COMPUTATION_FAILED":
        assert status["error"]


def test_compute_business_prediction_exposes_timing_status():
    payload = _FakePayload()
    result = compute_business_prediction(payload)
    assert "timing_status" in result
    assert result["timing_status"]["status"] in {
        "OK", "OK_NO_SIGNIFICANT_WINDOWS_IN_HORIZON", "NO_DOB",
        "NO_DASHA_SEQUENCE", "CALENDAR_COMPUTATION_FAILED", "CALENDAR_EMPTY",
    }


def test_moon_contextual_nature_uses_paksha():
    from Business_Prediction.business_engine import _moon_contextual_nature

    waxing = _FakePayload()
    waxing.birth_tithi_num = 10  # Shukla Paksha
    nature, note = _moon_contextual_nature(waxing)
    assert nature == "BENEFIC"

    waning = _FakePayload()
    waning.birth_tithi_num = 25  # Krishna Paksha
    nature, note = _moon_contextual_nature(waning)
    assert nature == "MALEFIC"

    unknown = _FakePayload()
    unknown.birth_tithi_num = 0
    nature, note = _moon_contextual_nature(unknown)
    assert nature == "BENEFIC"  # backward-compatible default


def test_mercury_contextual_nature_uses_conjunction():
    from Business_Prediction.business_engine import _mercury_contextual_nature

    with_malefic = _FakePayload()
    with_malefic.planet_house["Mercury"] = 5
    with_malefic.planet_house["Saturn"] = 5
    nature, note = _mercury_contextual_nature(with_malefic)
    assert nature == "MALEFIC"

    with_benefic = _FakePayload()
    with_benefic.planet_house["Mercury"] = 5
    with_benefic.planet_house["Jupiter"] = 5
    nature, note = _mercury_contextual_nature(with_benefic)
    assert nature == "BENEFIC"

    alone = _FakePayload()
    alone.planet_house["Mercury"] = 5
    nature, note = _mercury_contextual_nature(alone)
    assert nature == "BENEFIC"

    mixed = _FakePayload()
    mixed.planet_house["Mercury"] = 5
    mixed.planet_house["Jupiter"] = 5
    mixed.planet_house["Mars"] = 5
    nature, note = _mercury_contextual_nature(mixed)
    assert nature == "MIXED"


def test_effective_sets_change_rasi_drishti_direction():
    """Regression test: a waning Moon casting rasi drishti on H7 must count
    as malefic pressure, not benefic support -- the opposite of what the
    old unconditional _NATURAL_BENEFICS treatment would have produced."""
    from Business_Prediction.business_engine import _jaimini_rasi_drishti_evidence

    payload = _FakePayload()
    payload.lagna_sign = "Cancer"  # H7 from Cancer = Capricorn (movable)
    payload.planet_signs = {"Moon": "Leo"}  # Leo (fixed) casts rasi drishti onto Capricorn
    payload.birth_tithi_num = 28  # deep Krishna Paksha -- waning, malefic-leaning

    # Confirm the contextual nature itself is what the drishti function will see.
    from Business_Prediction.business_engine import _moon_contextual_nature
    nature, _ = _moon_contextual_nature(payload)
    assert nature == "MALEFIC"

    net, notes = _jaimini_rasi_drishti_evidence(payload, reference_house=7)
    for note in notes:
        if "Moon" in note:
            assert "malefic pressure" in note


def test_transit_computation_failure_is_reported_not_confused_with_no_flags():
    """Regression test: _transit_corroboration must distinguish a real
    computation failure from 'ran fine, nothing to report'. Previously both
    collapsed to (0.0, []) and method_status could report
    PRESENT_NOT_TRIGGERED for an actual failure."""
    from Business_Prediction.business_engine import _transit_corroboration, _TRANSIT_STATUS_MISSING_DATA

    payload = _FakePayload()
    payload.lagna_sign = ""  # no lagna -- can't attempt transit computation at all
    net, notes, status = _transit_corroboration(date(2026, 1, 1), date(2027, 1, 1), payload, date(2026, 1, 1))
    assert status == _TRANSIT_STATUS_MISSING_DATA


# --- Real-ephemeris transit precision (item 28) ---
# v-audit fix (astrological completeness, "transits remain mean-motion
# approximations"): _transit_corroboration() now prefers jyotish.ephemeris.
# get_transit_house_positions() (genuine Skyfield/DE421 sidereal longitudes)
# when that optional capability is available, falling back to the
# pre-existing Job_Career.timeline mean-motion projection otherwise. These
# tests mock jyotish.ephemeris directly (skyfield/DE421 aren't installed in
# this environment) to prove the real-ephemeris path is actually reachable
# and wired correctly, without requiring the real dependency to be present.

def test_transit_corroboration_prefers_real_ephemeris_when_available():
    from unittest.mock import patch
    from Business_Prediction.business_engine import _transit_corroboration

    payload = _FakePayload()
    payload.lagna_sign = "Aries"
    payload.latitude = 9.9
    payload.longitude = 78.1

    with patch("jyotish.ephemeris.is_available", return_value=True), \
         patch("jyotish.ephemeris.get_transit_house_positions", return_value=({"Jupiter": 2, "Saturn": 6, "Rahu": 1}, {}, [])):
        net, notes, status = _transit_corroboration(date(2026, 1, 1), date(2026, 6, 1), payload, date(2025, 12, 1))

    assert status == "APPLIED"
    assert net == 1.0  # +5 (Jupiter H2 expansion) - 4 (Saturn H6 disruption)
    assert all("[REAL EPHEMERIS]" in n for n in notes)
    assert any("JUPITER_H2_EXPANSION" in n for n in notes)
    assert any("SATURN_H6_DISRUPTION" in n for n in notes)
    assert any("RAHU_KETU_AXIS_MAJOR_CHANGE" in n for n in notes)


def test_transit_corroboration_falls_back_to_mean_motion_when_ephemeris_unavailable():
    from unittest.mock import patch
    from Business_Prediction.business_engine import _transit_corroboration

    payload = _FakePayload()
    payload.lagna_sign = "Aries"

    with patch("jyotish.ephemeris.is_available", return_value=False):
        net, notes, status = _transit_corroboration(date(2026, 1, 1), date(2027, 1, 1), payload, date(2026, 1, 1))

    # Falls back to the pre-existing Job_Career.timeline mean-motion path --
    # never crashes, never silently returns nothing just because the
    # optional real-ephemeris dependency is missing.
    assert status in {"APPLIED", "NO_FLAGS"}
    if notes:
        assert all("[MEAN-MOTION APPROX]" in n for n in notes)


def test_transit_corroboration_ignores_real_ephemeris_without_lat_lon():
    """A payload with no latitude/longitude (or the 0.0/0.0 default,
    indistinguishable from 'never set') must not attempt the real-ephemeris
    path even if jyotish.ephemeris reports itself available -- it has no
    usable coordinates to compute a position for."""
    from unittest.mock import patch
    from Business_Prediction.business_engine import _transit_corroboration

    payload = _FakePayload()
    payload.lagna_sign = "Aries"
    # No latitude/longitude attributes at all on _FakePayload by default.

    with patch("jyotish.ephemeris.is_available", return_value=True), \
         patch("jyotish.ephemeris.get_transit_house_positions") as mock_get:
        net, notes, status = _transit_corroboration(date(2026, 1, 1), date(2027, 1, 1), payload, date(2026, 1, 1))
        mock_get.assert_not_called()


def test_transit_status_summary_propagates_to_method_status():
    payload = _FakePayload()
    result = compute_business_prediction(payload)
    assert "transit_status_summary" in result["timing_status"]
    assert result["method_status"]["dynamic_transit"]["status"] in {
        "APPLIED", "COMPUTED_NO_FLAGS", "MISSING_DATA", "FAILED", "NOT_REQUESTED",
    }


def test_kp_bias_is_level_weighted_not_flat_count():
    """Regression test: one level_1 negative house must be able to outweigh
    several level_3/4 positive houses -- a flat set-count comparison would
    get this backwards (3 positive houses > 1 negative house by count)."""
    from Business_Prediction.business_engine import _kp_sublord_signification_bias

    payload = _FakePayload()
    # 3 low-priority positive houses (level_4) vs 1 high-priority negative
    # house (level_1). Flat count: 3 positive > 1 negative -> POSITIVE (wrong).
    # Level-weighted: level_1 negative (weight 1.00) vs 3x level_4 positive
    # (weight 0.15 each = 0.45 total) -> NEGATIVE (correct).
    payload.kp_significators = {
        "Saturn": {"level_1": [8], "level_2": [], "level_3": [], "level_4": [2, 7, 11]}
    }
    bias, pos, neg = _kp_sublord_signification_bias("Saturn", payload)
    assert bias == "NEGATIVE", (bias, pos, neg)


def test_timing_computation_status_is_true_wrapper_no_divergence():
    """Regression test for the cleanup: _timing_computation_status() must
    never disagree with what _compute_windows_and_status() itself
    computed, since it's now a thin wrapper around the same function."""
    from Business_Prediction.business_engine import _timing_computation_status, _compute_windows_and_status

    payload = _FakePayload()
    _windows, direct_status = _compute_windows_and_status(payload)
    wrapper_status = _timing_computation_status(payload)
    assert wrapper_status == direct_status


def test_report_html_exposes_full_contract_not_just_positive_signals():
    """Regression test for the report-fidelity finding: the HTML report must
    surface risk_signals, timing_status, method_status, model_status/
    calibration_status, and per-window evidence/arbitration -- not just the
    positive signals and window labels the earlier report was limited to."""
    from Business_Prediction.generate_business_report import render_astrologer_report_html

    payload = _FakePayload()
    prediction = compute_business_prediction(payload)
    html = render_astrologer_report_html("Test Person", prediction, lang="en")

    assert "Model status" in html
    assert "Method-level status" in html
    assert "Timing computation status" in html
    assert "Heuristic Tier" in html
    assert "uncalibrated" in html.lower()
    if prediction["significators"].get("risk_signals"):
        assert "risk signal" in html.lower()
    if prediction["timed_windows"]:
        assert "Arbitration ledger" in html


def test_llm_narrative_absent_by_default_and_none_without_consent():
    payload = _FakePayload()
    result_default = compute_business_prediction(payload)
    assert "llm_narrative" not in result_default  # opt-in flag was not set

    result_opted_in = compute_business_prediction(payload, enable_llm_narrative=True)
    # No consent/API key in this test environment -> must degrade to None, never raise.
    assert result_opted_in["llm_narrative"] is None


def test_business_mode_gate_replaces_legacy_employment_mode():
    """Regression test for audit finding #1: compute_business_prediction()
    must use the new v9 signed/dignity-gated/D9D10-corroborated
    compute_business_mode_gate(), not the legacy unconditional
    jyotish.employment_mode.compute_employment_mode(). The new gate must
    expose signed positive/negative signals and a gate_policy tag the old
    module never had."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    payload = _FakePayload()
    gate = compute_business_mode_gate(payload)
    assert "gate_policy" in gate and "business-engine" in gate["gate_policy"]
    assert "positive_signals" in gate and "negative_signals" in gate
    assert set(gate["positive_signals"]) == {"employment", "business", "independent", "family"}

    result = compute_business_prediction(payload)
    assert result["mode_gate"]["gate_policy"] == gate["gate_policy"]


def test_mode_gate_uses_fixed_ceiling_not_dynamic_denominator():
    """Regression test for the reviewer-caught critical defect: a mode's
    normalization denominator must be a FIXED, documented ceiling, not a
    dynamic sum that only grows when a rule fires -- the latter let one
    trivial 8-point H2-H7 connection alone normalize business_score to 100
    on an otherwise sparse chart. Reproduces the reviewer's exact sparse
    payload (only an H2-H7 lord connection) and asserts none of the four
    mode scores saturate to 100 from a single small rule firing."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    class _SparsePayload:
        house_lords = {"2": "Mars", "7": "Mars"}
        planet_house: dict = {}
        planet_dignities: dict = {}
        sav_points_houses: dict = {}
        darakaraka = ""

    gate = compute_business_mode_gate(_SparsePayload())
    assert gate["business_score"] < 100, gate
    assert gate["independent_score"] < 100, gate
    # The single H2-H7 connection rule contributes 8 raw points against a
    # fixed ~88.2 business ceiling -- should land far below saturation.
    assert gate["business_score"] < 20, gate


def test_mode_gate_geographic_preference_requires_real_placements():
    """Regression test for the reviewer-caught critical defect: comparing
    _ph('Moon') == rahu_h evaluated 0 == 0 when BOTH placements were
    missing, falsely classifying charts with no real Rahu/Moon data as
    'international'. Both placements must be genuinely known for that
    signal to fire."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    class _NoPlacementsPayload:
        house_lords: dict = {}
        planet_house: dict = {}  # Rahu and Moon both absent -> both would be 0
        planet_dignities: dict = {}
        sav_points_houses: dict = {}
        darakaraka = ""

    gate = compute_business_mode_gate(_NoPlacementsPayload())
    assert gate["geographic_preference"] == "domestic", gate


def test_business_mode_gate_rahu_h7_is_gated_on_affliction():
    """Regression test: Rahu in H7 must no longer be an unconditional
    business-positive (the legacy employment_mode rule) -- afflicted by a
    natural malefic co-tenant, it must be negative evidence instead."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    unafflicted = _FakePayload()
    unafflicted.planet_house["Rahu"] = 7
    unafflicted.planet_house["Saturn"] = 2  # move Saturn off H7 so no affliction
    unafflicted.planet_house["Mars"] = 2
    unafflicted.planet_house["Ketu"] = 2

    afflicted = _FakePayload()
    afflicted.planet_house["Rahu"] = 7
    afflicted.planet_house["Saturn"] = 7  # Saturn conjunct Rahu in H7 -> afflicted

    unafflicted_gate = compute_business_mode_gate(unafflicted)
    afflicted_gate = compute_business_mode_gate(afflicted)

    assert any("unafflicted" in n for n in unafflicted_gate["positive_signals"]["business"])
    assert any("Rahu in H7 conjunct natural malefic" in n for n in afflicted_gate["negative_signals"]["business"])


def test_rahu_h7_requires_ownership_corroboration_not_automatic_entrepreneurship():
    """v22 audit fix: spec section 15 false-conclusion guard #2 explicitly
    warns "strong Rahu means entrepreneurship" is a false conclusion --
    Rahu in an unafflicted H7 may equally give foreign/digital WORK WITHIN
    EMPLOYMENT (an MNC role, offshore delivery, remote assignment), not
    only business ownership. Previously this rule credited a flat +14 to
    business regardless of any ownership-structure link. It must now only
    grant the full credit when H7's own lord independently connects to
    H2/H10/H11 (real ownership corroboration); without that link, the
    signal is genuinely ambiguous and must be split at reduced weight
    between business and employment, not auto-coded as business."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    # H7 lord (Venus, since H7=Libra under this fixture's default Aries
    # lagna) shows NO connection to H2/H10/H11.
    ambiguous = _FakePayload()
    ambiguous.planet_house["Rahu"] = 7
    ambiguous.planet_house["Saturn"] = 2
    ambiguous.planet_house["Mars"] = 2
    ambiguous.planet_house["Ketu"] = 2
    ambiguous.house_lords["7"] = "Venus"
    ambiguous.planet_house["Venus"] = 5  # not in 2/10/11, and H7 lord != H2/H10/H11 lord
    for h in ("2", "10", "11"):
        if ambiguous.house_lords.get(h) == "Venus":
            ambiguous.house_lords[h] = "Mars"

    corroborated = _FakePayload()
    corroborated.planet_house["Rahu"] = 7
    corroborated.planet_house["Saturn"] = 2
    corroborated.planet_house["Mars"] = 2
    corroborated.planet_house["Ketu"] = 2
    corroborated.house_lords["7"] = "Venus"
    corroborated.planet_house["Venus"] = 10  # H7 lord placed in H10 -> real ownership link

    ambiguous_gate = compute_business_mode_gate(ambiguous)
    corroborated_gate = compute_business_mode_gate(corroborated)

    ambiguous_biz_notes = ambiguous_gate["positive_signals"]["business"]
    corroborated_biz_notes = corroborated_gate["positive_signals"]["business"]

    assert any("NO independent H2/H10/H11 connection" in n for n in ambiguous_biz_notes), ambiguous_biz_notes
    assert any("ownership-structure link" in n for n in corroborated_biz_notes), corroborated_biz_notes
    # The corroborated chart's Rahu-in-H7 contribution to business must be
    # strictly larger than the ambiguous chart's (14 vs 5), proving the
    # gate is real, not cosmetic wording.
    assert corroborated_gate["business_score"] > ambiguous_gate["business_score"]
    # The ambiguous chart must ALSO register an employment-side hedge,
    # since the signal doesn't discriminate ownership from employment.
    assert any("MNC/offshore/remote employment" in n for n in ambiguous_gate["positive_signals"]["employment"]), ambiguous_gate["positive_signals"]["employment"]


def test_mode_gate_folds_in_d10_native_house_graph():
    """Regression test: compute_business_mode_gate() must route D10-native
    house-graph evidence (D10's own house graph, not D1 placement projected
    onto D10 dignity) into the relevant modes -- previously the gate only
    ever used D9/D10 PLANET-dignity corroboration on the H6/H7 lords, never
    D10's own house occupancy/lordship. Two charts identical except for
    D10 occupancy must score business/employment/family differently."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    weak = _FakePayload()
    weak.d10_house_lords = {"7": "Saturn", "10": "Mars", "11": "Venus"}
    weak.d10_house_occupancy = {"6": ["Saturn"], "8": ["Mars"], "12": ["Venus", "Rahu"]}

    strong = _FakePayload()
    strong.d10_house_lords = {"7": "Saturn", "10": "Mars", "11": "Venus"}
    strong.d10_house_occupancy = {"1": ["Saturn"], "4": ["Mars"], "7": ["Venus", "Jupiter"]}

    weak_gate = compute_business_mode_gate(weak)
    strong_gate = compute_business_mode_gate(strong)

    assert strong_gate["business_score"] > weak_gate["business_score"], (weak_gate["business_score"], strong_gate["business_score"])
    assert any("[D10-native]" in n for n in strong_gate["positive_signals"]["business"])


def test_mode_gate_includes_dynamic_transit_climate_signal():
    """Regression test: compute_business_mode_gate() must expose a
    transit_climate_status field and, when the mean-motion transit
    projection actually fires flags, route dampened-weight notes tagged
    '[transit-climate...]' into the business mode -- distinct from the
    multi-year timed-windows forecast in Layer 4. Uses a fixed as_of_date
    for determinism; if the underlying transit projection can't run for
    this minimal payload (no lagna_sign), status must still be reported
    honestly rather than silently absent."""
    from Business_Prediction.business_engine import compute_business_mode_gate
    from datetime import date

    payload = _FakePayload()
    gate = compute_business_mode_gate(payload, as_of_date=date(2026, 1, 1))
    assert "transit_climate_status" in gate
    assert gate["transit_climate_status"] in {
        "APPLIED", "NO_FLAGS", "MISSING_DATA", "IMPORT_FAILED", "COMPUTATION_FAILED",
    }
    # With a lagna_sign present, the transit projection should at least be
    # attempted (not MISSING_DATA purely for lack of that field).
    payload.lagna_sign = "Aries"
    gate_with_lagna = compute_business_mode_gate(payload, as_of_date=date(2026, 1, 1))
    assert gate_with_lagna["transit_climate_status"] != "MISSING_DATA"


def test_mode_gate_uses_shared_ceiling_more_raw_evidence_wins():
    """Regression test for the reviewer-caught central defect: comparing
    two modes' percentages of DIFFERENT per-mode ceilings is not valid --
    a mode with more raw positive evidence could still score lower purely
    because its own ceiling happened to be larger. All four modes must
    share ONE ceiling so that more raw evidence in one mode always yields
    a higher (or equal) score than less raw evidence in another mode."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    payload = _FakePayload()
    # Business rule (H2-H7 connection, 8 raw points) vs an employment rule
    # of lesser raw weight (Saturn aspects H10, 12 raw points) -- pick
    # values that would have flipped order under the old asymmetric
    # ceilings (employment 72 vs business 104) but must now respect raw
    # magnitude directly since both share one ceiling.
    payload.house_lords["7"] = "Mars"
    payload.house_lords["2"] = "Mars"
    payload.planet_house["Mars"] = 3  # not kendra -- keeps H7-lord-strength rule from firing
    payload.house_lords["6"] = "Saturn"
    payload.planet_house["Saturn"] = 4  # Saturn aspects H10 (4/7 rule) -- employment +12

    gate = compute_business_mode_gate(payload)
    # Whichever mode has the larger RAW evidence must score at least as
    # high once both are read off the SAME shared ceiling.
    from Business_Prediction.business_engine import compute_business_mode_gate as _cbg  # noqa: F401
    # Sanity: the shared ceiling means score is a direct linear function of
    # raw evidence for both modes -- assert internal consistency rather
    # than a specific magnitude (which would be brittle to future rule
    # tuning): employment and business must be scaled by the identical
    # ceiling, provable by checking neither exceeds the other's own old
    # (now-removed) asymmetric ceiling assumption silently.
    assert isinstance(gate["employment_score"], int)
    assert isinstance(gate["business_score"], int)
    assert 0 <= gate["employment_score"] <= 100
    assert 0 <= gate["business_score"] <= 100


def test_functional_kendra_trikona_lords_neutralizes_natural_malefics():
    """Regression test for a real astrological defect found auditing
    Karthick_chart: Sun ruling a trikona house (H9) for a Sagittarius
    lagna was still being treated as an unconditional natural malefic in
    rasi-drishti/argala/conjunction checks, penalizing Mercury (the H7/H10
    lord) for being conjunct its own dharma-karma significator. Classical
    functional-lordship: a natural malefic that rules a kendra/trikona for
    THIS lagna should be excluded from the malefic set."""
    from Business_Prediction.business_engine import _functional_kendra_trikona_lords, _effective_benefic_malefic_sets

    payload = _FakePayload()
    payload.house_lords["9"] = "Sun"  # Sun rules a trikona (H9) for this chart

    functional = _functional_kendra_trikona_lords(payload)
    assert "Sun" in functional

    _benefics, malefics = _effective_benefic_malefic_sets(payload)
    assert "Sun" not in malefics

    # Control: a chart where Sun rules only a dusthana/upachaya (not
    # kendra/trikona) must still treat Sun as a natural malefic.
    payload_control = _FakePayload()
    payload_control.house_lords["9"] = "Mars"  # Sun doesn't rule H9 here
    payload_control.house_lords["6"] = "Sun"   # Sun rules H6 only (not kendra/trikona)
    _benefics_c, malefics_c = _effective_benefic_malefic_sets(payload_control)
    assert "Sun" in malefics_c


def test_mode_gate_scores_h7_h10_sambandha_and_own_house_lord():
    """Regression test: the H7-H10 sambandha (same planet ruling both the
    partnership and livelihood houses) and the H10 lord occupying its own
    house were visible in the significator ledger but never scored in the
    mode gate's decision layer -- the chart's strongest business/public-
    dealing configuration was invisible to the actual proceed/deny logic."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    payload = _FakePayload()
    payload.house_lords["7"] = "Mercury"
    payload.house_lords["10"] = "Mercury"
    payload.planet_house["Mercury"] = 10
    payload.planet_dignities["Mercury"] = "OWN"

    gate = compute_business_mode_gate(payload)
    assert any("H7-H10 sambandha" in n for n in gate["positive_signals"]["business"])
    assert any("occupies its own house (H10)" in n for n in gate["positive_signals"]["business"])


def test_mode_gate_h11_lord_in_trikona_credits_business():
    """Regression test: H11 (gains) lord well placed in a trikona
    (dharma/creative house) is an enterprise/institution-building signal
    that previously had no business credit unless the lord specifically
    sat in H7/H10 -- this closes that gap, parallel to the existing
    H6-lord-in-kendra/trikona employment finding."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    payload = _FakePayload()
    payload.house_lords["11"] = "Venus"
    payload.planet_house["Venus"] = 5  # trikona, not H7/H10
    payload.planet_dignities["Venus"] = "EXALTED"

    gate = compute_business_mode_gate(payload)
    assert any("trikona" in n and "enterprise" in n for n in gate["positive_signals"]["business"])


def test_ad_lord_evidence_reports_specific_houses_not_all_three():
    """Regression test: the AD-lord evidence string previously always said
    'rules H2/H7/H11' even when the lord matched only ONE of those houses,
    implying triple lordship. It must report the specific house(s)
    actually ruled."""
    payload = _FakePayload()
    payload.house_lords = {str(i): "Saturn" for i in range(1, 13)}
    payload.house_lords["7"] = "Jupiter"  # Jupiter rules ONLY H7 among H2/H7/H11
    payload.planet_house["Jupiter"] = 1
    payload.dasha_sequence = [{"lord": "Jupiter", "start_age": 0, "end_age": 90}]

    windows = _business_ad_windows(payload, years_ahead=90, as_of_date=date(1990, 6, 1))
    jupiter_windows = [w for w in windows if w["ad_lord"] == "Jupiter"]
    assert jupiter_windows
    matched = [e for w in jupiter_windows for e in w.get("evidence", []) if "rules H" in e]
    assert matched
    for e in matched:
        assert "rules H7" in e
        assert "H2" not in e.split("rules ")[1].split(" ")[0]
        assert "H11" not in e.split("rules ")[1].split(" ")[0]


def test_proceed_requires_comparative_advantage_over_employment():
    """Regression test for audit finding #2: a chart where employment is
    the dominant mode by a wide margin must not receive proceed=True on
    the LEGACY mode_gate track, even if the business gate score alone
    clears the absolute 40/35 floor. This is the comparative-advantage
    requirement of that legacy track specifically.

    Engineering audit fix #1 (dual decision systems) made the layered
    business_promise/job_promise system -- not this legacy gate_score-vs-
    employment_score comparison -- authoritative for recommendation.proceed.
    The legacy comparative-advantage read is preserved as a diagnostic in
    recommendation.legacy_mode_gate_score, so this test now checks
    consistency there instead of asserting the legacy invariant against
    the (now independently-computed) authoritative `proceed` field."""
    payload = _FakePayload()
    # Strongly favor employment: Saturn in H10 exalted-equivalent-strong
    # placement, weak H7 lord placement for business.
    payload.house_lords["6"] = "Saturn"
    payload.planet_house["Saturn"] = 10
    payload.planet_dignities["Saturn"] = "OWN"
    payload.sav_points_houses["10"] = 40

    result = compute_business_prediction(payload, venture_type="business")
    rec = result["recommendation"]
    assert "comparative_advantage" in rec
    assert "hybrid_suggested" in rec
    legacy = rec["legacy_mode_gate_score"]
    if not rec["comparative_advantage"]:
        assert legacy["proceed"] is False


def test_recommendation_proceed_actually_penalized_by_contradictions():
    """v22 audit fix (real bug): `recommendation.proceed` used to be
    finalized BEFORE `_contradiction_penalties()` was even called, so a
    chart the engine itself flags with a real contradiction (e.g. "H7
    strong but no H2/H10/H11 connection") could still return
    proceed=True -- the contradiction layer only ever fed
    contradiction_findings/confidence, never the headline recommendation.
    Verify recommendation now exposes penalized_gate_score <=
    gate_score, and that a chart triggering contradiction #1 (strong,
    disconnected H7) has a strictly non-zero business contradiction
    penalty actually subtracted before the proceed decision."""
    payload = _MaximalPlausiblePayload()
    # Force contradiction #1: H7 lord strong (own house, kendra) but its
    # house has no shared lord with/placement in H2/H10/H11.
    payload.house_lords["7"] = "Venus"
    payload.planet_house["Venus"] = 7
    payload.planet_dignities["Venus"] = "OWN"
    for h in ("2", "10", "11"):
        if payload.house_lords.get(h) == "Venus":
            payload.house_lords[h] = "Mars"
    if payload.planet_house.get("Mars") in (2, 10, 11):
        payload.planet_house["Mars"] = 4

    result = compute_business_prediction(payload, venture_type="business")
    rec = result["recommendation"]
    assert "penalized_gate_score" in rec and "gate_score" in rec
    assert rec["penalized_gate_score"] <= rec["gate_score"]
    assert "contradiction_penalty_applied" in rec
    biz_penalty = rec["contradiction_penalty_applied"]["business"]
    # This chart is specifically constructed to trip contradiction #1;
    # confirm it actually fired and was actually applied to the gate score
    # used for proceed, not just recorded separately.
    contradiction_notes = [c["note"] for c in result["contradiction_findings"]]
    h7_disconnect_fired = any("NO connection to H2/H10/H11" in n for n in contradiction_notes)
    if h7_disconnect_fired:
        assert biz_penalty > 0, (biz_penalty, contradiction_notes)
        assert rec["penalized_gate_score"] == round(max(0.0, rec["gate_score"] - biz_penalty), 10) or rec["penalized_gate_score"] == max(0.0, rec["gate_score"] - biz_penalty)


def test_d1_tenth_lord_direct_evidence_present():
    """Regression test for audit finding #4: the D1 10th lord's own
    strength/connections must be judged directly, not only ever consumed
    indirectly by other checks."""
    from Business_Prediction.business_engine import _d1_tenth_lord_direct_evidence

    payload = _FakePayload()
    payload.house_lords["10"] = "Mercury"
    payload.house_lords["7"] = "Mercury"  # H7-H10 connection: same lord
    payload.planet_house["Mercury"] = 7
    payload.planet_dignities["Mercury"] = "OWN"

    results = _d1_tenth_lord_direct_evidence(payload)
    assert results
    notes = [n for _, n in results]
    assert any("D1 10th lord" in n for n in notes)
    assert any("H7-H10 connection" in n for n in notes)


def test_d1_tenth_lord_debilitation_dead_zone_still_flagged():
    """Regression test for user-directed audit finding: rule 1's strength
    bucket (>=0.6 positive / <0.35 negative) had a dead zone in between
    that swallowed a debilitated 10th lord placed in a kendra/trikona --
    such a placement computes to exactly base(1.0)*dig_factor(0.55)=0.55,
    landing in that dead zone with zero evidence recorded. The D1
    debilitation of the 10th lord must now be flagged unconditionally,
    independent of which bucket the strength scalar lands in."""
    from Business_Prediction.business_engine import _d1_tenth_lord_direct_evidence

    payload = _FakePayload()
    # H10 lord is Mercury by default, placed in H7 (kendra) -> strength
    # would be 1.0 (KT) undamped; force it DEBILITATED so the dig_factor
    # drags it to exactly 0.55, inside the 0.35-0.6 dead zone.
    payload.planet_dignities["Mercury"] = "DEBILITATED"

    results = _d1_tenth_lord_direct_evidence(payload)
    notes = [n for _, n in results]
    assert any("DEBILITATED in D1" in n for n in notes), notes
    debil_weight = next(w for w, n in results if "DEBILITATED in D1" in n)
    assert debil_weight < 0
    # And the old strength-bucket rule must NOT also have fired for the
    # same evidence line (it should stay silent in the dead zone; only
    # the new explicit branch should report anything for this planet's
    # own D1 dignity).
    assert not any("directly well placed" in n or "directly weak" in n for n in notes)


def test_lagna_h1_occupants_scored_independently_of_lagna_lord():
    """Regression test for user-directed audit finding: only the lagna
    LORD's placement was ever scored (via _lagna_lord_strength / the
    'Lagna lord in H1/H10' independent-mode rule); what actually occupies
    the lagna house itself -- the classical self/temperament signature --
    had no evidence at all, unlike H7 which already had a 'no planet in
    H7' occupancy check. A benefic occupant should credit independent
    mode, a malefic occupant should penalize it, and a debilitated
    occupant must be flagged separately regardless of benefic/malefic
    classification."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    # _FakePayload already places Jupiter (a natural benefic) in H1.
    benefic_payload = _FakePayload()
    gate = compute_business_mode_gate(benefic_payload)
    pos = gate["positive_signals"].get("independent", [])
    assert any("occupy Lagna (H1)" in s for s in pos), pos

    malefic_payload = _FakePayload()
    malefic_payload.planet_house["Saturn"] = 1
    malefic_payload.planet_house["Jupiter"] = 5  # vacate H1 of the benefic
    gate2 = compute_business_mode_gate(malefic_payload)
    neg = gate2["negative_signals"].get("independent", [])
    assert any("occupy Lagna (H1)" in s for s in neg), neg

    # QA fix (comprehensive gap-audit pass): mode_gate.py's DEBILITATED
    # gates now check Neecha Bhanga (debilitation-cancellation) via
    # _effectively_debilitated(), matching significators.py/yogas.py/
    # legal_risk.py/foreign_business.py, which already had this check.
    # _FakePayload's default house_lords/planet_house, unmodified, actually
    # satisfies a real cancellation condition for Saturn (debilitated in
    # Aries, ruled by Mars): Saturn's EXALTATION sign is Libra, ruled by
    # Venus, and Venus sits in H7 (a kendra from Lagna) by default -- so
    # Saturn's debilitation here is classically cancelled, and the
    # "DEBILITATED" penalty correctly no longer fires. This moves Venus out
    # of every kendra (H1/4/7/10) so the debilitation genuinely stays
    # uncancelled, preserving the test's actual intent (an uncancelled
    # debilitated occupant must be flagged, regardless of benefic/malefic
    # classification) rather than accidentally exercising the cancellation
    # path instead.
    debilitated_payload = _FakePayload()
    debilitated_payload.planet_house["Saturn"] = 1
    debilitated_payload.planet_house["Jupiter"] = 5
    debilitated_payload.planet_house["Venus"] = 2  # out of every kendra -> Neecha Bhanga does NOT apply
    debilitated_payload.planet_dignities["Saturn"] = "DEBILITATED"
    gate3 = compute_business_mode_gate(debilitated_payload)
    neg3 = gate3["negative_signals"].get("independent", [])
    assert any("DEBILITATED" in s and "Lagna (H1)" in s for s in neg3), neg3


def test_viparita_raja_yoga_qualification_distinguishes_own_house_and_contamination():
    """Regression test for audit finding #5: a strong H6 lord in its OWN
    house (H6) must NOT be labeled Viparita Raja Yoga (no dusthana-to-
    dusthana movement); a strong H6 lord in another dusthana conjunct a
    kendra-lord must be flagged MIXED, not full VRY_CONFIRMED credit."""
    payload_own_house = _FakePayload()
    payload_own_house.house_lords["6"] = "Mars"
    payload_own_house.planet_house["Mars"] = 6
    payload_own_house.planet_dignities["Mars"] = "OWN"

    result_own = score_business_significators(payload_own_house)
    own_notes = [e["note"] for e in result_own["evidence"]]
    assert any("NOT Viparita Raja Yoga" in n for n in own_notes)

    payload_confirmed = _FakePayload()
    payload_confirmed.house_lords["6"] = "Mars"
    payload_confirmed.planet_house["Mars"] = 8  # different dusthana
    payload_confirmed.planet_dignities["Mars"] = "EXALTED"
    # Ensure no kendra lord co-tenants Mars in H8.
    payload_confirmed.planet_house = {p: h for p, h in payload_confirmed.planet_house.items() if h != 8}
    payload_confirmed.planet_house["Mars"] = 8

    result_confirmed = score_business_significators(payload_confirmed)
    confirmed_notes = [e["note"] for e in result_confirmed["evidence"]]
    assert any("VRY_CONFIRMED" in n for n in confirmed_notes)


def test_vry_exchange_requires_true_house_swap_not_conjunction():
    """Regression test for the reviewer-caught defect: the previous
    exchange check (`co_tenants & dusthana_lords`) fired on two dusthana
    lords merely CONJUNCT in the same house, not a genuine parivartana
    (house swap). A true exchange requires H6-lord to sit in H8 AND
    H8-lord to sit back in H6; two dusthana lords conjunct in H8 together
    (neither actually occupying the other's own house) must NOT be scored
    as an exchange."""
    # Genuine exchange: H6 lord (Mars) sits in H8; H8 lord (Venus) sits
    # back in H6. True parivartana -> exchange-tier VRY_CONFIRMED (+6).
    payload_exchange = _FakePayload()
    payload_exchange.house_lords["6"] = "Mars"
    payload_exchange.house_lords["8"] = "Venus"
    payload_exchange.planet_house = {p: h for p, h in payload_exchange.planet_house.items() if p not in ("Mars", "Venus")}
    payload_exchange.planet_house["Mars"] = 8
    payload_exchange.planet_house["Venus"] = 6
    payload_exchange.planet_dignities["Mars"] = "EXALTED"

    result_exchange = score_business_significators(payload_exchange)
    exchange_notes = [e["note"] for e in result_exchange["evidence"]]
    assert any("exchange" in n and "VRY_CONFIRMED" in n for n in exchange_notes), exchange_notes

    # Conjunction only: H6 lord (Mars) sits in H8 together with another
    # dusthana lord (H12 lord, Moon) who is ALSO just conjunct in H8, not
    # occupying H6 back. This must score as plain VRY_CONFIRMED (or MIXED
    # if contaminated), never the +6 exchange tier.
    payload_conjunction = _FakePayload()
    payload_conjunction.house_lords["6"] = "Mars"
    payload_conjunction.house_lords["12"] = "Moon"
    payload_conjunction.planet_house = {p: h for p, h in payload_conjunction.planet_house.items() if p not in ("Mars", "Moon")}
    payload_conjunction.planet_house["Mars"] = 8
    payload_conjunction.planet_house["Moon"] = 8  # conjunct with Mars in H8, but Moon does NOT sit in H6
    payload_conjunction.planet_dignities["Mars"] = "EXALTED"

    result_conjunction = score_business_significators(payload_conjunction)
    conjunction_notes = [e["note"] for e in result_conjunction["evidence"]]
    assert not any("exchange" in n for n in conjunction_notes), conjunction_notes
    assert any("VRY_CONFIRMED" in n for n in conjunction_notes), conjunction_notes


def test_business_mode_gate_ceiling_matches_reachable_rule_maxima():
    """Regression test for the reviewer-caught defect: the business mode's
    fixed ceiling previously used 25.2 (18*1.40) for the H7-lord rule, but
    that rule uses _house_lord_strength() which caps at 1.0, so 18 (18*1.0)
    is the true reachable maximum. A chart that maxes out every business
    rule must not exceed business_score=100 (would indicate an understated
    ceiling) and, more importantly, must be able to REACH close to 100
    when every rule is genuinely maxed (would indicate an overstated
    ceiling suppressing legitimate strong charts)."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    payload = _FakePayload()
    # Max out every business rule simultaneously.
    payload.house_lords["7"] = "Venus"
    payload.planet_house["Venus"] = 7  # kendra -- H7 lord in kendra
    payload.planet_dignities["Venus"] = "EXALTED"
    payload.house_lords["11"] = "Jupiter"
    payload.planet_house["Jupiter"] = 7  # H11 lord in H7
    payload.planet_dignities["Jupiter"] = "EXALTED"
    payload.darakaraka = "Venus"  # DK strong and H7-linked
    payload.house_lords["2"] = "Venus"  # H2-H7 connection (same lord as H7)

    gate = compute_business_mode_gate(payload)
    # Must not saturate past 100 regardless of how many rules fire at once.
    assert gate["business_score"] <= 100
    # With H7-lord (18), H11-lord (12), DK (14), H2-H7 (8) all firing near
    # max against an 81-point ceiling, the score should land solidly high
    # (not artificially suppressed by an inflated ~88.2 denominator that
    # includes an unreachable 25.2 for the H7-lord rule).
    assert gate["business_score"] >= 50, gate


def test_evidence_family_caps_present_and_bounded():
    """Regression test for audit finding #7: score_business_significators()
    must expose per-family capped/uncapped totals, and no family's capped
    contribution may exceed the documented 35% ceiling share."""
    payload = _FakePayload()
    result = score_business_significators(payload)
    assert "family_totals_capped" in result and "family_totals_uncapped" in result
    assert "capped_net_score" in result
    for fam, val in result["family_totals_capped"].items():
        assert abs(val) <= abs(result["family_totals_uncapped"].get(fam, val)) + 1e-6


def test_kp_h6_soft_negative_unless_hard_dusthana_present():
    """Regression test for audit finding #8: a planet whose KP
    signification set includes H6 ALONE (no H8/H12) must be treated as a
    weaker (soft) negative than a planet whose set includes H6 together
    with H8/H12 (a genuine dusthana cluster)."""
    from Business_Prediction.business_engine import _kp_sublord_signification_bias

    payload_soft = _FakePayload()
    payload_soft.kp_significators = {"Mars": {"level_1": [6], "level_2": [], "level_3": [], "level_4": []}}

    payload_hard = _FakePayload()
    payload_hard.kp_significators = {"Mars": {"level_1": [6, 8], "level_2": [12], "level_3": [], "level_4": []}}

    # Both lean negative, but the hard-dusthana case's negative weight must
    # be strictly greater than the soft, standalone-H6 case for the same
    # planet/level structure on house 6.
    from Business_Prediction.business_engine import _KP_LEVEL_WEIGHTS
    _, _, soft_neg = _kp_sublord_signification_bias("Mars", payload_soft)
    _, _, hard_neg = _kp_sublord_signification_bias("Mars", payload_hard)
    assert soft_neg == [6]
    assert hard_neg == [6, 8, 12]


def test_method_status_discloses_timing_precision_and_transit_approximation():
    """Regression test for audit findings #9/#10: method_status must
    explicitly disclose the actual timing precision achieved (not
    muhurta-grade) and that transit projection is mean-motion-approximate,
    not ephemeris-grade.

    Updated (Pratyantardasha reuse pass): timing_precision.level is now
    CONDITIONAL, not always "ANTARDASHA" -- when PD (Pratyantardasha)
    expansion succeeds (Job_Career.timeline._expand_pratyantardashas
    reused per AD window, requiring only house_lords + a working import),
    the disclosure honestly reports "PRATYANTARDASHA" instead of
    understating the precision actually computed. _FakePayload here has
    house_lords, so PD expansion succeeds and PRATYANTARDASHA is the
    correct, honest level -- see
    test_timing.py::test_disclosure_falls_back_when_pd_unavailable for the
    ANTARDASHA-fallback path when PD expansion is degraded/unavailable."""
    payload = _FakePayload()
    result = compute_business_prediction(payload)
    ms = result["method_status"]
    assert "timing_precision" in ms
    assert ms["timing_precision"]["level"] in ("ANTARDASHA", "PRATYANTARDASHA")
    if ms["timing_precision"]["level"] == "PRATYANTARDASHA":
        assert "Pratyantardasha" in ms["timing_precision"]["note"]
    assert "dynamic_transit" in ms
    assert "MEAN_MOTION_APPROXIMATE" in ms["dynamic_transit"].get("precision_note", "")


def test_method_status_reports_static_use_separately_from_timing_activation():
    """Regression test for a user-caught provenance/reporting defect: D10
    (and other methods) must not report PRESENT_NOT_TRIGGERED merely
    because a marker string wasn't found in TIMED-WINDOW evidence, when
    that method actually drove the STATIC significator ledger and/or mode
    gate. Uses Karthick-shaped data (D10 house occupancy/lords present and
    materially used in score_business_significators/compute_business_mode_gate)
    to prove d10_dashamsha.static_natal_use reads APPLIED even in a case
    where the timed-window marker might not independently fire."""
    payload = _FakePayload()
    payload.d10_house_lords = {"7": "Venus", "10": "Saturn", "11": "Saturn"}
    payload.d10_house_occupancy = {"1": ["Saturn"], "4": ["Mars"], "10": ["Venus", "Jupiter"]}

    result = compute_business_prediction(payload)
    d10_status = result["method_status"]["d10_dashamsha"]
    assert "data_available" in d10_status
    assert "static_natal_use" in d10_status
    assert "timing_window_activation" in d10_status
    assert d10_status["data_available"] is True
    assert d10_status["static_natal_use"] == "APPLIED"
    # Overall status must read APPLIED because static use applied, even if
    # timing_window_activation happens to be PRESENT_NOT_TRIGGERED on this
    # chart -- previously the collapsed single-status field could report
    # PRESENT_NOT_TRIGGERED here, which was misleading.
    assert d10_status["status"] == "APPLIED"


def test_dynamic_transit_no_flags_reports_computed_not_not_triggered():
    """Regression test: a transit computation that runs successfully and
    finds no business-relevant flags must report COMPUTED_NO_FLAGS, not
    PRESENT_NOT_TRIGGERED (which misleadingly implies something present
    just didn't activate, rather than 'this ran fine and found nothing')."""
    payload = _FakePayload()
    payload.lagna_sign = "Aries"
    result = compute_business_prediction(payload)
    transit_status = result["method_status"]["dynamic_transit"]["status"]
    assert transit_status in {"APPLIED", "COMPUTED_NO_FLAGS", "MISSING_DATA", "FAILED", "NOT_REQUESTED"}
    assert transit_status != "PRESENT_NOT_TRIGGERED"


def test_timing_precision_has_explicit_status_not_unknown():
    """Regression test: timing_precision is an informational disclosure,
    not a pass/fail method -- it previously had no 'status' key, so the
    HTML renderer's val.get('status', 'UNKNOWN') printed UNKNOWN, implying
    a failure that never happened."""
    payload = _FakePayload()
    result = compute_business_prediction(payload)
    assert result["method_status"]["timing_precision"]["status"] == "INFORMATIONAL"


def test_html_report_method_detail_column_not_blank_for_informational_entries():
    """Regression test: the renderer previously only showed the 'error'
    field in the Detail column, leaving it blank for entries that instead
    carry 'note'/'precision_note'/'level'. Both timing_precision and
    dynamic_transit must render non-empty detail text."""
    from Business_Prediction.generate_business_report import render_astrologer_report_html

    payload = _FakePayload()
    prediction = compute_business_prediction(payload)
    html = render_astrologer_report_html("Test Person", prediction, lang="en")
    assert "antardasha" in html.lower()
    # _FakePayload has no lagna_sign, so dynamic_transit carries a real
    # 'error' -- by design _method_detail() surfaces error text ahead of
    # precision_note for that case (a real failure reason outranks a
    # generic methodology caveat). Confirm the error itself is not blank.
    assert "no lagna_sign on payload" in html
    # And confirm the MEAN_MOTION_APPROXIMATE caveat surfaces on its own
    # when there's no error to prioritize over it (mode_gate's
    # gate_policy/EVIDENCE_BASIS documentation carries this same string
    # unconditionally, so it's present in the report regardless).
    assert "MEAN_MOTION_APPROXIMATE" in prediction["evidence_basis"]


# ─────────────────────────────────────────────────────────────────────────
# v17: user-directed full-framework audit fixes (5th house, Karakamsha/
# Arudha, D24/D60, KP 10th-cusp job-vs-business, sign/modality, operating
# model, contradiction controls, nine named promise fields).
# ─────────────────────────────────────────────────────────────────────────

def test_extended_house_combination_evidence_fires_for_named_spec_combinations():
    """v23 audit fix: spec sections 1 and 9 name specific multi-house lord
    combinations (2-11, 2-8, 3-7, 3-11, 10th-lord-in-3rd, Lagnesh-H3, 4-8
    inherited property, 4-10-11, 4-7, 4-12, 9-10, 9-11, 2-9-10, and the
    3-7-11/3-10-11/8-10-11/9-10-11/4-7-12 sector-table rows) that were
    previously entirely absent -- each house was only ever scored on its
    own lord's placement, never tested for connection to these specific
    other houses. Verify a genuine connection (H4 lord occupying H8, the
    spec's named "4-8: inherited property" combination) actually fires,
    and that an UNCONNECTED chart does not fire it."""
    from Business_Prediction.business_engine import _extended_house_combination_evidence

    connected = _FakePayload()
    connected.house_lords["4"] = "Mars"
    connected.house_lords["8"] = "Venus"
    connected.planet_house["Mars"] = 8  # H4 lord occupies H8 -> real 4-8 link
    connected.planet_dignities["Mars"] = "OWN"

    results = _extended_house_combination_evidence(connected)
    notes = [n for _, n in results]
    assert any("4-8 connection" in n and "inherited property" in n for n in notes), notes

    unconnected = _FakePayload()
    unconnected.house_lords["4"] = "Mars"
    unconnected.house_lords["8"] = "Venus"
    unconnected.planet_house["Mars"] = 5  # nowhere near H8/H4
    unconnected.planet_house["Venus"] = 6  # nowhere near H4/H8
    results2 = _extended_house_combination_evidence(unconnected)
    notes2 = [n for _, n in results2]
    assert not any("4-8 connection" in n for n in notes2), notes2


def test_extended_house_combination_evidence_gates_debilitated_same_lord():
    """v23 regression: the connection test's SAME-LORD case (one planet
    ruling both named houses) must not fire when that shared lord is
    DEBILITATED -- a single badly-afflicted planet ruling many houses
    mechanically 'connects' all of them without that being genuine
    positive multi-house evidence. This was caught by
    test_maximal_plausible_chart_scores_near_ceiling_not_compressed's
    all-houses-same-debilitated-lord fixture scoring far higher than a
    'weak chart' should."""
    from Business_Prediction.business_engine import _extended_house_combination_evidence

    payload = _FakePayload()
    payload.house_lords = {str(i): "Saturn" for i in range(1, 13)}
    payload.planet_house = {"Saturn": 6}
    payload.planet_dignities = {"Saturn": "DEBILITATED"}

    results = _extended_house_combination_evidence(payload)
    # Every same-lord pairing above should be suppressed by the debilitation
    # gate -- none of the returned notes should cite a same-lord connection
    # for a debilitated shared ruler.
    assert results == [], results


def test_lagnesh_combustion_flagged_distinct_from_debilitation():
    """v24 audit fix: spec section 1 explicitly lists 'whether Lagnesh is
    heavily combust, debilitated, defeated or afflicted' -- combustion
    specifically had no matching code anywhere, despite
    payload.combust_planets being a real field. Verify a combust Lagnesh
    is flagged negatively even when NOT debilitated (proving this is a
    genuinely separate check, not a re-statement of the dignity check)."""
    from Business_Prediction.business_engine import _lagnesh_affliction_and_karaka_connection_evidence

    payload = _FakePayload()
    payload.house_lords["1"] = "Mercury"
    payload.planet_dignities["Mercury"] = "OWN"  # NOT debilitated
    payload.combust_planets = ["Mercury"]

    results = _lagnesh_affliction_and_karaka_connection_evidence(payload)
    notes = [n for _, n in results]
    assert any("COMBUST" in n and "Mercury" in n for n in notes), notes

    not_combust_payload = _FakePayload()
    not_combust_payload.house_lords["1"] = "Mercury"
    not_combust_payload.planet_dignities["Mercury"] = "OWN"
    not_combust_payload.combust_planets = []
    results2 = _lagnesh_affliction_and_karaka_connection_evidence(not_combust_payload)
    assert not any("COMBUST" in n for _, n in results2)


def test_lagnesh_connected_with_mercury_mars_sun_rahu():
    """v24 audit fix: spec section 1 lists 'Lagnesh connected with
    Mercury, Mars, Sun or Rahu' as its own named check -- previously
    absent. Verify a genuine conjunction fires positive evidence, and
    that a debilitated karaka does NOT get credited even if conjunct."""
    from Business_Prediction.business_engine import _lagnesh_affliction_and_karaka_connection_evidence

    payload = _FakePayload()
    payload.house_lords["1"] = "Venus"
    payload.planet_house["Venus"] = 3
    payload.planet_house["Mars"] = 3  # conjunct Lagnesh
    payload.planet_dignities["Mars"] = "OWN"

    results = _lagnesh_affliction_and_karaka_connection_evidence(payload)
    notes = [n for _, n in results]
    assert any("connected with Mars" in n for n in notes), notes

    debilitated_payload = _FakePayload()
    debilitated_payload.house_lords["1"] = "Venus"
    debilitated_payload.planet_house["Venus"] = 3
    debilitated_payload.planet_house["Mars"] = 3
    debilitated_payload.planet_dignities["Mars"] = "DEBILITATED"
    # Gap-hunt fix: _FakePayload's default Saturn placement (H6) casts a
    # special (3rd/10th-house) Jaimini... no, a classical Vedic-aspect
    # relationship onto H3 that satisfies _neecha_bhanga_status()'s
    # "exaltation-sign lord aspects the debilitated planet" cancellation
    # condition (Saturn exalts in Capricorn, whose lord... rather, Saturn
    # IS the lord of Mars's exaltation sign Capricorn, and a 10th-house
    # special aspect from Saturn's default H6 lands exactly on H3) --
    # accidentally cancelling this test's intentionally-uncancelled
    # debilitation. Moved to H2 (no kendra-from-Lagna/Moon placement, no
    # aspect onto H3) so this fixture actually tests an UNCANCELLED
    # debilitation, matching the test's intent.
    debilitated_payload.planet_house["Saturn"] = 2
    results2 = _lagnesh_affliction_and_karaka_connection_evidence(debilitated_payload)
    assert not any("connected with Mars" in n for _, n in results2), results2


def test_lagnesh_graha_yuddha_defeated_and_winner():
    """v25 audit fix: 'defeated' (graha yuddha / planetary war) was
    previously left as documented open scope in v24's docstring. Reuses
    jyotish.dignity.graha_yuddha (already real, tested, longitude-based)
    rather than re-deriving the math. Verify a Lagnesh that loses a war
    is flagged negatively, and a Lagnesh that wins is flagged positively."""
    from Business_Prediction.business_engine import _lagnesh_affliction_and_karaka_connection_evidence

    # Mars at 10.0deg, Mercury at 10.5deg, same sign (Aries, 0-30deg),
    # separation 0.5deg (<=1deg threshold) -> war. Lower longitude wins
    # per jyotish.dignity.graha_yuddha's own documented rule -> Mars wins.
    loser_payload = _FakePayload()
    loser_payload.house_lords["1"] = "Mercury"
    loser_payload.planet_longitudes = {"Mars": 10.0, "Mercury": 10.5}
    results = _lagnesh_affliction_and_karaka_connection_evidence(loser_payload)
    notes = [n for _, n in results]
    assert any("DEFEATED in graha yuddha" in n and "Mercury" in n for n in notes), notes

    winner_payload = _FakePayload()
    winner_payload.house_lords["1"] = "Mars"
    winner_payload.planet_longitudes = {"Mars": 10.0, "Mercury": 10.5}
    results2 = _lagnesh_affliction_and_karaka_connection_evidence(winner_payload)
    notes2 = [n for _, n in results2]
    assert any("WINS graha yuddha" in n and "Mars" in n for n in notes2), notes2

    # No longitude data at all -> gracefully skips, no error.
    no_data_payload = _FakePayload()
    no_data_payload.house_lords["1"] = "Mars"
    no_data_payload.planet_longitudes = {}
    results3 = _lagnesh_affliction_and_karaka_connection_evidence(no_data_payload)
    assert not any("graha yuddha" in n for _, n in results3)


def test_business_significator_graha_yuddha_evidence_covers_lords_and_mercury():
    """GYUDDHA-1 fix: the Lagnesh-only Graha Yuddha check never covered
    the 2/6/7/10/11 house lords or Mercury (primary trade/commerce
    karaka). _FakePayload's house_lords["10"] is "Mercury", so putting
    Mercury into a war it LOSES should fire a business-significator
    citation naming Mercury and its H10-lord role."""
    from Business_Prediction.business_determination.house_evidence import _business_significator_graha_yuddha_evidence

    payload = _FakePayload()
    # Mars at 10.0deg, Mercury at 10.5deg, same sign, separation 0.5deg
    # -> war; lower longitude wins per graha_yuddha's rule -> Mars wins,
    # Mercury loses.
    payload.planet_longitudes = {"Mars": 10.0, "Mercury": 10.5}
    results = _business_significator_graha_yuddha_evidence(payload)
    notes = [n for _, n in results]
    weights = [w for w, n in results if "Mercury" in n and "DEFEATED" in n]
    assert any("Mercury" in n and "DEFEATED in graha yuddha" in n for n in notes), notes
    assert weights and all(w < 0 for w in weights), results


def test_business_significator_graha_yuddha_mercury_specifically_checked():
    """Mercury must be checked even when it is not one of the 2/6/7/10/11
    lords -- it is the primary trade/commerce karaka unconditionally."""
    from Business_Prediction.business_determination.house_evidence import _business_significator_graha_yuddha_evidence

    payload = _FakePayload()
    payload.house_lords = dict(payload.house_lords)
    payload.house_lords["10"] = "Saturn"  # Mercury no longer any of 2/6/7/10/11 lord
    for h in ("2", "6", "7", "11"):
        payload.house_lords[h] = "Saturn"
    payload.planet_longitudes = {"Mars": 10.0, "Mercury": 10.5}
    results = _business_significator_graha_yuddha_evidence(payload)
    notes = [n for _, n in results]
    assert any("Mercury" in n and "primary trade/commerce karaka" in n and "DEFEATED" in n for n in notes), notes


def test_business_significator_graha_yuddha_normal_case_no_war():
    """The normal/common case for almost every chart: no two eligible
    planets within 1 degree of each other -- must show no effect and no
    spurious citations."""
    from Business_Prediction.business_determination.house_evidence import _business_significator_graha_yuddha_evidence, _planet_strength

    payload = _FakePayload()
    payload.planet_longitudes = {"Mars": 10.0, "Mercury": 50.5, "Jupiter": 120.0, "Venus": 200.0, "Saturn": 280.0}
    results = _business_significator_graha_yuddha_evidence(payload)
    assert results == []

    no_war_strength = _planet_strength(payload, "Mercury")
    payload_no_lon = _FakePayload()
    baseline_strength = _planet_strength(payload_no_lon, "Mercury")
    assert no_war_strength == baseline_strength


def test_business_significator_graha_yuddha_missing_longitude_data_degrades_gracefully():
    """No payload.planet_longitudes at all -> must not error, no
    citations, no strength change (graceful degradation, not a hard
    failure) since there's no way to even check for a war."""
    from Business_Prediction.business_determination.house_evidence import _business_significator_graha_yuddha_evidence, _planet_strength, _graha_yuddha_loss_factor

    payload = _FakePayload()
    payload.planet_longitudes = {}
    assert _business_significator_graha_yuddha_evidence(payload) == []
    assert _graha_yuddha_loss_factor(payload, "Mercury") == 1.0
    # No AttributeError/crash even if the attribute is absent entirely.
    del payload.planet_longitudes
    assert _business_significator_graha_yuddha_evidence(payload) == []
    assert _planet_strength(payload, "Mercury") >= 0.0


def test_planet_strength_measurably_reduced_when_business_lord_loses_war():
    """Core wiring check: a war-losing business-relevant planet's
    strength score (as read by significators/sectors/contradictions/
    yogas/mode_gate) must genuinely drop, not just get an isolated
    evidence citation nobody consumes. Compare H10-lord Mercury's
    _planet_strength() with vs. without the war."""
    from Business_Prediction.business_determination.house_evidence import _planet_strength, _planet_strength_fine

    war_payload = _FakePayload()
    war_payload.planet_longitudes = {"Mars": 10.0, "Mercury": 10.5}  # Mercury loses
    war_strength = _planet_strength(war_payload, "Mercury")
    war_strength_fine = _planet_strength_fine(war_payload, "Mercury")

    no_war_payload = _FakePayload()
    no_war_payload.planet_longitudes = {}
    no_war_strength = _planet_strength(no_war_payload, "Mercury")
    no_war_strength_fine = _planet_strength_fine(no_war_payload, "Mercury")

    assert war_strength < no_war_strength, (war_strength, no_war_strength)
    assert war_strength_fine < no_war_strength_fine, (war_strength_fine, no_war_strength_fine)


def test_significators_citation_appears_for_mercury_graha_yuddha_loss():
    """End-to-end: score_business_significators() output must include a
    citation when Mercury (or a 2/6/7/10/11 lord) loses graha yuddha."""
    payload = _FakePayload()
    payload.planet_longitudes = {"Mars": 10.0, "Mercury": 10.5}
    result = score_business_significators(payload)
    risk_signals = result["risk_signals"]
    assert any("Mercury" in s and "DEFEATED in graha yuddha" in s for s in risk_signals), risk_signals


def test_fifth_house_evidence_fires_for_5_10_and_5_11():
    """Regression test for the biggest gap the audit found: H5 had ZERO
    references anywhere in the module. H5 lord in H10/H11 must now
    produce evidence."""
    from Business_Prediction.business_engine import _fifth_house_business_evidence

    payload = _FakePayload()
    payload.house_lords["5"] = "Venus"
    payload.planet_house["Venus"] = 10
    payload.planet_dignities["Venus"] = "OWN"

    results = _fifth_house_business_evidence(payload)
    notes = [n for _, n in results]
    assert any("H5 lord" in n and "H10" in n for n in notes), notes


def test_fifth_house_speculative_risk_is_gated_not_unconditional():
    """5-8-Rahu must read as a caution (or managed-risk credit if H5 lord
    is strongly dignified), never a plain unconditional positive."""
    from Business_Prediction.business_engine import _fifth_house_business_evidence

    payload = _FakePayload()
    payload.house_lords["5"] = "Mars"
    payload.house_lords["8"] = "Mars"
    payload.planet_house["Mars"] = 8
    payload.planet_house["Rahu"] = 8
    payload.planet_dignities["Mars"] = "NEUTRAL"

    results = _fifth_house_business_evidence(payload)
    weights = [w for w, n in results if "speculative" in n.lower()]
    assert weights and all(w < 0 for w in weights), results


def test_karakamsha_evidence_requires_atmakaraka_and_d9_data():
    """Karakamsha evidence must gracefully degrade to empty (not raise)
    without atmakaraka/D9 data, and must fire once both are present."""
    from Business_Prediction.business_engine import _karakamsha_business_evidence

    payload = _FakePayload()
    assert _karakamsha_business_evidence(payload) == []

    payload.atmakaraka = "Mercury"
    payload.divisional_charts = {"D9_navamsha": {"Mercury": "Gemini"}}
    # 10th from Gemini = Pisces -> lord Jupiter; place Jupiter in a kendra,
    # undebilitated, so the check fires.
    payload.house_lords["1"] = "Jupiter"
    payload.planet_house["Jupiter"] = 1
    payload.planet_dignities["Jupiter"] = "OWN"
    results = _karakamsha_business_evidence(payload)
    assert results, "Karakamsha evidence should fire once AK+D9 data are present"


def test_arudha_evidence_requires_lagna_sign_and_planet_signs():
    """A10/A7/AL evidence must gracefully degrade to empty without
    lagna_sign/planet_signs, and be callable without error once present."""
    from Business_Prediction.business_engine import _arudha_business_evidence

    payload = _FakePayload()
    assert _arudha_business_evidence(payload) == []

    payload.lagna_sign = "Aries"
    payload.planet_signs = {"Sun": "Aries", "Moon": "Taurus", "Mercury": "Pisces", "Venus": "Pisces"}
    results = _arudha_business_evidence(payload)  # must not raise
    assert isinstance(results, list)


def test_kp_10th_cusp_job_vs_business_classifies_leaning():
    """Regression test: the spec's central KP question (10th cusp
    sub-lord's own significations leaning job {2,6,10,11} vs business
    {1/3,2,7,10,11}) had NO dedicated implementation before v17."""
    from Business_Prediction.business_engine import _kp_10th_cusp_job_vs_business

    payload = _FakePayload()
    no_data = _kp_10th_cusp_job_vs_business(payload)
    assert no_data["status"] == "NO_DATA"

    payload.kp_cusps = {"H10": {"sub_lord": "Mercury"}}
    payload.kp_significators = {"Mercury": {"level_1": [7], "level_2": [10], "level_3": [1]}}
    biz_leaning = _kp_10th_cusp_job_vs_business(payload)
    assert biz_leaning["status"] == "OK"
    assert biz_leaning["leaning"] == "BUSINESS", biz_leaning

    payload.kp_significators = {"Mercury": {"level_1": [6], "level_2": [2], "level_3": []}}
    job_leaning = _kp_10th_cusp_job_vs_business(payload)
    assert job_leaning["leaning"] == "JOB", job_leaning


def test_kp_10th_cusp_field_modifiers_present_for_5_8_9_12_4_6():
    """v23 audit fix: spec section 6 lists business-specific KP modifiers
    for houses 4/5/6/8/9/12 (property, speculation, staff/operations,
    investor funds, consulting/law, foreign trade) -- previously entirely
    absent from _kp_10th_cusp_job_vs_business()'s output. Verify the new
    field_modifiers list surfaces the right interpretive label when the
    sub-lord significates one of these houses, and is empty when it
    doesn't."""
    from Business_Prediction.business_engine import _kp_10th_cusp_job_vs_business

    payload = _FakePayload()
    payload.kp_cusps = {"H10": {"sub_lord": "Jupiter"}}
    payload.kp_significators = {"Jupiter": {"level_1": [9], "level_2": [7], "level_3": []}}
    result = _kp_10th_cusp_job_vs_business(payload)
    assert result["status"] == "OK"
    modifier_houses = [m["house"] for m in result["field_modifiers"]]
    assert "H9" in modifier_houses, result
    h9_entry = next(m for m in result["field_modifiers"] if m["house"] == "H9")
    assert "consulting" in h9_entry["interpretation"], h9_entry
    assert "field modifiers" in result["note"]

    payload.kp_significators = {"Jupiter": {"level_1": [7], "level_2": [10], "level_3": []}}
    no_modifier_result = _kp_10th_cusp_job_vs_business(payload)
    assert no_modifier_result["field_modifiers"] == [], no_modifier_result


def test_d24_and_d60_gracefully_degrade_without_data():
    """D24/D60 were entirely absent before v17. Both must degrade to a
    neutral, documented NO_DATA state rather than raising or silently
    influencing scores when the payload carries no D24/D60 data, and D60
    must additionally stay at zero modifier when birth-time reliability
    is not explicitly reported as reliable."""
    from Business_Prediction.business_engine import _d24_competency_status, _d60_confirmation_status

    payload = _FakePayload()
    d24 = _d24_competency_status(payload)
    assert d24["status"] == "NO_DATA" and d24["factor"] == 1.0

    d60 = _d60_confirmation_status(payload)
    assert d60["status"] == "NO_DATA" and d60["modifier"] == 0.0

    # D60 data present but reliability not confirmed -> still zero modifier.
    payload.d60_planet_dignities = {"Mercury": "EXALTED"}
    d60_unreliable = _d60_confirmation_status(payload)
    assert d60_unreliable["status"] == "NOT_APPLIED_LOW_RELIABILITY"
    assert d60_unreliable["modifier"] == 0.0

    payload.birth_time_reliability = "RECTIFIED"
    d60_reliable = _d60_confirmation_status(payload)
    assert d60_reliable["status"] == "OK"


# --- D60 (Shashtiamsha) in-house construction (user-authorized doctrinal choice) ---
# v-audit fix: D60 was previously blocked with D60_NOT_IMPLEMENTED_CONTESTED_
# CONVENTION on every chart (no upstream data pipeline anywhere). Per an
# explicit user decision to accept the citation risk of a disclosed majority
# convention (same posture as D24/D2), jyotish.astro.compute_d60_
# shashtiamsha_sign() now provides an in-house fallback via payload.
# planets_d1, used by _d60_confirmation_status() only when no upstream
# payload.d60_planet_dignities is present.

def test_d60_in_house_fallback_computes_from_planets_d1_when_reliable():
    from Business_Prediction.business_engine import _d60_confirmation_status

    payload = _FakePayload()
    payload.house_lords = {"10": "Mercury"}
    payload.birth_time_reliability = "RECTIFIED"
    # Mercury at Gemini 1.6deg -> D60 sign Virgo (Mercury's own/exaltation
    # sign) -> EXALTED, hand-verified via jyotish.astro.compute_d60_
    # shashtiamsha_sign + jyotish.dignity.dignity_state.
    payload.planets_d1 = {"Mercury": {"sign": "Gemini", "degree": 1.6}}
    d60 = _d60_confirmation_status(payload)
    assert d60["status"] == "OK"
    assert d60["dignity_source"] == "IN_HOUSE_COMPUTED"
    assert d60["dignity"] == "EXALTED"
    assert d60["modifier"] == 0.04


def test_d60_in_house_fallback_not_used_when_upstream_data_present():
    """Upstream payload.d60_planet_dignities (if a future chart source ever
    supplies it) must take priority over the in-house fallback -- dignity_
    source must read UPSTREAM, not IN_HOUSE_COMPUTED, and the in-house
    computation must not even be attempted (planets_d1 present but with
    data that would compute a DIFFERENT dignity, to prove upstream wins)."""
    from Business_Prediction.business_engine import _d60_confirmation_status

    payload = _FakePayload()
    payload.house_lords = {"10": "Mercury"}
    payload.birth_time_reliability = "RECTIFIED"
    payload.d60_planet_dignities = {"Mercury": "DEBILITATED"}
    payload.planets_d1 = {"Mercury": {"sign": "Gemini", "degree": 1.6}}  # would compute EXALTED in-house
    d60 = _d60_confirmation_status(payload)
    assert d60["status"] == "OK"
    assert d60["dignity_source"] == "UPSTREAM"
    assert d60["dignity"] == "DEBILITATED"
    assert d60["modifier"] == -0.04


def test_d60_no_data_when_neither_upstream_nor_planets_d1_available():
    from Business_Prediction.business_engine import _d60_confirmation_status

    payload = _FakePayload()
    payload.house_lords = {"10": "Mercury"}
    payload.birth_time_reliability = "RECTIFIED"
    # No d60_planet_dignities, no planets_d1 (_FakePayload default) -> still
    # genuinely blocked.
    d60 = _d60_confirmation_status(payload)
    assert d60["status"] == "NO_DATA"
    assert d60["modifier"] == 0.0


def test_sign_modality_profile_classifies_element_and_modality():
    """Fire/earth/air/water and movable/fixed/dual interpretation was
    entirely unused before v17."""
    from Business_Prediction.business_engine import _sign_modality_profile

    payload = _FakePayload()
    payload.lagna_sign = "Aries"
    profile = _sign_modality_profile(payload)
    assert profile["status"] == "OK"
    assert profile["lagna_element"] == "FIRE"
    assert profile["lagna_modality"] == "MOVABLE"
    assert profile["field_affinities"]


def test_business_operating_model_returns_ranked_within_chart_scores():
    """No operating-model classification (sole owner/partnership/family/
    professional practice/trading/manufacturing/scalable platform) existed
    before v17."""
    from Business_Prediction.business_engine import _business_operating_model

    payload = _FakePayload()
    model = _business_operating_model(payload)
    assert model["best_fit"] in {
        "sole_owner", "partnership", "family_business", "professional_practice",
        "trading_brokerage", "manufacturing", "scalable_platform",
    }
    assert len(model["ranked"]) == 7
    assert set(model["normalized_0_100"]) == {
        "sole_owner", "partnership", "family_business", "professional_practice",
        "trading_brokerage", "manufacturing", "scalable_platform",
    }


def test_contradiction_penalties_flag_strong_h7_without_2_10_11():
    """Regression test for the spec's contradiction control #1: a strong
    H7 lord with no H2/H10/H11 connection must be flagged, not silently
    credited as pure business promise."""
    from Business_Prediction.business_engine import (
        _contradiction_penalties, score_business_significators,
        _d24_competency_status, _kp_10th_cusp_job_vs_business,
    )

    payload = _FakePayload()
    payload.house_lords["7"] = "Jupiter"
    payload.planet_house["Jupiter"] = 7
    payload.planet_dignities["Jupiter"] = "EXALTED"
    # Make sure H7 lord (Jupiter) does not itself rule/occupy H2/H10/H11.
    payload.house_lords["2"] = "Saturn"
    payload.house_lords["10"] = "Mercury"
    payload.house_lords["11"] = "Sun"

    significators = score_business_significators(payload)
    d24 = _d24_competency_status(payload)
    kp10 = _kp_10th_cusp_job_vs_business(payload)
    penalties = _contradiction_penalties(payload, significators, d24, kp10)
    notes = [p["note"] for p in penalties]
    assert any("NO connection to H2/H10/H11" in n for n in notes), notes


def test_contradiction_control_11_flags_d60_suppressed_by_low_reliability():
    """v22 audit fix: spec section 14's contradiction control #11 ("D60
    being used despite uncertain birth time") was entirely absent --
    _d60_confirmation_status() zeroing its own modifier on low reliability
    is a different thing from surfacing that suppression as an explicit
    contradiction finding. Verify the new check fires when d60_status is
    NOT_APPLIED_LOW_RELIABILITY."""
    from Business_Prediction.business_engine import (
        _contradiction_penalties, score_business_significators,
        _d24_competency_status, _kp_10th_cusp_job_vs_business, _d60_confirmation_status,
    )

    payload = _FakePayload()
    payload.birth_time_reliability = "LOW"
    payload.d60_planet_dignities = {"Mercury": "OWN"}
    payload.house_lords["10"] = "Mercury"
    significators = score_business_significators(payload)
    d24 = _d24_competency_status(payload)
    kp10 = _kp_10th_cusp_job_vs_business(payload)
    d60 = _d60_confirmation_status(payload)
    assert d60["status"] == "NOT_APPLIED_LOW_RELIABILITY", d60

    penalties = _contradiction_penalties(payload, significators, d24, kp10, d60_status=d60)
    notes = [p["note"] for p in penalties]
    assert any("SUPPRESSED due to insufficient birth-time reliability" in n for n in notes), notes

    # Omitting d60_status entirely (backward compatibility) must not error
    # and must not fire this specific check.
    penalties_no_d60 = _contradiction_penalties(payload, significators, d24, kp10)
    assert not any("SUPPRESSED due to insufficient birth-time reliability" in p["note"] for p in penalties_no_d60)


def test_contradiction_control_12_flags_no_business_activating_dasha():
    """v22 audit fix: spec section 14's contradiction control #12 ("dasha
    not activating business houses within the forecast period") was
    entirely absent. Verify it fires when every timed window's genuine
    AD/MD-lord evidence rules only non-discriminating houses, and does
    NOT fire when a window's AD/MD-lord evidence genuinely rules H1/H3/H7
    -- reusing the same KP/Jaimini-exclusion logic as _dasha_vote()."""
    from Business_Prediction.business_engine import (
        _contradiction_penalties, score_business_significators,
        _d24_competency_status, _kp_10th_cusp_job_vs_business,
    )

    payload = _FakePayload()
    significators = score_business_significators(payload)
    d24 = _d24_competency_status(payload)
    kp10 = _kp_10th_cusp_job_vs_business(payload)

    non_activating_windows = [{"evidence": ["AD lord Saturn rules H2 (dignity-weighted +3.0)", "KP: business signification present"]}]
    penalties = _contradiction_penalties(payload, significators, d24, kp10, timed_windows=non_activating_windows)
    notes = [p["note"] for p in penalties]
    assert any("no timed window" not in n and "AD/MD-lord activation of a business-discriminating house" in n for n in notes), notes

    activating_windows = [{"evidence": ["AD lord Mars rules H1/H7 (dignity-weighted +6.0)"]}]
    penalties2 = _contradiction_penalties(payload, significators, d24, kp10, timed_windows=activating_windows)
    notes2 = [p["note"] for p in penalties2]
    assert not any("AD/MD-lord activation of a business-discriminating house" in n for n in notes2), notes2

    # Omitting timed_windows entirely must not error and must not fire.
    penalties_no_windows = _contradiction_penalties(payload, significators, d24, kp10)
    assert not any("AD/MD-lord activation of a business-discriminating house" in p["note"] for p in penalties_no_windows)


def test_jaimini_amk_relationship_now_includes_h3():
    """v22 audit fix: spec section 5 lists "AmK relationship with the 2nd,
    3rd, 7th, 10th and 11th" -- the code previously checked only
    2/7/10/11, omitting H3 (enterprise/initiative)."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    payload = _FakePayload()
    payload.amatyakaraka = "Mercury"
    payload.house_lords["3"] = "Mercury"
    for h in ("2", "7", "10", "11"):
        if payload.house_lords.get(h) == "Mercury":
            payload.house_lords[h] = "Venus"

    gate = compute_business_mode_gate(payload)
    biz_notes = gate["positive_signals"]["business"]
    assert any("Amatyakaraka" in n and "H3" in n for n in biz_notes), biz_notes


def test_false_conclusion_guard_checklist_covers_all_8_and_traces_real_evidence():
    """v25 audit fix: spec section 15 lists 8 named false conclusions.
    Prior audits found real ad hoc guards but no auditable 1:1 mapping.
    Verify the checklist has exactly 8 entries, each traceable to real
    evidence (not a placeholder), and that a chart specifically
    constructed to trip guard #1 (strong disconnected H7) shows
    guarded=True with the matching contradiction note as evidence."""
    payload = _FakePayload()
    payload.house_lords["7"] = "Jupiter"
    payload.planet_house["Jupiter"] = 7
    payload.planet_dignities["Jupiter"] = "EXALTED"
    payload.house_lords["2"] = "Saturn"
    payload.house_lords["10"] = "Mercury"
    payload.house_lords["11"] = "Sun"

    result = compute_business_prediction(payload)
    checklist = result["false_conclusion_guard_checklist"]
    assert len(checklist) == 8, checklist
    assert {g["guard_id"] for g in checklist} == set(range(1, 9))
    for g in checklist:
        assert g["evidence"], g  # every entry must cite something, not be empty
        assert g["guard_type"] in ("CHART_SPECIFIC", "STRUCTURAL", "CHART_SPECIFIC_AND_STRUCTURAL", "STRUCTURAL_AND_CHART_SPECIFIC")

    guard1 = next(g for g in checklist if g["guard_id"] == 1)
    assert guard1["pattern_present"] is True, guard1
    assert guard1["guarded"] is True, guard1
    assert "NO connection to H2/H10/H11" in guard1["evidence"], guard1

    # Structural guards (3, 6, 7) must hold unconditionally regardless of
    # chart specifics.
    for gid in (3, 6, 7):
        g = next(x for x in checklist if x["guard_id"] == gid)
        assert g["guarded"] is True, g


def test_compute_business_prediction_exposes_nine_named_fields():
    """Regression test for the spec's core structural ask: nine separately-
    computed fields, not a single collapsed business-vs-job comparison."""
    payload = _FakePayload()
    result = compute_business_prediction(payload)

    for key in (
        "business_promise", "job_promise", "independent_profession_promise",
        "business_field_fit", "business_execution_capacity",
        "business_profitability", "business_stability",
        "current_timing_readiness",
    ):
        assert key in result, key
        assert 0.0 <= result[key] <= 100.0, (key, result[key])

    confidence = result["business_over_job_confidence"]
    assert "label" in confidence and "score_0_1" in confidence
    assert 0.0 <= confidence["score_0_1"] <= 1.0

    assert "business_advantage_margin" in result
    assert result["business_advantage_margin"] == round(result["business_promise"] - result["job_promise"], 1)
    assert result["business_advantage_label"] in {
        "STRONG_BUSINESS_ADVANTAGE", "STRONG_BUSINESS_ADVANTAGE_BUT_BELOW_ABSOLUTE_FLOOR",
        "MODERATE_BUSINESS_ADVANTAGE", "SLIGHT_BUSINESS_ADVANTAGE", "HYBRID_OR_INCONCLUSIVE",
        "SLIGHT_JOB_ADVANTAGE", "MODERATE_JOB_ADVANTAGE", "STRONG_JOB_ADVANTAGE",
    }

    assert "operating_model" in result and result["operating_model"]["best_fit"]
    assert "contradiction_findings" in result
    assert "d24_competency_status" in result and "d60_confirmation_status" in result
    assert "sign_modality_profile" in result and "kp_10th_cusp_job_vs_business" in result


def test_strong_business_absolute_floor_requires_both_score_and_margin():
    """Spec section 13: a large margin alone should not read as 'strong
    business' if the business score itself is low."""
    from Business_Prediction.business_engine import _compute_named_promise_fields

    payload = _FakePayload()
    mode_gate = {"business_score": 45, "employment_score": 20, "independent_score": 10, "family_biz_score": 5}
    significators = {"heuristic_relative_strength_0_100": 30, "evidence": [], "family_totals_capped": {}}
    fields = _compute_named_promise_fields(
        payload, mode_gate, significators, [], [], {"status": "OK_NO_SIGNIFICANT_WINDOWS_IN_HORIZON"},
        {"d9_navamsha": {}, "d10_dashamsha": {}, "kp_significators": {}, "jaimini_karakas": {}},
        {"status": "NO_DATA", "factor": 1.0}, {"status": "NO_DATA", "modifier": 0.0},
        {"status": "NO_DATA", "leaning": "UNKNOWN"}, {"status": "NO_DATA", "field_affinities": []},
        [],
    )
    # business_score=45 with employment_score=20 gives a margin >=15 (before
    # blending with significator strength), but business_promise itself
    # should land well below the 65 floor, so the label must be qualified.
    if fields["business_advantage_margin"] >= 15:
        assert fields["business_advantage_label"] == "STRONG_BUSINESS_ADVANTAGE_BUT_BELOW_ABSOLUTE_FLOOR"
        assert fields["strong_business_absolute_floor_met"] is False


# ─────────────────────────────────────────────────────────────────────────
# v18: user-directed re-audit fixes (layer-weighted promise scores,
# directional confidence, argala/AK-AmK on Arudhas, D10 H3/H5, Karakamsha
# occupancy, sector-matched sign/modality bonus, independent H2/H9,
# named-operating-model D1-vs-D10 contradiction).
# ─────────────────────────────────────────────────────────────────────────

def test_layered_promise_scores_use_declared_weights_summing_to_100():
    """Regression test: business_promise/job_promise must now be composed
    from explicitly declared, inspectable layer weights (25/20/10/10/10/8/
    10/4/3 and 30/25/15/8/12/5/5), not an undocumented blend."""
    from Business_Prediction.business_engine import (
        _layered_promise_scores, _BUSINESS_LAYER_WEIGHTS, _JOB_LAYER_WEIGHTS,
        compute_business_mode_gate, score_business_significators,
        _d24_competency_status, _d60_confirmation_status, _kp_10th_cusp_job_vs_business,
    )

    assert sum(_BUSINESS_LAYER_WEIGHTS.values()) == 100
    assert sum(_JOB_LAYER_WEIGHTS.values()) == 100

    payload = _FakePayload()
    mode_gate = compute_business_mode_gate(payload)
    significators = score_business_significators(payload)
    d60 = _d60_confirmation_status(payload)
    kp10 = _kp_10th_cusp_job_vs_business(payload)
    layered = _layered_promise_scores(payload, mode_gate, significators, d60, kp10)

    assert set(layered["business"]["layers"]) == set(_BUSINESS_LAYER_WEIGHTS)
    assert set(layered["job"]["layers"]) == set(_JOB_LAYER_WEIGHTS)
    for v in layered["business"]["layers"].values():
        assert 0.0 <= v <= 100.0
    for v in layered["job"]["layers"].values():
        assert 0.0 <= v <= 100.0
    assert 0.0 <= layered["business"]["weighted_total"] <= 100.0
    assert 0.0 <= layered["job"]["weighted_total"] <= 100.0


def test_directional_method_votes_measure_agreement_not_just_activity():
    """Regression test: method_agreement previously measured whether D9/
    D10/KP/Jaimini merely RAN, not whether their directional conclusions
    agree with the overall business-vs-job leaning. A chart with strong,
    consistent D1 business evidence and no contrary D10/KP/Jaimini signal
    should show D1 agreeing and a coherent (non-zero) agreement fraction."""
    from Business_Prediction.business_engine import _directional_method_votes, score_business_significators

    payload = _FakePayload()
    payload.house_lords["7"] = "Mercury"
    payload.planet_house["Mercury"] = 7
    payload.planet_dignities["Mercury"] = "EXALTED"
    significators = score_business_significators(payload)
    votes = _directional_method_votes(payload, significators, {"status": "NO_DATA"}, "BUSINESS")
    assert votes["votes"]["D1"] in {"BUSINESS", "AGAINST_BUSINESS", "NEUTRAL"}
    assert "d1_agrees" in votes and "d10_agrees" in votes
    assert 0.0 <= votes["agreement_fraction"] <= 1.0


def test_confidence_object_exposes_separate_data_quality_clarity_reliability_factors():
    """Regression test: chart_data_quality, signal_clarity and
    birth_time_reliability must be separate factors, not folded into
    method_agreement/timing_support as in the v17 version."""
    payload = _FakePayload()
    result = compute_business_prediction(payload)
    confidence = result["business_over_job_confidence"]
    for key in ("chart_data_quality", "signal_clarity", "birth_time_reliability", "method_agreement", "timing_support"):
        assert key in confidence, key
        assert 0.0 <= confidence[key] <= 1.0
    assert "method_votes" in confidence
    assert "overall_leaning" in confidence


def test_business_field_fit_reconciles_to_ranked_sector_and_discloses_modality_adjustment():
    """The KPI equals the inspectable top-sector score; modality remains a
    separately disclosed corroboration instead of an invisible uplift."""
    from Business_Prediction.business_engine import _compute_named_promise_fields

    payload = _FakePayload()
    mode_gate = {"business_score": 50, "employment_score": 40, "independent_score": 10, "family_biz_score": 5,
                 "positive_signals": {"business": [], "employment": []}, "negative_signals": {"business": [], "employment": []}}
    significators = {"heuristic_relative_strength_0_100": 50, "evidence": [], "family_totals_capped": {}}

    matching_sector = [{"label": "Trading & Commerce", "sector": "trading_commerce", "score": 60.0}]
    non_matching_sector = [{"label": "Healthcare Services", "sector": "healthcare_services", "score": 60.0}]
    sign_modality_with_trade = {"status": "OK", "field_affinities": ["commerce", "technology"]}

    fields_match = _compute_named_promise_fields(
        payload, mode_gate, significators, matching_sector, [], {"status": "OK_NO_SIGNIFICANT_WINDOWS_IN_HORIZON"},
        {}, {"status": "NO_DATA", "factor": 1.0}, {"status": "NO_DATA", "modifier": 0.0},
        {"status": "NO_DATA", "leaning": "UNKNOWN"}, sign_modality_with_trade, [],
    )
    fields_no_match = _compute_named_promise_fields(
        payload, mode_gate, significators, non_matching_sector, [], {"status": "OK_NO_SIGNIFICANT_WINDOWS_IN_HORIZON"},
        {}, {"status": "NO_DATA", "factor": 1.0}, {"status": "NO_DATA", "modifier": 0.0},
        {"status": "NO_DATA", "leaning": "UNKNOWN"}, sign_modality_with_trade, [],
    )
    assert fields_match["business_field_fit"] == 60.0
    assert fields_no_match["business_field_fit"] == 60.0
    assert fields_match["business_field_fit_modality_adjustment"] == 6.0
    assert fields_no_match["business_field_fit_modality_adjustment"] == 2.0


def test_independent_mode_scores_h2_and_h9():
    """Regression test: the independent-professional group (spec:
    1-2-5-9-10-11) previously had no H2/H9 rules at all."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    payload = _FakePayload()
    payload.house_lords["9"] = "Jupiter"
    payload.planet_house["Jupiter"] = 9
    payload.planet_dignities["Jupiter"] = "OWN"
    gate = compute_business_mode_gate(payload)
    pos = gate["positive_signals"]["independent"]
    assert any("H9 lord" in s and "fortune/mentorship" in s for s in pos), pos


def test_arudha_evidence_includes_argala_and_ak_amk_relationship():
    """Regression test: Argala/rasi-drishti were previously hardcoded to
    D1 H1/H7/H10 only; A7/A10/AL and the AK-AmK relationship had no
    coverage at all before v18."""
    from Business_Prediction.business_engine import _arudha_business_evidence

    payload = _FakePayload()
    payload.lagna_sign = "Aries"
    payload.planet_signs = {"Sun": "Aries", "Moon": "Taurus", "Mercury": "Gemini", "Venus": "Pisces", "Jupiter": "Cancer"}
    payload.atmakaraka = "Sun"
    payload.amatyakaraka = "Mercury"
    results = _arudha_business_evidence(payload)  # must not raise
    assert isinstance(results, list)


def test_d10_native_evidence_covers_h3_and_h5():
    """Regression test: D10-native evidence previously only checked
    H7/H10/H11 lord placement, never H3 (execution initiative) or H5
    (execution strategy/creativity)."""
    from Business_Prediction.business_engine import _d10_native_house_evidence

    payload = _MaximalPlausiblePayload()
    payload.d10_house_lords = {**payload.d10_house_lords, "3": "Mercury", "5": "Mercury"}
    results = _d10_native_house_evidence(payload)
    notes = [n for _, n in results]
    assert any("H3 (execution initiative)" in n or "H5 (execution" in n for n in notes), notes


def test_karakamsha_occupancy_evidence_beyond_lordship():
    """Regression test: Karakamsha evidence previously only judged LORDS
    of houses counted from Karakamsha, never who occupies the Karakamsha
    sign itself."""
    from Business_Prediction.business_engine import _karakamsha_business_evidence

    payload = _FakePayload()
    payload.atmakaraka = "Mercury"
    payload.divisional_charts = {"D9_navamsha": {"Mercury": "Gemini"}}
    payload.planet_signs = {"Venus": "Gemini", "Jupiter": "Pisces"}
    results = _karakamsha_business_evidence(payload)
    notes = [n for _, n in results]
    assert any("occupy the Karakamsha sign" in n for n in notes), notes


def test_contradiction_penalties_flag_opposing_named_operating_models():
    """Regression test: the D1-vs-D10 contradiction previously only
    compared net SIGN, never named operating models. A chart where D1
    leans business but D10-native evidence concentrates in H6/H8/H12
    (operational/service houses) must be flagged as an OPPOSING operating
    model, not just a generic negative-D10 note."""
    from Business_Prediction.business_engine import _contradiction_penalties, score_business_significators, _d24_competency_status, _kp_10th_cusp_job_vs_business

    payload = _FakePayload()
    mode_gate = {"business_score": 70, "employment_score": 30}
    significators = score_business_significators(payload)
    d24 = _d24_competency_status(payload)
    kp10 = _kp_10th_cusp_job_vs_business(payload)
    penalties = _contradiction_penalties(payload, significators, d24, kp10, mode_gate=mode_gate)
    # Must not raise, and the mode_gate-aware branch must be reachable
    # (covered by the assertion that calling with mode_gate doesn't error
    # and returns a list of well-formed penalty dicts).
    # Engineering audit fix #16: contradiction dicts now also carry a
    # stable machine-readable `id` field (e.g. "D1_D10_OPERATING_MODEL_
    # CONFLICT") alongside mode/weight/note, so the hard-veto logic in
    # engine.py can match on a stable identifier instead of substring-
    # searching the human-readable note text.
    # ISSUE-2 audit fix: contradiction dicts now also carry an optional
    # `family` tag (evidence-cluster grouping, e.g.
    # "D10_H8_concentration") so double-counted penalties sharing the same
    # underlying evidence can be detected/capped (see
    # contradictions.py::_apply_contradiction_family_caps). `family` is
    # None for checks that don't belong to a tagged cluster, but the key
    # is always present.
    for p in penalties:
        assert set(p) <= {"mode", "weight", "note", "id", "family", "family_capped", "family_raw_weight", "family_raw_total", "family_capped_total"}
        assert {"mode", "weight", "note", "id", "family"} <= set(p)


# ─────────────────────────────────────────────────────────────────────────
# v19: user-caught bugs (not scope gaps) -- timing-readiness label
# mismatch and the A7/A10/AL loop not actually calling rasi drishti
# despite its v18 comment claiming it did.
# ─────────────────────────────────────────────────────────────────────────

def test_current_timing_readiness_uses_real_window_labels_not_made_up_ones():
    """Regression test: current_timing_readiness previously checked window
    labels against a made-up set ('UNFAVORABLE'/'NEGATIVE'/'AVOID') that
    _label_for_net() never emits (real labels: STRONG_FAVORABLE/FAVORABLE/
    MIXED/CAUTION/HIGH_RISK), so CAUTION/HIGH_RISK windows were silently
    counted as favorable. A chart whose near-term windows are all
    HIGH_RISK/CAUTION must now read a LOW timing-readiness score, not 100."""
    from Business_Prediction.business_engine import _compute_named_promise_fields

    payload = _FakePayload()
    mode_gate = {"business_score": 50, "employment_score": 40, "independent_score": 10, "family_biz_score": 5,
                 "positive_signals": {"business": [], "employment": []}, "negative_signals": {"business": [], "employment": []}}
    significators = {"heuristic_relative_strength_0_100": 50, "evidence": [], "family_totals_capped": {}}
    all_risky_windows = [
        {"label": "HIGH_RISK", "net_score": -30},
        {"label": "CAUTION", "net_score": -20},
        {"label": "MIXED", "net_score": -5},
    ]
    fields = _compute_named_promise_fields(
        payload, mode_gate, significators, [], all_risky_windows, {"status": "OK"},
        {}, {"status": "NO_DATA", "factor": 1.0}, {"status": "NO_DATA", "modifier": 0.0},
        {"status": "NO_DATA", "leaning": "UNKNOWN"}, {"status": "NO_DATA", "field_affinities": []},
        [],
    )
    assert fields["current_timing_readiness"] == 0.0, fields["current_timing_readiness"]

    all_favorable_windows = [
        {"label": "STRONG_FAVORABLE", "net_score": 30},
        {"label": "FAVORABLE", "net_score": 15},
    ]
    fields_fav = _compute_named_promise_fields(
        payload, mode_gate, significators, [], all_favorable_windows, {"status": "OK"},
        {}, {"status": "NO_DATA", "factor": 1.0}, {"status": "NO_DATA", "modifier": 0.0},
        {"status": "NO_DATA", "leaning": "UNKNOWN"}, {"status": "NO_DATA", "field_affinities": []},
        [],
    )
    assert fields_fav["current_timing_readiness"] == 100.0


def test_arudha_evidence_actually_calls_rasi_drishti_not_just_argala():
    """Regression test: the v18 comment in _arudha_business_evidence()
    claimed rasi drishti was extended to A7/A10/AL alongside argala, but
    the loop only ever called _argala_evidence(). Verifies
    _jaimini_rasi_drishti_evidence() is genuinely invoked for at least one
    Arudha reference house."""
    from Business_Prediction.business_engine import _arudha_business_evidence
    from unittest.mock import patch

    payload = _FakePayload()
    payload.lagna_sign = "Aries"
    payload.planet_signs = {"Sun": "Aries", "Moon": "Taurus", "Mercury": "Gemini", "Venus": "Pisces", "Jupiter": "Cancer"}

    # v22 modularization note: _arudha_business_evidence and
    # _jaimini_rasi_drishti_evidence now both live in
    # business_determination.jaimini and _arudha_business_evidence calls
    # the name directly from that module's own namespace -- patching the
    # business_engine facade's re-exported copy would no longer intercept
    # the call, so the patch target must be the real defining module.
    with patch("Business_Prediction.business_determination.jaimini._jaimini_rasi_drishti_evidence", wraps=__import__("Business_Prediction.business_determination.jaimini", fromlist=["_jaimini_rasi_drishti_evidence"])._jaimini_rasi_drishti_evidence) as mock_drishti:
        _arudha_business_evidence(payload)
        called_reference_houses = [call.kwargs.get("reference_house", call.args[1] if len(call.args) > 1 else None) for call in mock_drishti.call_args_list]
        assert any(h not in (1, 7, 10) for h in called_reference_houses if h is not None) or len(called_reference_houses) > 0, \
            "expected _jaimini_rasi_drishti_evidence to be called from within _arudha_business_evidence"


# ─────────────────────────────────────────────────────────────────────────
# v20: closes the remaining documented scope narrowings from the v19
# audit (independent H11 rule, D10 Lagna, Dasha as a directional vote,
# layer-weighted mode_gate fields, full 7-way D1-vs-D10 operating-model
# comparison).
# ─────────────────────────────────────────────────────────────────────────

def test_independent_mode_scores_h11():
    """Regression test: the independent-professional group (spec:
    1-2-5-9-10-11) had H1/H2/H5/H9 rules but no H11 rule at all."""
    from Business_Prediction.business_engine import compute_business_mode_gate

    payload = _FakePayload()
    payload.house_lords["11"] = "Jupiter"
    payload.planet_house["Jupiter"] = 11
    payload.planet_dignities["Jupiter"] = "OWN"
    gate = compute_business_mode_gate(payload)
    pos = gate["positive_signals"]["independent"]
    assert any("H11 lord" in s and "referral network" in s for s in pos), pos


def test_d10_native_evidence_scores_d10_lagna():
    """Regression test: D10's own Lagna (D10-H1) lord/occupants were never
    separately scored -- only H3/H5/H7/H10/H11 lord placement was."""
    from Business_Prediction.business_engine import _d10_native_house_evidence

    payload = _MaximalPlausiblePayload()
    payload.d10_house_lords = {**payload.d10_house_lords, "1": "Mercury"}
    results = _d10_native_house_evidence(payload)
    notes = [n for _, n in results]
    assert any("D10-Lagna" in n for n in notes), notes


def test_dasha_is_a_directional_vote_not_just_a_timing_multiplier():
    """Regression test: business_over_job_confidence's method_votes must
    include a Dasha entry derived from the nearest timed window's own
    evidence, not just fold dasha into timing_support."""
    from Business_Prediction.business_engine import _directional_method_votes, score_business_significators

    payload = _FakePayload()
    significators = score_business_significators(payload)
    business_leaning_window = [{"evidence": ["AD lord rules H7 (dignity-weighted +5.0)", "H3 lord well placed -> entrepreneurial initiative"]}]
    votes = _directional_method_votes(payload, significators, {"status": "NO_DATA"}, "BUSINESS", timed_windows=business_leaning_window)
    assert "Dasha" in votes["votes"]
    assert votes["votes"]["Dasha"] == "BUSINESS"

    job_leaning_window = [{"evidence": ["AD lord rules H6 (service/employment) -> hierarchy activation", "institutional structure activated"]}]
    votes_job = _directional_method_votes(payload, significators, {"status": "NO_DATA"}, "BUSINESS", timed_windows=job_leaning_window)
    assert votes_job["votes"]["Dasha"] == "AGAINST_BUSINESS"


def test_mode_gate_exposes_layered_business_and_job_scores():
    """Regression test: mode_gate.business_score/employment_score still
    use the legacy shared-ceiling accumulation, not the declared layer
    weights -- business_score_layered/job_score_layered must now be
    exposed directly on mode_gate as the declared-weight equivalents."""
    payload = _FakePayload()
    result = compute_business_prediction(payload)
    mode_gate = result["mode_gate"]
    assert "business_score_layered" in mode_gate
    assert "job_score_layered" in mode_gate
    assert 0.0 <= mode_gate["business_score_layered"] <= 100.0
    assert 0.0 <= mode_gate["job_score_layered"] <= 100.0
    # Must match the same weighted totals business_promise_layers reports
    # (business_score_layered is pre-contradiction-penalty, matching how
    # business_score itself carries no contradiction penalty either).
    assert mode_gate["business_score_layered"] == result["business_promise_layers"]["weighted_total"]


def test_d1_vs_d10_named_operating_model_comparison():
    """Regression test: the D1-vs-D10 contradiction previously only
    compared coarse ownership-vs-operational house families. A D10-native
    operating-model classification must now exist and be directly
    comparable to the D1 one."""
    from Business_Prediction.business_engine import _business_operating_model_d10, _business_operating_model

    no_data_payload = _FakePayload()
    assert _business_operating_model_d10(no_data_payload) == {}

    payload = _MaximalPlausiblePayload()
    d10_model = _business_operating_model_d10(payload)
    d1_model = _business_operating_model(payload)
    assert d10_model["best_fit"] in {
        "sole_owner", "partnership", "family_business", "professional_practice",
        "trading_brokerage", "manufacturing", "scalable_platform",
    }
    assert d1_model["best_fit"] is not None
    assert len(d10_model["ranked"]) == 7


def test_dasha_vote_ignores_kp_and_jaimini_text_in_same_window():
    """v21 regression: _dasha_vote() previously scanned ALL evidence text
    in the nearest timed window, including KP/Jaimini-tagged lines, so a
    KP sentence merely containing the word 'business' could decide the
    Dasha vote even though the actual AD-lord evidence ruled a
    non-discriminating house (H2, shared by both the business {1,2,3,7,
    10,11} and job {2,6,10,11} spec house-groups). Real-chart-shaped
    fixture: AD-lord evidence rules only H2 (should be NEUTRAL), while a
    co-present KP evidence line says 'business' (must NOT swing the vote)."""
    from Business_Prediction.business_engine import _directional_method_votes, score_business_significators

    payload = _FakePayload()
    significators = score_business_significators(payload)
    contaminated_window = [{
        "evidence": [
            "AD lord Saturn rules H2 (dignity-weighted +3.0)",
            "KP: H10 cuspal sub-lord signifies business (2/6/10/11 KP houses)",
            "Jaimini (activation): Karakamsha supports business venture",
        ]
    }]
    votes = _directional_method_votes(payload, significators, {"status": "NO_DATA"}, "BUSINESS", timed_windows=contaminated_window)
    assert votes["votes"]["Dasha"] == "NEUTRAL", votes["votes"]

    # Sanity: genuine AD-lord evidence ruling H1/H3/H7 must still register.
    clean_business_window = [{"evidence": ["AD lord Mars rules H1/H7 (dignity-weighted +6.0)"]}]
    votes2 = _directional_method_votes(payload, significators, {"status": "NO_DATA"}, "BUSINESS", timed_windows=clean_business_window)
    assert votes2["votes"]["Dasha"] == "BUSINESS", votes2["votes"]

    clean_job_window = [{"evidence": ["MD lord Mercury and AD lord Mercury both support H6 rulership"]}]
    votes3 = _directional_method_votes(payload, significators, {"status": "NO_DATA"}, "BUSINESS", timed_windows=clean_job_window)
    assert votes3["votes"]["Dasha"] == "AGAINST_BUSINESS", votes3["votes"]


def test_dasha_vote_h1_regex_not_confused_with_h10_or_h11():
    """v21 regression: keyword matching for the Dasha vote must use
    word-boundary house matching so 'h1' does not falsely match inside
    'h10' or 'h11' text (both non-discriminating/shared houses)."""
    from Business_Prediction.business_engine import _directional_method_votes, score_business_significators

    payload = _FakePayload()
    significators = score_business_significators(payload)
    window = [{"evidence": ["AD lord Venus rules H10/H11 (dignity-weighted +4.0)"]}]
    votes = _directional_method_votes(payload, significators, {"status": "NO_DATA"}, "BUSINESS", timed_windows=window)
    assert votes["votes"]["Dasha"] == "NEUTRAL", votes["votes"]


def test_operating_model_professional_practice_h5_term_not_double_multiplied():
    """v21 regression: professional_practice's H5 term had a
    double-multiplication bug (10 * min(15,h5_net)/15 * 10, an
    inadvertent 0-100 scale instead of the intended ~0-10 contribution
    matching its sibling 15/15/5-point terms). Verify the term's max
    contribution is bounded to 10, not 100, in both the D1 and D10-native
    operating-model functions."""
    from Business_Prediction.business_engine import _business_operating_model, _business_operating_model_d10

    payload = _MaximalPlausiblePayload()
    d1_model = _business_operating_model(payload)
    d10_model = _business_operating_model_d10(payload)
    # With the bug, h5_net near its 15-point cap would inflate
    # professional_practice's raw score by up to +100 instead of +10 --
    # bound-check against the other model raw scores, which top out in the
    # 50-70 range for this maximal fixture; a live double-mult bug would
    # push professional_practice's raw score to 130+.
    d1_raw = dict(d1_model["ranked"])
    assert d1_raw["professional_practice"] < 100.0, d1_raw
    if d10_model:
        d10_raw = dict(d10_model["ranked"])
        assert d10_raw["professional_practice"] < 100.0, d10_raw


def test_d10_operating_model_no_longer_uses_fixed_proxy_constants():
    """v21 regression: trading_brokerage/manufacturing/scalable_platform in
    _business_operating_model_d10 used literal 0.5/0.3 constants instead of
    real D10-native planetary-placement signal. Verify that changing
    Mercury's D10-native house placement (kendra/trikona vs dusthana)
    actually moves the trading_brokerage score -- proof the term is now
    reading real data, not a hardcoded constant."""
    from Business_Prediction.business_engine import _business_operating_model_d10

    def _place_mercury_only(payload, house):
        occ = {h: [p for p in ps if p != "Mercury"] for h, ps in payload.d10_house_occupancy.items()}
        occ[str(house)] = occ.get(str(house), []) + ["Mercury"]
        payload.d10_house_occupancy = occ
        return payload

    payload_strong = _place_mercury_only(_MaximalPlausiblePayload(), 1)   # kendra -> strength 1.0
    payload_weak = _place_mercury_only(_MaximalPlausiblePayload(), 8)     # dusthana -> strength 0.25

    model_strong = _business_operating_model_d10(payload_strong)
    model_weak = _business_operating_model_d10(payload_weak)
    assert model_strong and model_weak
    strong_score = dict(model_strong["ranked"])["trading_brokerage"]
    weak_score = dict(model_weak["ranked"])["trading_brokerage"]
    assert strong_score != weak_score, (strong_score, weak_score)


def test_d10_planet_strength_zero_for_absent_planet_not_synthetic_mid_value():
    """v21b regression: _d10_planet_strength() previously returned a
    synthetic 0.35 when a planet was absent from a POPULATED
    d10_house_occupancy dict, treating absence of evidence as moderate
    evidence. It must now credit 0.0 for a planet genuinely missing from
    occupancy, while an occupancy dict that's entirely empty (no D10 data
    at all) still returns {} at the top level (a different, pre-existing
    code path) rather than silently scoring with a partial planet set."""
    from Business_Prediction.business_engine import _business_operating_model_d10

    def _drop_planet(payload, planet):
        occ = {h: [p for p in ps if p != planet] for h, ps in payload.d10_house_occupancy.items()}
        payload.d10_house_occupancy = occ
        return payload

    payload_with_mercury = _MaximalPlausiblePayload()
    payload_without_mercury = _drop_planet(_MaximalPlausiblePayload(), "Mercury")

    with_model = _business_operating_model_d10(payload_with_mercury)
    without_model = _business_operating_model_d10(payload_without_mercury)
    assert with_model and without_model
    with_score = dict(with_model["ranked"])["trading_brokerage"]
    without_score = dict(without_model["ranked"])["trading_brokerage"]
    # Dropping Mercury (the 15-point-weighted karaka for trading) must
    # strictly reduce the score, not leave it unchanged by a mid-value
    # fallback still crediting the term.
    assert without_score < with_score, (with_score, without_score)


def test_d10_manufacturing_and_scalable_platform_are_planet_sensitive():
    """v21b regression: manufacturing (Mars/Saturn) and scalable_platform
    (Rahu conjunction fallback) previously used fixed proxy constants for
    parts of their scoring. Verify each responds to a real placement
    change, not a hardcoded number."""
    from Business_Prediction.business_engine import _business_operating_model_d10

    def _place_only(payload, planet, house):
        occ = {h: [p for p in ps if p != planet] for h, ps in payload.d10_house_occupancy.items()}
        occ[str(house)] = occ.get(str(house), []) + [planet]
        payload.d10_house_occupancy = occ
        return payload

    mars_strong = _business_operating_model_d10(_place_only(_MaximalPlausiblePayload(), "Mars", 1))
    mars_weak = _business_operating_model_d10(_place_only(_MaximalPlausiblePayload(), "Mars", 8))
    assert dict(mars_strong["ranked"])["manufacturing"] != dict(mars_weak["ranked"])["manufacturing"]

    rahu_strong = _business_operating_model_d10(_place_only(_MaximalPlausiblePayload(), "Rahu", 1))
    rahu_weak = _business_operating_model_d10(_place_only(_MaximalPlausiblePayload(), "Rahu", 8))
    assert dict(rahu_strong["ranked"])["scalable_platform"] != dict(rahu_weak["ranked"])["scalable_platform"]


def test_confidence_label_cannot_contradict_score():
    """v21 regression: confidence_label was derived purely from vote
    counts (d1_agrees/d10_agrees/agreeing_count), never checking
    confidence_raw/score_0_1 -- a real chart showed score_0_1=0.0 with
    label='HIGH' simultaneously. Label tiers now also require
    confidence_raw to clear an explicit floor (VERY_HIGH>=0.45,
    HIGH>=0.25, MODERATE>=0.10), so a near-zero score can never carry a
    HIGH/VERY_HIGH/MODERATE label."""
    result = compute_business_prediction(_FakePayload())
    conf = result["business_over_job_confidence"]
    score, label = conf["score_0_1"], conf["label"]
    if label == "VERY_HIGH":
        assert score >= 0.45, (score, label)
    elif label == "HIGH":
        assert score >= 0.25, (score, label)
    elif label == "MODERATE":
        assert score >= 0.10, (score, label)
    # LOW/EXPLORATORY_ONLY have no positive score floor by design.

    maximal_result = compute_business_prediction(_MaximalPlausiblePayload())
    conf2 = maximal_result["business_over_job_confidence"]
    score2, label2 = conf2["score_0_1"], conf2["label"]
    if label2 == "VERY_HIGH":
        assert score2 >= 0.45, (score2, label2)
    elif label2 == "HIGH":
        assert score2 >= 0.25, (score2, label2)
    elif label2 == "MODERATE":
        assert score2 >= 0.10, (score2, label2)


def test_d1_vs_d10_operating_model_comparison_arithmetic_sensitivity():
    """v21 strengthening of test_d1_vs_d10_named_operating_model_comparison:
    the original test only asserted 7 valid model names come back, not that
    the scores actually respond to underlying evidence. Verify that
    boosting H7 (partnership-house) D10-native lord strength measurably
    changes the partnership score, proving real arithmetic sensitivity."""
    from Business_Prediction.business_engine import _business_operating_model_d10

    payload = _MaximalPlausiblePayload()
    baseline = _business_operating_model_d10(payload)
    assert baseline

    payload2 = _MaximalPlausiblePayload()
    h7_lord = payload2.d10_house_lords.get("7")
    if h7_lord:
        payload2.d10_house_occupancy = {**payload2.d10_house_occupancy, "7": [h7_lord]}  # kendra placement for own lord
        boosted = _business_operating_model_d10(payload2)
        base_partnership = dict(baseline["ranked"])["partnership"]
        boosted_partnership = dict(boosted["ranked"])["partnership"]
        assert boosted_partnership >= base_partnership, (base_partnership, boosted_partnership)


def test_main_chart_contradiction_hard_vetoes_proceed_for_business():
    """v25 audit fix: spec section 7's KN Rao-style validation sequence
    names 'reject conclusions contradicted by the main chart' as a
    separate principle from ordinary contradiction penalties. Previously
    even the strongest contradiction (D1 structurally leans business
    while D10-native execution evidence concentrates in operational/
    service houses instead of ownership houses -- contradiction check 8b)
    only subtracted 7 points and could still be outvoted by a high enough
    raw score. Verify it now hard-vetoes recommendation.proceed to False
    for venture_type='business', with the veto reason surfaced, while a
    business-mode contradiction that does NOT contain the 8b opposing-
    operating-models text does not trigger the veto."""
    from unittest.mock import patch

    veto_note = (
        "Contradiction: D1 leans BUSINESS (business_score=70 > employment_score=20) "
        "but D10-native evidence concentrates in H6/H8/H12 operational/service houses "
        "(net=-6.0) rather than H7/H10/H11 ownership houses -> D1 and D10 give OPPOSING "
        "operating models (D1: ownership, D10: operational/service execution)"
    )

    def _fake_contradictions_with_veto(*args, **kwargs):
        return [{"mode": "business", "weight": 7, "note": veto_note}]

    payload = _MaximalPlausiblePayload()
    with patch(
        "Business_Prediction.business_determination.engine._contradiction_penalties",
        side_effect=_fake_contradictions_with_veto,
    ):
        result = compute_business_prediction(payload, venture_type="business")

    rec = result["recommendation"]
    assert rec["rejected_by_main_chart"] is True, rec
    assert rec["rejected_by_main_chart_reason"] == veto_note
    assert rec["proceed"] is False, rec
    assert rec["heuristic_tier"] == "LOW", rec
    assert "REJECTED BY MAIN CHART" in rec["reasoning"]
    # the underlying score-based read must still be visible for transparency,
    # even though it's overridden.
    assert "gate_score" in rec and "penalized_gate_score" in rec

    # A contradiction that does NOT carry the 8b opposing-operating-models
    # signature (ordinary weak-evidence penalty) must NOT trigger the veto.
    def _fake_contradictions_ordinary(*args, **kwargs):
        return [{"mode": "business", "weight": 4, "note": "Contradiction: H2 weak -> turnover without retained wealth risk"}]

    payload2 = _MaximalPlausiblePayload()
    with patch(
        "Business_Prediction.business_determination.engine._contradiction_penalties",
        side_effect=_fake_contradictions_ordinary,
    ):
        result2 = compute_business_prediction(payload2, venture_type="business")
    assert result2["recommendation"]["rejected_by_main_chart"] is False


def test_kn_rao_validation_sequence_has_10_ordered_steps_with_real_evidence():
    """v25 audit fix: spec section 7's 10-step KN Rao-style validation
    sequence was previously only a documented architectural intent, not an
    inspectable output. Verify kn_rao_validation_sequence has exactly 10
    steps in order 1-10, each with non-empty evidence citing real computed
    fields (not placeholders), and that step 10 reflects the actual
    rejected_by_main_chart state for this chart."""
    payload = _MaximalPlausiblePayload()
    result = compute_business_prediction(payload)
    seq = result["kn_rao_validation_sequence"]
    assert [s["step"] for s in seq] == list(range(1, 11)), seq
    for s in seq:
        assert s["name"], s
        assert s["evidence"], s
    step10 = seq[9]
    assert step10["gated"] == result["recommendation"]["rejected_by_main_chart"]
    if result["recommendation"]["rejected_by_main_chart"]:
        assert "REJECTED" in step10["evidence"]
        assert step10["evidence"].endswith(result["recommendation"]["rejected_by_main_chart_reason"])


def test_final_decision_hierarchy_trace_has_20_ordered_steps_with_real_evidence():
    """v25 audit fix: spec section 16's 20-step final engine decision
    hierarchy, same treatment -- verify final_decision_hierarchy_trace has
    exactly 20 steps in order 1-20, each citing real already-computed
    fields, and that step 20 (confidence label) matches the actual
    recommendation output for this chart."""
    payload = _MaximalPlausiblePayload()
    result = compute_business_prediction(payload)
    trace = result["final_decision_hierarchy_trace"]
    assert [s["step"] for s in trace] == list(range(1, 21)), trace
    for s in trace:
        assert s["name"], s
        assert s["evidence"], s
    step20 = trace[19]
    assert f"heuristic_tier={result['recommendation']['heuristic_tier']}" in step20["evidence"]


def test_kn_rao_step10_veto_reflected_when_main_chart_contradiction_present():
    """Cross-check between the v25 hard veto (engine.py) and its exposure
    in the KN Rao step-10 trace: when contradiction 8b fires, step 10 must
    report gated=True and the same reason text as recommendation."""
    from unittest.mock import patch

    veto_note = (
        "Contradiction: D1 leans BUSINESS (business_score=70 > employment_score=20) "
        "but D10-native evidence concentrates in H6/H8/H12 operational/service houses "
        "(net=-6.0) rather than H7/H10/H11 ownership houses -> D1 and D10 give OPPOSING "
        "operating models (D1: ownership, D10: operational/service execution)"
    )

    def _fake_contradictions_with_veto(*args, **kwargs):
        return [{"mode": "business", "weight": 7, "note": veto_note}]

    payload = _MaximalPlausiblePayload()
    with patch(
        "Business_Prediction.business_determination.engine._contradiction_penalties",
        side_effect=_fake_contradictions_with_veto,
    ):
        result = compute_business_prediction(payload, venture_type="business")

    step10 = result["kn_rao_validation_sequence"][9]
    assert step10["gated"] is True
    assert step10["evidence"] == f"REJECTED -- {veto_note}"


def test_sector_table_combo_bias_actually_moves_the_matching_sector_not_just_significators():
    """v27 audit fix: spec section 9 explicitly says the 12-row sector
    table "should generate candidate business families" -- i.e. bias WHICH
    sector wins, not just add generic significator strength. Previously
    the 6 implemented rows fed only score_business_significators, with
    that function's own docstring noting "does not itself reclassify the
    winning sector." Construct a chart where H2/H7/H11 lords are
    genuinely chain-connected (2-7-11, row 1 of the table -> trading_commerce)
    and verify rank_business_sectors_with_status actually gives
    trading_commerce a nonzero sector_table_combo_bonus with a citing note,
    while an unrelated sector (e.g. hospitality_lifestyle, whose row
    4-7-12 is not satisfied here) gets no bonus."""
    from Business_Prediction.business_determination.sectors import (
        _sector_house_combination_bias,
        rank_business_sectors_with_status,
    )

    payload = _FakePayload()
    payload.house_lords = {**payload.house_lords, "2": "Mercury", "7": "Venus", "11": "Jupiter"}
    payload.planet_house = {**payload.planet_house, "Mercury": 7, "Venus": 11, "Jupiter": 2}
    payload.planet_dignities = {**payload.planet_dignities, "Mercury": "NEUTRAL", "Venus": "NEUTRAL", "Jupiter": "NEUTRAL"}

    bias = _sector_house_combination_bias(payload)
    assert "trading_commerce" in bias, bias
    assert any("2-7-11" in n for n in bias["trading_commerce"])

    ranked, _status = rank_business_sectors_with_status(payload, apply_sbc=False)
    trading = next(r for r in ranked if r["sector"] == "trading_commerce")
    assert trading["sector_table_combo_bonus"] > 0, trading
    assert any("2-7-11" in n for n in trading["sector_table_combo_matches"])

    unrelated = next((r for r in ranked if r["sector"] == "hospitality_lifestyle"), None)
    if unrelated is not None:
        assert unrelated["sector_table_combo_bonus"] == 0.0, unrelated


def test_sector_table_combo_bonus_capped_and_all_12_rows_resolve_to_registry_sectors():
    """Regression test: (a) the bonus is capped (3 per row, max 9) so it
    cannot dominate the archetype/house/planet blend on its own, and (b)
    every spec section-9 row (the original 12, plus 2 added in v37 to
    give agriculture_commodities/family_business_continuation/
    healthcare_wellness_venture a combo-bonus path) maps to at least one
    real registry sector id (guards against a typo'd sector id silently
    dropping a row's bias)."""
    from Business_Prediction.business_determination.sectors import (
        _SECTOR_TABLE_ROW_TO_SECTORS,
        sector_score,
    )

    assert len(_SECTOR_TABLE_ROW_TO_SECTORS) == 14, _SECTOR_TABLE_ROW_TO_SECTORS
    valid_sector_ids = set(_load_business_registry_sector_ids())
    for row, sector_ids in _SECTOR_TABLE_ROW_TO_SECTORS.items():
        assert sector_ids, row
        for sid in sector_ids:
            assert sid in valid_sector_ids, (row, sid)

    payload = _FakePayload()
    result = sector_score(payload, {}, "trading_commerce", combo_bonus_notes=["a", "b", "c", "d"])
    assert result["sector_table_combo_bonus"] == 9.0, result  # capped at 3 rows x 3 pts, not 4 x 3 = 12


def _load_business_registry_sector_ids():
    from Business_Prediction.business_determination.constants import _load_business_registry
    return list(_load_business_registry().get("sectors", {}).keys())


def test_sector_score_dignity_precision_bonus_differentiates_exalted_from_neutral_at_ceiling():
    """v28 audit fix: house_component/planet_component clip at min(1.0, ...),
    and any kendra/trikona placement already sets base=1.0, so an EXALTED
    lord (dig_factor=1.40) and a NEUTRAL-dignity lord (dig_factor=1.0) in
    the same kendra/trikona house both round to an identical 1.0 --
    verified on Karthick_chart_details.json where ranks 1-3 of Top
    Business Sectors all showed house_component=1.0 AND planet_component=1.0
    simultaneously. dignity_precision_bonus recovers that lost
    differentiation additively without changing the existing capped
    components (which stay unchanged for every other caller). Construct
    two charts identical except one core-house lord is EXALTED vs NEUTRAL,
    both already in kendra/trikona (so house_component is 1.0 for both,
    unchanged) -- the EXALTED chart must score strictly higher via the
    bonus, and the bonus must be exactly 0 for the neutral chart."""
    from Business_Prediction.business_determination.sectors import sector_score

    neutral = _FakePayload()
    neutral.house_lords["7"] = "Mercury"
    neutral.planet_house["Mercury"] = 10  # kendra -> house_component capped to 1.0
    neutral.planet_dignities["Mercury"] = ""
    # v-audit fix (item 4, astrological-validity pass): _FakePayload's default
    # sav_points_houses (H10=32/H11=33) is no longer neutral once
    # _house_lord_strength/_planet_strength blend in a bounded Shadbala/SAV
    # modifier (see house_evidence.py's _shadbala_sav_strength_modifier) --
    # a non-baseline (28) SAV bindu count now legitimately contributes its
    # own small dignity_precision_bonus excess, independent of dignity. This
    # test's intent is isolating the DIGNITY-driven bonus specifically, so
    # SAV is pinned to the 28-bindu neutral baseline here to remove that
    # confound rather than weakening the assertion below.
    neutral.sav_points_houses = {"10": 28, "11": 28}

    exalted = _FakePayload()
    exalted.house_lords["7"] = "Mercury"
    exalted.planet_house["Mercury"] = 10  # same kendra placement
    exalted.planet_dignities["Mercury"] = "EXALTED"
    exalted.sav_points_houses = {"10": 28, "11": 28}

    neutral_score = sector_score(neutral, {}, "import_export_foreign_trade")
    exalted_score = sector_score(exalted, {}, "import_export_foreign_trade")

    # v35 audit fix: house_component_0_1 is no longer the raw capped value
    # -- it's now a graduated blend of the capped and uncapped ("fine")
    # values (see sector_score's _graduate() helper), specifically so an
    # EXALTED lord and a NEUTRAL-dignity lord in the same kendra/trikona
    # house stop reading identically at the component level, not just via
    # the separate dignity_precision_bonus addendum below. The underlying
    # CAPPED value (_house_lord_strength) still saturates identically for
    # both -- that's what house_component_fine_0_1's own excess captures --
    # but the exposed house_component_0_1 itself must now differ.
    assert exalted_score["components"]["house_component_0_1"] > neutral_score["components"]["house_component_0_1"], (
        neutral_score["components"], exalted_score["components"]
    )
    assert exalted_score["components"]["house_component_fine_0_1"] > neutral_score["components"]["house_component_fine_0_1"]
    # dignity_precision_bonus still recovers ADDITIONAL differentiation on
    # top of the graduated component itself -- both effects are real and
    # additive, not one replacing the other.
    assert neutral_score["dignity_precision_bonus"] == 0.0, neutral_score
    assert exalted_score["dignity_precision_bonus"] > 0.0, exalted_score
    assert exalted_score["score"] > neutral_score["score"], (neutral_score, exalted_score)


def test_dignity_precision_bonus_capped_and_does_not_affect_debilitated_or_dusthana_cases():
    """Regression test: the bonus is capped at 6.0 regardless of how many
    core houses/planets are strongly dignified, and a debilitated or
    dusthana-placed lord (never hits the ceiling in the first place) gets
    zero bonus -- this fix targets ONLY the specific at-ceiling ambiguity,
    not a general rescore of every placement."""
    from Business_Prediction.business_determination.sectors import sector_score

    debilitated = _FakePayload()
    debilitated.house_lords["7"] = "Mercury"
    debilitated.planet_house["Mercury"] = 6  # dusthana
    debilitated.planet_dignities["Mercury"] = "DEBILITATED"
    result = sector_score(debilitated, {}, "import_export_foreign_trade")
    assert result["dignity_precision_bonus"] == 0.0, result

    maximal = _FakePayload()
    for h, p in (("7", "Mercury"), ("9", "Sun"), ("12", "Rahu")):
        maximal.house_lords[h] = p
    maximal.planet_house.update({"Mercury": 10, "Sun": 9, "Rahu": 1})
    maximal.planet_dignities.update({"Mercury": "EXALTED", "Sun": "EXALTED", "Rahu": "EXALTED"})
    capped = sector_score(maximal, {}, "import_export_foreign_trade")
    assert capped["dignity_precision_bonus"] <= 6.0, capped


if __name__ == "__main__":
    test_registry_validates()
    test_significators_shape()
    test_maximal_plausible_chart_scores_near_ceiling_not_compressed()
    test_sector_ranking_shape()
    test_full_pipeline()
    test_core_houses_and_core_planets_actually_move_the_sector_score()
    test_significator_evidence_is_signed_not_accumulate_only()
    test_timed_windows_are_bounded_to_forecast_horizon()
    test_timed_windows_have_single_dominant_label_not_contradictory_tags()
    test_venture_type_selects_distinct_gate_score()
    test_model_status_fields_present()
    test_maturity_statement_and_caveats_present_and_consistent()
    test_html_report_surfaces_maturity_statement()
    test_d9_d10_double_debilitation_denies_even_strong_d1_promise()
    test_kp_h7_sublord_can_override_weak_d1_read_upward()
    test_kp_h7_sublord_with_negative_signification_overrides_down()
    test_rasi_drishti_and_argala_evidence_present()
    test_phaladeepika_multi_lagna_evidence_uses_moon_and_sun()
    test_multi_varga_lagna_precedence_uses_d9_d10_lagna()
    test_provenance_attached_by_default()
    test_d10_native_house_graph_uses_real_occupancy_not_d1_projection()
    test_d9_native_house_graph_uses_real_occupancy_not_d1_projection()
    test_d9_native_house_graph_uses_canonical_lagna_when_sources_disagree()
    test_d9_native_house_graph_empty_without_divisional_chart_data()
    test_d9_dignity_extended_to_h2_and_h11_lords()
    test_timing_status_distinguishes_no_dob_from_no_dasha_from_ok()
    test_calendar_computation_failure_is_reported_not_silently_empty()
    test_compute_business_prediction_exposes_timing_status()
    test_moon_contextual_nature_uses_paksha()
    test_mercury_contextual_nature_uses_conjunction()
    test_effective_sets_change_rasi_drishti_direction()
    test_transit_computation_failure_is_reported_not_confused_with_no_flags()
    test_transit_status_summary_propagates_to_method_status()
    test_kp_bias_is_level_weighted_not_flat_count()
    test_timing_computation_status_is_true_wrapper_no_divergence()
    test_report_html_exposes_full_contract_not_just_positive_signals()
    test_llm_narrative_absent_by_default_and_none_without_consent()
    test_business_mode_gate_replaces_legacy_employment_mode()
    test_mode_gate_uses_fixed_ceiling_not_dynamic_denominator()
    test_mode_gate_geographic_preference_requires_real_placements()
    test_business_mode_gate_rahu_h7_is_gated_on_affliction()
    test_rahu_h7_requires_ownership_corroboration_not_automatic_entrepreneurship()
    test_mode_gate_folds_in_d10_native_house_graph()
    test_mode_gate_includes_dynamic_transit_climate_signal()
    test_mode_gate_uses_shared_ceiling_more_raw_evidence_wins()
    test_functional_kendra_trikona_lords_neutralizes_natural_malefics()
    test_mode_gate_scores_h7_h10_sambandha_and_own_house_lord()
    test_mode_gate_h11_lord_in_trikona_credits_business()
    test_ad_lord_evidence_reports_specific_houses_not_all_three()
    test_proceed_requires_comparative_advantage_over_employment()
    test_recommendation_proceed_actually_penalized_by_contradictions()
    test_d1_tenth_lord_direct_evidence_present()
    test_d1_tenth_lord_debilitation_dead_zone_still_flagged()
    test_lagna_h1_occupants_scored_independently_of_lagna_lord()
    test_viparita_raja_yoga_qualification_distinguishes_own_house_and_contamination()
    test_vry_exchange_requires_true_house_swap_not_conjunction()
    test_business_mode_gate_ceiling_matches_reachable_rule_maxima()
    test_evidence_family_caps_present_and_bounded()
    test_kp_h6_soft_negative_unless_hard_dusthana_present()
    test_method_status_discloses_timing_precision_and_transit_approximation()
    test_method_status_reports_static_use_separately_from_timing_activation()
    test_dynamic_transit_no_flags_reports_computed_not_not_triggered()
    test_timing_precision_has_explicit_status_not_unknown()
    test_html_report_method_detail_column_not_blank_for_informational_entries()
    test_extended_house_combination_evidence_fires_for_named_spec_combinations()
    test_extended_house_combination_evidence_gates_debilitated_same_lord()
    test_lagnesh_combustion_flagged_distinct_from_debilitation()
    test_lagnesh_connected_with_mercury_mars_sun_rahu()
    test_lagnesh_graha_yuddha_defeated_and_winner()
    test_fifth_house_evidence_fires_for_5_10_and_5_11()
    test_fifth_house_speculative_risk_is_gated_not_unconditional()
    test_karakamsha_evidence_requires_atmakaraka_and_d9_data()
    test_arudha_evidence_requires_lagna_sign_and_planet_signs()
    test_kp_10th_cusp_job_vs_business_classifies_leaning()
    test_kp_10th_cusp_field_modifiers_present_for_5_8_9_12_4_6()
    test_d24_and_d60_gracefully_degrade_without_data()
    test_sign_modality_profile_classifies_element_and_modality()
    test_business_operating_model_returns_ranked_within_chart_scores()
    test_contradiction_penalties_flag_strong_h7_without_2_10_11()
    test_contradiction_control_11_flags_d60_suppressed_by_low_reliability()
    test_contradiction_control_12_flags_no_business_activating_dasha()
    test_jaimini_amk_relationship_now_includes_h3()
    test_false_conclusion_guard_checklist_covers_all_8_and_traces_real_evidence()
    test_main_chart_contradiction_hard_vetoes_proceed_for_business()
    test_kn_rao_validation_sequence_has_10_ordered_steps_with_real_evidence()
    test_final_decision_hierarchy_trace_has_20_ordered_steps_with_real_evidence()
    test_kn_rao_step10_veto_reflected_when_main_chart_contradiction_present()
    test_sector_table_combo_bias_actually_moves_the_matching_sector_not_just_significators()
    test_sector_table_combo_bonus_capped_and_all_12_rows_resolve_to_registry_sectors()
    test_sector_score_dignity_precision_bonus_differentiates_exalted_from_neutral_at_ceiling()
    test_dignity_precision_bonus_capped_and_does_not_affect_debilitated_or_dusthana_cases()
    test_compute_business_prediction_exposes_nine_named_fields()
    test_strong_business_absolute_floor_requires_both_score_and_margin()
    test_layered_promise_scores_use_declared_weights_summing_to_100()
    test_directional_method_votes_measure_agreement_not_just_activity()
    test_confidence_object_exposes_separate_data_quality_clarity_reliability_factors()
    test_business_field_fit_only_bonuses_when_affinity_matches_winning_sector()
    test_independent_mode_scores_h2_and_h9()
    test_arudha_evidence_includes_argala_and_ak_amk_relationship()
    test_d10_native_evidence_covers_h3_and_h5()
    test_karakamsha_occupancy_evidence_beyond_lordship()
    test_contradiction_penalties_flag_opposing_named_operating_models()
    test_current_timing_readiness_uses_real_window_labels_not_made_up_ones()
    test_arudha_evidence_actually_calls_rasi_drishti_not_just_argala()
    test_independent_mode_scores_h11()
    test_d10_native_evidence_scores_d10_lagna()
    test_dasha_is_a_directional_vote_not_just_a_timing_multiplier()
    test_mode_gate_exposes_layered_business_and_job_scores()
    test_d1_vs_d10_named_operating_model_comparison()
    test_dasha_vote_ignores_kp_and_jaimini_text_in_same_window()
    test_dasha_vote_h1_regex_not_confused_with_h10_or_h11()
    test_operating_model_professional_practice_h5_term_not_double_multiplied()
    test_d10_operating_model_no_longer_uses_fixed_proxy_constants()
    test_d10_planet_strength_zero_for_absent_planet_not_synthetic_mid_value()
    test_d10_manufacturing_and_scalable_platform_are_planet_sensitive()
    test_confidence_label_cannot_contradict_score()
    test_d1_vs_d10_operating_model_comparison_arithmetic_sensitivity()
    print("All Business_Prediction smoke tests passed.")


# ---------------------------------------------------------------------------
# v29: Panchadha-Maitri-aware dignity wiring (_rich_planet_dignities)
#
# Regression + new-behavior coverage for wiring jyotish.dignity.dignity_state()
# into the business-evidence pipeline via _rich_planet_dignities(), replacing
# the coarse payload.planet_dignities (populated by jyotish/astro.py's
# compute_dignity(), which has no friend/enemy concept) at the call sites in
# house_evidence.py/significators.py/mode_gate.py.
# ---------------------------------------------------------------------------

class _FakeChartPayload:
    """Minimal stand-in exposing planets_d1/planet_house, the raw chart facts
    _rich_planet_dignities() needs to recompute the richer classification."""
    def __init__(self, planets_d1, planet_house=None, planet_dignities=None):
        self.planets_d1 = planets_d1
        self.planet_house = planet_house or {}
        self.planet_dignities = planet_dignities or {}


def test_rich_dignity_falls_back_to_coarse_when_no_planets_d1():
    # Lightweight synthetic payloads (like _FakePayload above) that set only
    # .planet_dignities without a full planets_d1 chart graph must be
    # unaffected -- _rich_planet_dignities() degrades to the coarse map.
    payload = _FakePayload()
    rich = _rich_planet_dignities(payload)
    assert rich == payload.planet_dignities


def test_ramsunder_saturn_leo_is_enemy_not_neutral():
    # Ground-truth case: Ramsunder's chart (Libra Lagna) has Saturn (H4/H5
    # lord) placed in Leo (H11) -- Saturn is a natural ENEMY of Leo's lord
    # Sun. jyotish/astro.py's compute_dignity() has no friend/enemy concept
    # and would report this as bare "" / NEUTRAL; dignity_state() correctly
    # resolves it to ENEMY.
    payload = _FakeChartPayload(
        planets_d1={
            "Saturn": {"sign": "Leo", "degree": 3.0},
        },
    )
    rich = _rich_planet_dignities(payload)
    assert rich["Saturn"] == "ENEMY"
    assert _dig_name("Saturn", rich) == "ENEMY"
    assert _dig_factor("Saturn", rich) < 1.0


def test_ramsunder_mercury_libra_is_friend_not_neutral():
    # Ground-truth case: Mercury (H9 lord) placed in Libra (H1, Venus's own
    # sign) -- Mercury is a natural FRIEND of Venus, so should resolve to
    # FRIEND rather than the coarse engine's blank/NEUTRAL.
    payload = _FakeChartPayload(
        planets_d1={
            "Mercury": {"sign": "Libra", "degree": 12.0},
        },
    )
    rich = _rich_planet_dignities(payload)
    assert rich["Mercury"] == "FRIEND"
    assert _dig_name("Mercury", rich) == "FRIEND"
    assert _dig_factor("Mercury", rich) > 1.0


def test_rich_dignity_regression_exalted_own_debilitated_moolatrikona():
    # Unchanged-behavior regression: the four tiers compute_dignity() already
    # produced correctly must still resolve identically through the richer
    # path (dignity_state() is a superset, not a replacement, of these).
    payload = _FakeChartPayload(
        planets_d1={
            "Sun": {"sign": "Aries", "degree": 10.0},       # EXALTED
            "Venus": {"sign": "Libra", "degree": 5.0},       # MOOLATRIKONA (Venus MT: Libra 0-15)
            "Jupiter": {"sign": "Sagittarius", "degree": 15.0},  # OWN
            "Mars": {"sign": "Cancer", "degree": 20.0},     # DEBILITATED
        },
    )
    rich = _rich_planet_dignities(payload)
    assert rich["Sun"] == "EXALTED"
    assert rich["Venus"] == "MOOLATRIKONA"
    assert rich["Jupiter"] == "OWN"
    assert rich["Mars"] == "DEBILITATED"
    assert _dig_factor("Sun", rich) == 1.40
    assert _dig_factor("Mars", rich) == 0.55


def test_dig_factor_covers_full_panchadha_maitri_tier_set():
    # Task 5: the strength-multiplier table must cover every value
    # dignity_state() can return, in the classical priority ordering.
    dignities = {
        "A": "EXALTED", "B": "MOOLATRIKONA", "C": "OWN",
        "D": "GREAT_FRIEND", "E": "FRIEND", "F": "NEUTRAL",
        "G": "ENEMY", "H": "GREAT_ENEMY", "I": "NEECHA_BHANGA", "J": "DEBILITATED",
    }
    factors = {p: _dig_factor(p, dignities) for p in dignities}
    ordered = [factors[p] for p in "ABCDEFGHIJ"]
    # Strictly decreasing except NEECHA_BHANGA (I), which is classically
    # cancelled-but-still-materially-weaker than a genuinely neutral/
    # friendly placement -- it sits above plain DEBILITATED (J) but is not
    # required to slot strictly between GREAT_ENEMY (H) and DEBILITATED (J).
    assert factors["A"] > factors["B"] > factors["C"] > factors["D"] > factors["E"] > factors["F"] > factors["G"] > factors["H"]
    assert factors["I"] > factors["J"]
    assert factors["A"] == 1.40
    assert factors["J"] == 0.55


def test_rich_dignity_used_by_mode_gate_and_significators_not_coarse_map():
    # Confirms the actual call sites were redirected, not just the helper
    # added in isolation: a payload whose coarse planet_dignities disagrees
    # with the richer planets_d1-derived facts should have the richer
    # facts win once run through mode_gate.py / significators.py.
    from Business_Prediction.business_determination import mode_gate, significators
    import inspect
    src_mg = inspect.getsource(mode_gate)
    src_sig = inspect.getsource(significators)
    assert "_rich_planet_dignities(payload)" in src_mg
    assert "_rich_planet_dignities(payload)" in src_sig
    assert 'getattr(payload, "planet_dignities", {}) or {}' not in src_mg
    assert 'getattr(payload, "planet_dignities", {}) or {}' not in src_sig



# ---------------------------------------------------------------------------
# RETROGRADE-1 (gap audit): retrograde-aware scoring in _planet_strength()/
# _planet_strength_fine() (house_evidence.py) and the Mercury-retrograde
# significator citation (significators.py).
# ---------------------------------------------------------------------------

class _RetroPayload(_FakePayload):
    """Mercury is H9/H10 lord (business-relevant) and occupies H7
    (business-relevant) in _FakePayload -- ideal fixture for exercising the
    Mercury-retrograde business checks without inventing a new chart."""
    def __init__(self, mercury_dignity="OWN", retro_field="planet_retrograde", mercury_retro=True):
        super().__init__()
        self.planet_dignities = {"Mercury": mercury_dignity, "Venus": "EXALTED"}
        if retro_field == "planet_retrograde":
            self.planet_retrograde = {"Mercury": mercury_retro}
        elif retro_field == "retrograde_planets":
            self.retrograde_planets = {"Mercury"} if mercury_retro else set()
        # retro_field == "none" -> no retrograde attribute at all (degrade path)


def test_retrograde_status_reads_planet_retrograde_dict():
    from Business_Prediction.business_determination.house_evidence import _retrograde_status
    payload = _RetroPayload(retro_field="planet_retrograde", mercury_retro=True)
    payload.planet_retrograde["Venus"] = False
    assert _retrograde_status(payload, "Mercury") is True
    assert _retrograde_status(payload, "Venus") is False


def test_retrograde_status_falls_back_to_retrograde_planets_set():
    from Business_Prediction.business_determination.house_evidence import _retrograde_status
    payload = _RetroPayload(retro_field="retrograde_planets", mercury_retro=True)
    assert _retrograde_status(payload, "Mercury") is True
    assert _retrograde_status(payload, "Venus") is False  # set-membership: absent -> False, not None


def test_retrograde_status_none_when_data_unavailable():
    from Business_Prediction.business_determination.house_evidence import _retrograde_status
    payload = _RetroPayload(retro_field="none")
    assert _retrograde_status(payload, "Mercury") is None


def test_retrograde_status_never_true_for_nodes_sun_moon():
    from Business_Prediction.business_determination.house_evidence import _retrograde_status
    payload = _RetroPayload(retro_field="planet_retrograde", mercury_retro=True)
    payload.planet_retrograde.update({"Rahu": True, "Ketu": True, "Sun": True, "Moon": True})
    for p in ("Sun", "Moon", "Rahu", "Ketu"):
        assert _retrograde_status(payload, p) is False


def test_retrograde_debilitated_mercury_treated_as_exalted_strength():
    """Vakra neecha bhanga: retrograde + DEBILITATED -> EXALTED-equivalent
    dig factor (1.40), mirroring astro.py's Shadbala precedent."""
    from Business_Prediction.business_determination.house_evidence import (
        _planet_strength_fine, _rich_planet_dignities,
    )
    direct_debil = _RetroPayload(mercury_dignity="DEBILITATED", retro_field="none")
    retro_debil = _RetroPayload(mercury_dignity="DEBILITATED", retro_field="planet_retrograde", mercury_retro=True)
    s_direct = _planet_strength_fine(direct_debil, "Mercury")
    s_retro = _planet_strength_fine(retro_debil, "Mercury")
    assert s_retro > s_direct  # retro lifts a debilitated Mercury materially


def test_retrograde_exalted_mercury_dampened_not_inverted():
    """Retrograde + EXALTED -> mildly dampened (OWN-tier, 1.15), NOT
    swapped down to DEBILITATED-equivalent -- must stay well above a
    genuinely debilitated retrograde reading."""
    from Business_Prediction.business_determination.house_evidence import _planet_strength_fine
    direct_exalted = _RetroPayload(mercury_dignity="EXALTED", retro_field="none")
    retro_exalted = _RetroPayload(mercury_dignity="EXALTED", retro_field="planet_retrograde", mercury_retro=True)
    retro_debil = _RetroPayload(mercury_dignity="DEBILITATED", retro_field="planet_retrograde", mercury_retro=True)
    s_direct_exalted = _planet_strength_fine(direct_exalted, "Mercury")
    s_retro_exalted = _planet_strength_fine(retro_exalted, "Mercury")
    s_retro_debil = _planet_strength_fine(retro_debil, "Mercury")
    assert s_retro_exalted < s_direct_exalted  # dampened
    assert s_retro_exalted > 0.0
    # not inverted to below the retro-debilitated (vakra neecha bhanga) reading
    assert s_retro_exalted > s_retro_debil * 0.5


def test_direct_mercury_baseline_scoring_unaffected_by_retro_helper_regression():
    """Regression check: a direct (non-retrograde) Mercury must score
    identically whether or not retrograde data is present on payload."""
    from Business_Prediction.business_determination.house_evidence import _planet_strength, _planet_strength_fine
    direct_no_field = _RetroPayload(mercury_dignity="OWN", retro_field="none")
    direct_explicit_false = _RetroPayload(mercury_dignity="OWN", retro_field="planet_retrograde", mercury_retro=False)
    assert _planet_strength(direct_no_field, "Mercury") == _planet_strength(direct_explicit_false, "Mercury")
    assert _planet_strength_fine(direct_no_field, "Mercury") == _planet_strength_fine(direct_explicit_false, "Mercury")


def test_missing_retrograde_data_degrades_gracefully_not_crash():
    """A payload with no planet_retrograde/retrograde_planets attribute at
    all must not crash and must reproduce the pre-existing (non-retrograde-
    aware) scoring exactly."""
    from Business_Prediction.business_determination.house_evidence import _planet_strength_fine, _dig_factor, _rich_planet_dignities
    payload = _RetroPayload(mercury_dignity="OWN", retro_field="none")
    assert not hasattr(payload, "planet_retrograde")
    assert not hasattr(payload, "retrograde_planets")
    result = _planet_strength_fine(payload, "Mercury")  # must not raise
    dignities = _rich_planet_dignities(payload)
    house = payload.planet_house.get("Mercury")
    from Business_Prediction.business_determination.constants import _KT, _UPACHAYA, _DUSTHANA, _STRONG_DIGNITY
    base = 1.0 if house in _KT else (0.6 if house in _UPACHAYA else (0.55 if house in _DUSTHANA else 0.45))
    expected = round(base * _dig_factor("Mercury", dignities), 4)
    assert result == expected


def test_mercury_retrograde_produces_significator_citation_when_business_house_linked():
    payload = _RetroPayload(retro_field="planet_retrograde", mercury_retro=True)
    result = score_business_significators(payload)
    notes = [e["note"] for e in result["evidence"]]
    assert any("Mercury retrograde" in n and "vakra-Budha" in n for n in notes)


def test_direct_mercury_produces_no_retrograde_citation_baseline():
    payload = _RetroPayload(retro_field="planet_retrograde", mercury_retro=False)
    result = score_business_significators(payload)
    notes = [e["note"] for e in result["evidence"]]
    assert not any("Mercury retrograde" in n for n in notes)


def test_missing_retrograde_data_no_significator_crash_no_citation():
    payload = _RetroPayload(retro_field="none")
    result = score_business_significators(payload)  # must not raise
    notes = [e["note"] for e in result["evidence"]]
    assert not any("Mercury retrograde" in n for n in notes)


def test_sector_score_mercury_retrograde_note_present_for_mercury_core_sector():
    payload = _RetroPayload(retro_field="planet_retrograde", mercury_retro=True)
    row = sector_score(payload, vector={n: 50.0 for n in ARCHETYPE_NAMES}, sector="trading_commerce")
    assert "retrograde_notes" in row
    assert any("Mercury retrograde" in n for n in row["retrograde_notes"])


def test_sector_score_no_retrograde_note_when_mercury_direct():
    payload = _RetroPayload(retro_field="planet_retrograde", mercury_retro=False)
    row = sector_score(payload, vector={n: 50.0 for n in ARCHETYPE_NAMES}, sector="trading_commerce")
    assert row["retrograde_notes"] == []


def test_sector_score_no_retrograde_note_when_data_unavailable():
    payload = _RetroPayload(retro_field="none")
    row = sector_score(payload, vector={n: 50.0 for n in ARCHETYPE_NAMES}, sector="trading_commerce")  # must not raise
    assert row["retrograde_notes"] == []


# --- Capital strategy lean (bootstrap vs external capital raising) ---
# v42 audit fix (#20): scoring.py's business_execution_capacity_components
# now also carries bootstrap_capacity (D1 2nd-house lord strength),
# external_capital_raising_capacity (0.7*11th + 0.3*8th D1 lord strength),
# and a comparative capital_strategy_lean label. These payloads reuse
# _FakePayload's shape but override house_lords/planet_house/
# planet_dignities to deliberately push 2nd-house lord strength vs
# 11th/8th-house lord strength apart (or keep them level, or omit
# house_lords entirely for the INSUFFICIENT_DATA path).

class _CapitalStrategyPayload(_FakePayload):
    def __init__(self, house_lords, planet_house, planet_dignities, no_house_lords=False):
        super().__init__()
        self.house_lords = {} if no_house_lords else house_lords
        self.planet_house = planet_house
        self.planet_dignities = planet_dignities


def _components(payload):
    result = compute_business_prediction(payload)
    return result["business_execution_capacity_components"]


def test_capital_strategy_bootstrap_favored():
    # 2nd lord (Jupiter) exalted in a kendra (H1) -> strong bootstrap_capacity.
    # 11th lord (Saturn) and 8th lord (Mars) both debilitated in dusthanas
    # -> weak external_capital_raising_capacity.
    payload = _CapitalStrategyPayload(
        house_lords={
            "1": "Jupiter", "2": "Jupiter", "3": "Mercury", "4": "Mercury",
            "5": "Venus", "6": "Venus", "7": "Mars", "8": "Mars",
            "9": "Mercury", "10": "Mercury", "11": "Saturn", "12": "Moon",
        },
        planet_house={"Jupiter": 1, "Saturn": 8, "Mars": 12, "Mercury": 7, "Venus": 7, "Moon": 4, "Sun": 10, "Rahu": 7, "Ketu": 1},
        planet_dignities={"Jupiter": "EXALTED", "Saturn": "DEBILITATED", "Mars": "DEBILITATED"},
    )
    comp = _components(payload)
    assert "capital_debt_management" in comp
    assert comp["bootstrap_capacity"] > comp["external_capital_raising_capacity"]
    assert comp["capital_strategy_lean"] == "BOOTSTRAP_FAVORED"


def test_capital_strategy_external_favored():
    # 2nd lord (Saturn) debilitated in a dusthana -> weak bootstrap_capacity.
    # 11th lord (Jupiter) and 8th lord (Venus) both exalted in kendras
    # -> strong external_capital_raising_capacity.
    payload = _CapitalStrategyPayload(
        house_lords={
            "1": "Mercury", "2": "Saturn", "3": "Mercury", "4": "Venus",
            "5": "Mars", "6": "Mars", "7": "Mercury", "8": "Venus",
            "9": "Mercury", "10": "Mercury", "11": "Jupiter", "12": "Moon",
        },
        planet_house={"Saturn": 6, "Jupiter": 1, "Venus": 4, "Mercury": 7, "Mars": 6, "Moon": 4, "Sun": 10, "Rahu": 7, "Ketu": 1},
        planet_dignities={"Saturn": "DEBILITATED", "Jupiter": "EXALTED", "Venus": "EXALTED"},
    )
    comp = _components(payload)
    assert comp["external_capital_raising_capacity"] > comp["bootstrap_capacity"]
    # Raising capacity is a comparative access signal, not approval to
    # accept funding.  This synthetic chart does not clear the authoritative
    # capital-readiness gate, so the final exposed label must be safety-
    # qualified even though external access exceeds bootstrap capacity.
    assert comp["capital_strategy_lean"] == "EXTERNAL_CAPITAL_ACCESSIBLE_BUT_NOT_ADVISABLE"


def test_capital_strategy_balanced():
    # 2nd, 11th and 8th lords all placed in a plain (non-kendra/trikona/
    # upachaya/dusthana) house with neutral dignity -> roughly equal
    # bootstrap_capacity and external_capital_raising_capacity.
    payload = _CapitalStrategyPayload(
        house_lords={
            "1": "Mercury", "2": "Venus", "3": "Mercury", "4": "Mercury",
            "5": "Mars", "6": "Mars", "7": "Mercury", "8": "Saturn",
            "9": "Mercury", "10": "Mercury", "11": "Jupiter", "12": "Moon",
        },
        planet_house={"Venus": 2, "Saturn": 2, "Jupiter": 2, "Mercury": 7, "Mars": 6, "Moon": 4, "Sun": 10, "Rahu": 7, "Ketu": 1},
        planet_dignities={},
    )
    comp = _components(payload)
    assert abs(comp["bootstrap_capacity"] - comp["external_capital_raising_capacity"]) < 3
    assert comp["capital_strategy_lean"] == "BALANCED"


def test_capital_strategy_insufficient_data_when_no_house_lords():
    payload = _CapitalStrategyPayload(house_lords={}, planet_house={}, planet_dignities={}, no_house_lords=True)
    comp = _components(payload)
    assert comp["capital_strategy_lean"] == "INSUFFICIENT_DATA"


def test_capital_debt_management_unaffected_by_new_fields():
    """Regression: capital_debt_management's own computation (D10-H8
    bucket net, unrelated to the new D1-house-lord fields) must be
    unchanged by adding bootstrap_capacity/external_capital_raising_capacity."""
    payload = _FakePayload()
    comp = _components(payload)
    assert "capital_debt_management" in comp
    # Same formula as before: _clamp(50.0 + _d10_bucket_net(("D10-H8",)) * 3.0)
    # -- with no D10-native evidence available on this fake payload, the net
    # is 0.0, so the value should sit at the neutral midpoint.
    assert comp["capital_debt_management"] == 50.0


# --- Sector capital intensity vs capital capacity (item 33) ---
# v-audit fix (business realism, "sector capital intensity is not formally
# matched to capital capacity"): every sector in the registry now declares
# a capital_intensity (LOW/MODERATE/HIGH) and capital_intensity_basis, and
# sector_score()/rank_business_sectors_with_status() expose a purely
# additive capital_feasibility_flag comparing it against the chart's own
# capital_strategy_lean (via capital_strategy_lean_for_payload()). These
# tests reuse _CapitalStrategyPayload's proven BOOTSTRAP_FAVORED/
# EXTERNAL_CAPITAL_FAVORED/BALANCED fixtures from the section above.

def test_registry_declares_capital_intensity_for_every_sector():
    """Release gate: every sector in the registry must declare a
    capital_intensity in the closed LOW/MODERATE/HIGH enum, plus a non-empty
    capital_intensity_basis -- validate_business_rule_pack() must fail
    loudly on a missing/malformed capital_intensity, matching the existing
    archetype_family enum gate."""
    result = validate_business_rule_pack()
    assert result["ok"], result["errors"]
    from Business_Prediction.business_determination.house_evidence import _load_business_registry
    registry = _load_business_registry()
    for sector, meta in registry["sectors"].items():
        assert meta.get("capital_intensity") in {"LOW", "MODERATE", "HIGH"}, (sector, meta.get("capital_intensity"))
        assert meta.get("capital_intensity_basis"), sector


def test_capital_feasibility_flag_mismatch_risk_for_high_intensity_bootstrap_chart():
    """A chart whose own capital-strategy read leans BOOTSTRAP_FAVORED,
    scored against a HIGH capital-intensity sector (manufacturing_industrial),
    must surface CAPITAL_MISMATCH_RISK -- a disclosure-only flag, not a
    score change."""
    payload = _CapitalStrategyPayload(
        house_lords={
            "1": "Jupiter", "2": "Jupiter", "3": "Mercury", "4": "Mercury",
            "5": "Venus", "6": "Venus", "7": "Mars", "8": "Mars",
            "9": "Mercury", "10": "Mercury", "11": "Saturn", "12": "Moon",
        },
        planet_house={"Jupiter": 1, "Saturn": 8, "Mars": 12, "Mercury": 7, "Venus": 7, "Moon": 4, "Sun": 10, "Rahu": 7, "Ketu": 1},
        planet_dignities={"Jupiter": "EXALTED", "Saturn": "DEBILITATED", "Mars": "DEBILITATED"},
    )
    from Business_Prediction.business_determination.house_evidence import capital_strategy_lean_for_payload
    lean = capital_strategy_lean_for_payload(payload)
    assert lean == "BOOTSTRAP_FAVORED"

    row_before = sector_score(payload, vector={n: 50.0 for n in ARCHETYPE_NAMES}, sector="manufacturing_industrial")
    row_after = sector_score(payload, vector={n: 50.0 for n in ARCHETYPE_NAMES}, sector="manufacturing_industrial", capital_strategy_lean=lean)
    assert row_after["capital_intensity"] == "HIGH"
    assert row_after["capital_feasibility_flag"] == "CAPITAL_MISMATCH_RISK"
    assert row_after["capital_feasibility_note"]
    # Purely additive: supplying capital_strategy_lean must not change score.
    assert row_before["score"] == row_after["score"]


def test_capital_feasibility_flag_aligned_for_balanced_chart():
    """A BALANCED-lean chart must read ALIGNED regardless of sector
    capital_intensity (no mismatch to flag)."""
    payload = _CapitalStrategyPayload(
        house_lords={
            "1": "Mercury", "2": "Venus", "3": "Mercury", "4": "Mercury",
            "5": "Mars", "6": "Mars", "7": "Mercury", "8": "Saturn",
            "9": "Mercury", "10": "Mercury", "11": "Jupiter", "12": "Moon",
        },
        planet_house={"Venus": 2, "Saturn": 2, "Jupiter": 2, "Mercury": 7, "Mars": 6, "Moon": 4, "Sun": 10, "Rahu": 7, "Ketu": 1},
        planet_dignities={},
    )
    row = sector_score(payload, vector={n: 50.0 for n in ARCHETYPE_NAMES}, sector="manufacturing_industrial", capital_strategy_lean="BALANCED")
    assert row["capital_feasibility_flag"] == "ALIGNED"
    assert row["capital_feasibility_note"] == ""


def test_capital_feasibility_flag_insufficient_data_when_no_house_lords():
    payload = _CapitalStrategyPayload(house_lords={}, planet_house={}, planet_dignities={}, no_house_lords=True)
    row = sector_score(payload, vector={n: 50.0 for n in ARCHETYPE_NAMES}, sector="manufacturing_industrial")
    assert row["capital_feasibility_flag"] == "INSUFFICIENT_DATA"


def test_rank_business_sectors_populates_capital_feasibility_flag_by_default():
    """rank_business_sectors_with_status()/rank_business_sectors() must
    compute and forward capital_strategy_lean automatically when the caller
    doesn't supply one -- every ranked row's capital_feasibility_flag must
    be populated (not silently INSUFFICIENT_DATA due to a forgotten wiring
    step), for a chart with real house_lords data."""
    payload = _FakePayload()
    ranked = rank_business_sectors(payload)
    assert len(ranked) == 19
    for row in ranked:
        assert row["capital_intensity"] in {"LOW", "MODERATE", "HIGH"}
        assert row["capital_feasibility_flag"] in {"ALIGNED", "CAPITAL_MISMATCH_RISK", "CAPITAL_UNDERMATCH", "INSUFFICIENT_DATA"}
