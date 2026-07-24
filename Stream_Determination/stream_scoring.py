"""Astrological scorer for the under-15 broad-stream + subject engine.

Deliberately NOT a re-run of Field_Determination's six-method bundle -- that
machinery (KNRao/KP/Jaimini/Parashara/Dashamsha/Sudarshana, cross-method
clarity/outlier/correlation weighting) is built for adjudicating between 199
specific vocational branches for a chart old enough to have a stable D10 and
meaningful dasha-timed career signal. At under-15 the only defensible ask is
much coarser: which of the 3 broad streams does the chart's natal (D1)
planetary strength pattern support, and within each stream, which subjects.

Reused from the rest of the codebase (read-only, no shared mutable state):
  jyotish.constants._DIGNITY_MOD  -- classical-dignity -> numeric multiplier
                                      (used only for the D24 confirmation
                                      section below -- see note there on why
                                      it is NOT reapplied to eff_strengths).
  Field_Determination/field_methods/common.py -- method_result/rubric_section/
      clamp_score/build_score_rubric, so this engine's output has the same
      auditable rubric shape as the main engine's, for report consistency.

SCORING_CONTRACT_VERSION below tracks the *formula* (which sections exist,
their caps, the weighting logic) separately from STREAM_ENGINE_VERSION
(the module as a whole). 2026-07-22 audit finding: three different formula
generations had shipped under the same "stream-determination.v1" label with
no way to tell which report was scored under which -- bump
SCORING_CONTRACT_VERSION on every rubric-shape change from now on, even if
STREAM_ENGINE_VERSION doesn't move.
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
from typing import Any, Dict, List

from jyotish.constants import _DIGNITY_MOD, _SIGN_LORD, _SIGN_NUM
from jyotish.astro import (
    _get_planetary_aspects,
    _compute_jaimini_argala,
    _compute_jaimini_virodhargala,
    compute_d24_chart,
    _get_active_chara_dasha_sign,
    _detect_jaimini_raj_yogas,
    _get_active_dasha_lord,
)
from jyotish.dignity import dignity_state
# GAP-FIX (2026-07-24, CRITICAL bug #2, unit-mismatch in Stage 2 dignity/
# strength tiebreaker): _PLANET_MIN_SHADBALA is the classical BPHS minimum-
# required shadbala virupa total per planet (Sun 390, Moon 360, Mars 300,
# Mercury 420, Jupiter 390, Venus 330, Saturn 300, Rahu/Ketu 300 -- see
# jyotish/ontology_kg.py). eff_strengths (jyotish/payload.py: "shadbala/
# min_sv ratio; 1.0=minimum, >1=stronger") is raw_shadbala/min_v-derived and
# lives on a ~1-3 scale. Any raw shadbala_virupas fallback used alongside
# eff_strengths MUST be divided by this same reference before comparison --
# otherwise a ~300 raw virupa value is compared directly against a ~1-3
# eff_strengths value and "wins" purely from being on the wrong scale.
from jyotish.ontology_kg import _PLANET_MIN_SHADBALA

# GAP-FIX (2026-07-22k, audit gap 8, "port jaimini.py logic here"): reused
# directly from Field_Determination/field_methods/jaimini.py rather than
# re-derived -- both are pure sign-arithmetic helpers with no side effects
# and no dependency back on this package, so importing them keeps the two
# engines' Jaimini rasi-drishti/house-distance math identical instead of
# risking two copies drifting apart over time.
from Field_Determination.field_methods.jaimini import _house_distance, _check_chara_drishti

from Field_Determination.field_methods.common import (
    build_score_rubric,
    clamp_score,
    method_result,
    normalize_method_score,
    rubric_section,
)

from .subject_registry import STREAM_META, SUBJECT_REGISTRY, SCIENCE_SUBJECT_BUNDLES, SUBJECT_SUB_ARCHETYPES
from .calibration import calibration_state
# GAP-FIX (field-derived-evidence, optional 8th rubric section, default off):
# only the cap constant is imported at module load time -- the actual
# safe_derive_stream_marks() call (which runs the adult engine) is imported
# lazily inside compute_stream_determination() so importing stream_scoring.py
# never has an import-time dependency on the adult engine being importable.
from .field_derived_stream import FIELD_DERIVED_EVIDENCE_CAP

# GAP-FIX (2026-07-22h, audit gaps 2/3/5, CONFIRMED real problem): a report
# claiming "stream-scoring-contract.2026-07-22g" only proves what STRING the
# code that produced it happened to declare -- it does not prove which
# actual bytes of stream_scoring.py/subject_registry.py were executing at
# the time (the audit caught exactly this: reports carrying a v2 label while
# the reviewed source on disk was still v1). Hashing the two source files
# this engine's entire scoring logic lives in gives an independently
# verifiable fingerprint of the executing build, orthogonal to whatever
# version string a human remembered to bump.
# GAP-FIX (audit #6): previously only hashed this package's own 4 files --
# every actual astrological calculation this engine depends on (D24
# construction, Jaimini argala/dasha/raj-yoga helpers, sign/dignity tables)
# lives upstream in jyotish/*, so a silent change there was invisible to this
# fingerprint. Extended to hash the specific upstream files this engine
# actually imports from (see stream_scoring.py's own import block above).
# STILL not a full reproducibility contract -- it does not hash the course
# registry JSON, ephemeris data files (de421.bsp), or the Python
# interpreter/dependency versions (skyfield, etc.). Those would need a
# separate environment-fingerprint mechanism, not a source-file hash, since
# they aren't Python source this repo owns.
def _engine_build_fingerprint() -> Dict[str, str]:
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(this_dir)
    hashes: Dict[str, str] = {}

    def _hash(rel_path: str, key: str) -> None:
        fpath = os.path.join(repo_root, rel_path)
        try:
            with open(fpath, "rb") as f:
                hashes[key] = hashlib.sha256(f.read()).hexdigest()[:16]
        except OSError:
            hashes[key] = "UNAVAILABLE"

    for fname in ("stream_scoring.py", "subject_registry.py", "stream_report.py",
                  "early_age_stream_engine.py"):
        _hash(os.path.join("Stream_Determination", fname), fname)
    for rel in ("jyotish/astro.py", "jyotish/engine_io.py", "jyotish/constants.py"):
        _hash(rel, rel)
    _hash(os.path.join("Field_Determination", "field_methods", "jaimini.py"),
          "Field_Determination/field_methods/jaimini.py")
    _hash(os.path.join("Field_Determination", "field_methods", "common.py"),
          "Field_Determination/field_methods/common.py")
    # Runtime/data identities are part of reproducibility too.  Source hashes
    # alone cannot explain a result produced with a different interpreter,
    # registry or ephemeris file.
    hashes["python_version"] = sys.version.split()[0]
    for rel in (
        "Stream_Determination/course_registry_v12.json",
        "Stream_Determination/subject_registry.py",
        "de421.bsp",
        "jyotish/de421.bsp",
    ):
        if rel not in ("Stream_Determination/subject_registry.py",):
            _hash(rel, rel)
    return hashes


_ENGINE_BUILD_FINGERPRINT = _engine_build_fingerprint()

# GAP-FIX (audit #45, then re-fixed this turn): this used to be duplicated
# in early_age_stream_engine.py too (both hardcoded to 15.0, "change one
# change both" left as a drift risk). Now THIS is the single source of
# truth -- early_age_stream_engine.py imports it from here instead of
# declaring its own copy (safe direction: that module already imports FROM
# this one, so no circular import).
AGE_THRESHOLD_YEARS = 15.0

STREAM_ENGINE_VERSION = "stream-determination.v5"
CALCULATION_PROFILE = "D1_TREE_D24_FRUIT_CLASSICAL_PRECEDENCE"
# GAP-FIX (2026-07-22e, audit gaps 7/8): rubric shape changed -- two new
# bounded sections added (relational_d1, jaimini_apparatus), caps rebalanced
# on the other five sections to keep the total at 100. See score_stream()'s
# docstring for the full new cap table.
# 2026-07-22f: fixed a confirmed cap-aggregation bug (audit P0-1) -- the
# final score now sums each section's CAPPED display value (rubric's
# display_total), not the uncapped actual value. See score_stream()'s inline
# comment at the total_raw assignment for the full history/impact.
# 2026-07-22g: audit items 10/11/12/13/14/17/19/26 -- role_placement
# hierarchy rebalanced (5th/9th lord now outweigh 10th lord/AmK for a
# school-stream decision), relational_d1 and jaimini_apparatus contributions
# scaled by each qualifying planet's cross-stream exclusivity (a planet
# shared by 2-3 streams' lists can no longer earn full, undiscounted credit
# in every one of them), mandatory-planet ceiling curve steepened from a
# near-cosmetic linear falloff to a shortfall-scaled one, "classical
# minimum-viable baseline" reworded to "engineered minimum-support
# threshold", D24 "no match" now carries an explicit NEUTRAL_NO_SIGNAL
# signal_state (distinct from a contradiction), and birth-time precision/
# uncertainty metadata no longer silently implies 0-minute uncertainty when
# precision is actually unknown.
# 2026-07-22h: audit items 2/3/5 (engine_build_fingerprint -- sha256 of this
# package's own source files, independent of any version string), 9 (D24
# dignity confirmation now tied to the specific educational lord(s) that
# already matched a house-placement role, not averaged across the whole
# stream planet list), 16 (subject_evidence discounted by how circular the
# used subjects' planet signature is relative to the stream's own planet-
# weight vector), 22/23/24 (sub_archetype label from the top-ranked core
# subject(s), e.g. "Science (Technical/Engineering)" vs "Science (Life
# Science/Medical)" -- labeling only, does not change scoring).
# 2026-07-22i: audit gaps 4/5 (D24_CONSTRUCTION_MISMATCH -- in-house
# Chaturvimshamsha recompute via jyotish.astro.compute_d24_chart, cross-
# checked against upstream D24 data; disagreeing planets are excluded from
# D24 role/dignity evidence rather than trusted either way; D24 Lagna itself
# is explicitly flagged UNVERIFIABLE since no lagna_degree field exists on
# the payload to re-derive it) and gap 13 (Jaimini apparatus gains a chara-
# dasha confirmation component, reusing the same _get_active_chara_dasha_sign
# already trusted by Field_Determination/field_methods/jaimini.py).
# 2026-07-22j: audit gaps 6/8/15 -- d24_confirmation gains a D24
# house-support component (this stream's own signature planets' D24
# placement, not just the 3 fixed lord roles) and a dispositor/combustion
# affliction discount on those lord roles; jaimini_apparatus gains karakamsha
# OCCUPANTS (not just sign-lord), 5th/9th/10th-from-karakamsha lords, and
# AK/AmK Jaimini raja-yoga detection (reusing the same
# _detect_jaimini_raj_yogas already trusted in Field_Determination/
# field_methods/jaimini.py). Caps rebalanced: d24_confirmation 20->25,
# jaimini_apparatus 8->13, planetary_strength 28->22, subject_evidence
# 18->14 to keep the total at 100. compute_d24_sign/compute_d24_chart (the
# in-house D24 recompute added in 2026-07-22i for the construction-mismatch
# check) are now formally validated by jyotish/tests/test_d24_construction.py,
# the same validation discipline compute_d10_sign already has.
# 2026-07-22k ("port jaimini.py logic here"): ported the three remaining
# named-but-missing pieces from Field_Determination/field_methods/jaimini.py
# into jaimini_apparatus -- Upapada Lagna sign-lord confirmation,
# Karakamsha's own rasi-drishti onto the D1 lagna, and the AK/AmK-weighted
# chara-karaka house-distance/drishti matrix (adapted from jaimini.py's
# field_affinity-weighted design to this engine's stream-planet-weight
# design). _house_distance/_check_chara_drishti are imported directly from
# jaimini.py rather than re-derived, so the two engines' rasi-drishti math
# cannot drift apart. Caps rebalanced: jaimini_apparatus 13->16,
# planetary_strength 22->19, keeping the total at 100.
# 2026-07-22l: fixed 4 gaps caught auditing a live Ramsunder report --
# (1) role_placement's note text was stale, omitting the 9th lord role
# added back in 2026-07-22g; (2) D24's dispositor/combustion affliction
# discount was sized off the role's CONFIGURED base weight rather than what
# it actually earned after house-weighting, letting the discount exceed
# 100% of that role's own credit and bleed into unrelated D24 components
# (CONFIRMED real bug); (3) jaimini_apparatus's exclusivity-scaled
# components were hard-clipped at the section cap, which asymmetrically
# punished charts whose Karakamsha lord happens to be stream-exclusive --
# now soft-compressed (tanh, same shape as clamp_score) above 75% of cap;
# (4) d24_confirmation now explicitly logs "checked, no match" for a known
# lord that simply didn't land in-house, mirroring role_placement's
# roles_missing transparency.
# 2026-07-24: bumped v4->v5 -- D24/JAIMINI ARBITRATION POLICY (see comment
# block above compute_stream_determination()) is a genuine rubric-shape
# change: when it fires, affected streams gain an additional
# "d24_arbitration_boost" rubric section not present in v4 reports, and
# score/normalized_score for those streams are computed AFTER that section
# is folded in, not purely from score_stream()'s own 7/8 sections anymore.
# 2026-07-24: bumped v6->v7 -- fixed two CRITICAL bugs from the external
# review (md/STREAM_DETERMINATION_CRITICAL_FIXES_20260724.md): (1) `streams`
# is no longer reordered by the classical precedence chain -- it is always
# in pure normalized_score-descending order now, and the report gained four
# new top-level fields (numeric_rank, d1_candidate_rank, precedence_decision,
# recommended_stream) so "numeric score leader" and "precedence-chain
# decision" are never conflated again; (2) Stage 2 (dignity/strength
# tiebreaker) no longer compares raw shadbala_virupas (~0-450 scale)
# directly against eff_strengths (~1-3 scale) -- the raw fallback is now
# normalized through _PLANET_MIN_SHADBALA before it can participate in the
# comparison. Any report/consumer keyed on scoring_contract_version should
# treat v6 and v7 reports as NOT directly comparable for dominant_stream/
# top_ranked_stream semantics.
#
# v8 (2026-07-24, this turn): (1) Stage 4 (dasha-relevance) gained an
# explicit as_of_date parameter threaded all the way from
# compute_stream_determination()/run_for_payload()/run_for_chart_file()/the
# --as-of-date CLI flag down to _stage4_dasha_relevance() -- date.today() is
# now used ONLY when as_of_date is not explicitly supplied, and the resolved
# date is echoed onto every report as "evaluation_as_of_date" so a saved
# report's dasha-stage evaluation is fully reproducible and traceable (see
# md/STREAM_DETERMINATION_DASHA_JAIMINI_DEPTH_20260724.md). (2) Stage 3
# (Jaimini AK/AmK) gained 5 additional classical checks -- 10th-from-
# Karakamsha, rasi-drishti (Jaimini whole-sign aspect), AK-AmK sambandha
# (with explicit contradiction surfacing when absent), AmK dignity/strength
# scaling (replacing the old flat AmK bonus), and an AmK/Karakamsha
# affliction check that dampens Stage 3 confidence -- all documented on the
# new "jaimini_depth_detail" field. Both changes can genuinely change
# precedence_chain_resolution_stage/recommended_stream on some charts (2 of
# 19 real production charts changed, both from "still_tied_after_full_chain"
# to a resolved "jaimini_akamk" stage -- see the doc above); v7 and v8
# reports are NOT guaranteed to agree on Stage 3/Stage 4 outcomes.
SCORING_CONTRACT_VERSION = "stream-scoring-contract.2026-07-24-v8"

_ALL_PLANETS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")


# GAP-FIX (2026-07-22, audit P0-2, CONFIRMED against source): jyotish/astro.py
# ::_compute_eff_strengths() already folds planet_dignities AND combustion
# (plus Digbala, Vargottama, Paksha Bala, planetary war, nakshatra-lord-house,
# neecha-bhanga...) into the eff_strengths ratio it returns -- verified by
# reading the function directly (search "_DIGNITY_MOD" and "comb_mod" in
# jyotish/astro.py). The previous version of this file re-multiplied
# eff_strengths by _DIGNITY_MOD AND applied a second combustion penalty on
# top -- a genuine double-count that artificially amplified exalted planets
# and over-penalized debilitated/combust ones a second time. eff_strengths
# is used AS-IS now; do not re-apply dignity or combustion adjustments here.
def _planet_strength(payload: Any, planet: str) -> float | None:
    """Effective strength for one planet, taken directly from the shared
    astrology layer's already-fully-adjusted eff_strengths (1.0 = minimum
    viable strength, >1 = progressively stronger; already includes dignity,
    combustion, Digbala, Vargottama, Paksha Bala, planetary war, and more --
    see jyotish/astro.py::_compute_eff_strengths)."""
    strengths = getattr(payload, "eff_strengths", {}) or {}
    if planet not in strengths or strengths.get(planet) is None:
        return None
    try:
        value = float(strengths[planet])
    except (TypeError, ValueError):
        return None
    # GAP-FIX (audit #63): float("nan")/float("inf") parse successfully --
    # TypeError/ValueError above never catches them -- so a malformed
    # upstream value (NaN from a division-by-zero elsewhere, or +/-inf) would
    # previously flow silently into weighted averages and corrupt every
    # section that touches this planet, with no visible error anywhere.
    # Treat as missing data (None) rather than a real strength value --
    # honest "no signal" beats a silently poisoned score.
    if not math.isfinite(value):
        return None
    return max(0.0, value)


def _stream_planet_strengths(payload: Any) -> Dict[str, float | None]:
    return {p: _planet_strength(payload, p) for p in _ALL_PLANETS}


# GAP-FIX (2026-07-22g, audit gaps 10/12/13/14): a planet like Mercury sits on
# 2-3 streams' signature-planet lists at once (Science, Commerce, and
# implicitly touching Humanities' subject registry too), so any bounded
# section that credits "this planet belongs to the stream" full marks in
# EVERY stream that lists it is not actually discriminating between streams
# -- it is rewarding a fact common to most charts, in most streams, almost
# every time. _planet_exclusivity scales such a section's contribution down
# in proportion to how many streams the planet is shared across (1.0 for a
# planet unique to one stream's list, 0.5 for a planet on two streams' lists,
# 0.33 for all three) -- used by relational_d1 and jaimini_apparatus below so
# a shared planet still counts, but no longer as if it were stream-exclusive
# evidence.
def _planet_exclusivity(planet: str) -> float:
    count = sum(1 for meta in STREAM_META.values() if planet in meta["planets"])
    return 1.0 / count if count else 0.0


def _house_support(payload: Any, planet: str, houses: List[int], house_weights: Dict[int, float]) -> float:
    """Weighted count of stream-house occupancy/lordship by this planet.

    GAP-FIX (2026-07-22, audit gap 9/11): now scaled by the SAME per-house
    house_weights used by role_placement, instead of a flat +1 per hit --
    so a universal house that happens to be in a stream's list (e.g.
    Commerce's H10/H11) contributes proportionally less than a house that's
    genuinely specific to that stream (Commerce's H2/H7).
    """
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords = getattr(payload, "house_lords", {}) or {}
    total = 0.0
    own_house = planet_house.get(planet)
    for h in houses:
        w = house_weights.get(h, 1.0)
        # Occupying a house and ruling that same house are two descriptions
        # of one planet-house relationship, not two independent testimonies.
        # Credit the relationship once; otherwise a planet that both occupies
        # and owns H5/H9 can silently receive double house-support points.
        if own_house == h or house_lords.get(str(h)) == planet:
            total += w
    return total


# GAP-FIX (2026-07-22, audit): the fixed per-stream planet-weight table
# (STREAM_META[...]['planets']) can only ever reward a planet that happens
# to be on that stream's hard-coded list, at that stream's hard-coded
# weight -- it has no way to notice that, on THIS specific chart, a planet
# NOT on the list (or on it at only a modest weight) is doing something
# structurally decisive: e.g. it is the 10th-house (career) lord, the
# Atmakaraka (soul-significator, highest classical authority for vocation
# in Jaimini astrology -- see Field_Determination/field_methods/jaimini.py's
# own centering on AK/AmK), the Amatyakaraka (career-significator), or the
# 5th (education/vidya) lord, and it is SITTING in a house that is this
# stream's own classical domain.
# GAP-FIX (2026-07-22g, audit gap 11): audit's own hierarchy for an under-15
# STREAM (not career) decision is D1 5th/9th promise first, career factors
# (10th lord, AmK, A10) as secondary confirmation only -- the previous
# weights inverted this (h10_lord=6.0 outweighed h5_lord=5.0, and h9_lord
# wasn't even checked as its own role). Now h5_lord/h9_lord (vidya/higher-
# learning) sit above h10_lord/AmK (career/vocation); AK stays close to h5/h9
# since Jaimini treats it as the chart's deepest soul-purpose signal, not a
# purely career one.
# GAP-FIX (audit -- "5th/9th indicators not separated into basic education
# vs subject aptitude vs higher learning"): BPHS assigns the 4th house its
# own, DIFFERENT educational signification (vidya-sthana in the sense of
# foundational/basic schooling -- alongside its more commonly cited comforts/
# mother/home significations), distinct from the 5th (buddhi/intelligence/
# aptitude, purva-punya) and 9th (higher learning, dharma, guru) this engine
# already checked. Adding h4_lord as its own role closes a real, classically-
# grounded gap rather than continuing to fold "is this child's educational
# foundation stable" into the aptitude-specific 5th-house signal. Weighted
# below h5/h9 (foundational schooling is real evidence but less stream-
# DISCRIMINATING than aptitude/higher-learning specifics -- a stable
# foundation says little about which of Science/Commerce/Humanities suits
# this chart) and below the career-secondary factors' AK, but above h10/AmK
# since it is still a primary EDUCATIONAL (not career) signal.
_ROLE_PLACEMENT_WEIGHTS: Dict[str, float] = {
    "h5_lord": 6.0,         # 5th (vidya/aptitude/buddhi) lord -- primary educational signal
    "h9_lord": 6.0,         # 9th (higher learning/dharma) lord -- primary educational signal
    "atmakaraka": 4.5,      # AK -- soul/vocational significator (Jaimini)
    "h4_lord": 3.5,         # 4th (foundational/basic schooling) lord -- primary but less stream-discriminating
    "h10_lord": 3.0,        # career-house lord -- secondary confirmation for a school-age decision
    "amatyakaraka": 2.5,    # AmK -- career/ministerial significator -- secondary confirmation
}


def _role_placement_bonus(payload: Any, houses: List[int], house_weights: Dict[int, float]) -> Dict[str, Any]:
    """Bounded bonus (cap enforced by caller via rubric_section) for a
    stream's classical significator houses actually containing the chart's
    10th lord, Atmakaraka, Amatyakaraka, and/or 5th (education) lord.

    GAP-FIX (2026-07-22, audit P0-5, CONFIRMED live on Ramsunder/Ananyaa):
    when the SAME planet holds more than one role (e.g. Saturn is both
    Atmakaraka AND 5th lord, and both point at the same house), the
    previous version summed every matching role's weight independently --
    double- (or triple-) counting one underlying astrological fact as if it
    were several separate testimonies. Now grouped by planet: a planet
    holding multiple roles is counted ONCE, at its single highest-weighted
    role, with the other roles it also holds noted for transparency but not
    additionally scored.
    """
    planet_house = getattr(payload, "planet_house", {}) or {}
    house_lords = getattr(payload, "house_lords", {}) or {}
    role_planets = {
        "h5_lord": house_lords.get("5", "") or getattr(payload, "h5_lord", "") or "",
        "h9_lord": house_lords.get("9", "") or getattr(payload, "h9_lord", "") or "",
        "atmakaraka": getattr(payload, "atmakaraka", "") or "",
        # GAP-FIX (audit -- basic-education vs aptitude/higher-learning
        # separation): 4th lord, not previously checked at all -- see
        # _ROLE_PLACEMENT_WEIGHTS' comment above for the classical rationale.
        "h4_lord": house_lords.get("4", "") or getattr(payload, "h4_lord", "") or "",
        # Payloads produced by older engine_io versions expose H10 only in
        # house_lords. Accept both representations so schema evolution does
        # not erase a major role signal.
        "h10_lord": getattr(payload, "h10_lord", "") or house_lords.get("10", "") or "",
        "amatyakaraka": getattr(payload, "amatyakaraka", "") or "",
    }
    known_roles = {role: planet for role, planet in role_planets.items() if planet}

    by_planet: Dict[str, List[str]] = {}
    for role, planet in known_roles.items():
        by_planet.setdefault(planet, []).append(role)

    raw = 0.0
    matches: List[str] = []
    planets_credited: set = set()
    for planet, roles in by_planet.items():
        placed_house = planet_house.get(planet)
        if placed_house not in houses:
            continue
        weight_house = house_weights.get(placed_house, 1.0)
        strongest_role = max(roles, key=lambda r: _ROLE_PLACEMENT_WEIGHTS[r])
        contribution = _ROLE_PLACEMENT_WEIGHTS[strongest_role] * weight_house
        raw += contribution
        planets_credited.add(planet)
        role_desc = "+".join(roles) if len(roles) > 1 else roles[0]
        matches.append(
            f"{planet} (role(s): {role_desc}) in house {placed_house} -- counted once via "
            f"strongest role '{strongest_role}' (house_weight={weight_house:.2f} -> +{contribution:.2f})"
        )

    # GAP-FIX (audit #62): d24_confirmation already distinguishes
    # POSITIVE_SUPPORT from NEUTRAL_NO_SIGNAL (no house match is not the
    # same as "this stream is contraindicated") -- role_placement previously
    # had no equivalent, so a raw=0.0 here read identically to a real
    # negative signal even though this section has no negative branch at
    # all (that's contraindications' job). Same convention now applied here
    # and to relational_d1 below, for cross-section consistency.
    signal_state = "POSITIVE_SUPPORT" if raw > 0 else "NEUTRAL_NO_SIGNAL"
    return {
        "raw": raw,
        "matches": matches,
        "roles_known": sorted(known_roles.keys()),
        "roles_missing": sorted(set(role_planets.keys()) - set(known_roles.keys())),
        "data_status": "COMPLETE" if len(known_roles) == len(role_planets) else (
            "PARTIAL" if known_roles else "MISSING"
        ),
        "signal_state": signal_state,
        "planets_credited": planets_credited,
    }


# GAP-FIX (2026-07-22, audit gap 6): first-pass D24 (Siddhamsha, the
# classical education/learning-capacity varga) integration. NOT a full
# classical D24 methodology (that would need its own dedicated method file,
# analogous to field_methods/dashamsha.py's D10 treatment) -- this reuses
# only what jyotish/engine_io.py already computes on every payload
# (d24_house_lords, d24_planet_dignities, d24_house_occupancy) as a bounded,
# clearly-labelled additive confirmation, exactly the same "bounded nudge"
# pattern used everywhere else in this codebase. Two components:
#   1. D24 lagna/5th/9th lord placement in the stream's own houses,
#      interpreted in D24 house-space (same house-number convention as D1,
#      applied to the D24 chart's own lords/occupants).
#   2. Average D24 dignity of the stream's D1 signature planets, as a
#      "does this planet's LEARNING/curriculum expression (D24) agree with
#      its natal (D1) promise" confirmation.
_D24_ROLE_WEIGHTS: Dict[str, float] = {
    "d24_lagna_lord": 5.0,
    "d24_h5_lord": 5.0,
    "d24_h9_lord": 5.0,
    # GAP-FIX (2026-07-24, explicit user request: "full D24 Siddhamsha
    # ontology"): 4th/10th lords added alongside lagna/5th/9th, weighted
    # below the primary learning houses -- consistent with the D1
    # role_placement precedent (h4_lord=3.5 < h5/h9=6.0 there) where the 4th
    # house is BPHS vidya-sthana (foundational/basic schooling, a real but
    # secondary educational signal) and the 10th is professional
    # specialization/karma expression, not core aptitude.
    "d24_h4_lord": 3.0,
    "d24_h10_lord": 3.0,
}
_D24_DIGNITY_CAP = 5.0
# GAP-FIX (2026-07-24): dispositor-chain and aspect/conjunction confirmation
# among the D24 role lords, added as two new bounded additive components
# alongside the existing role-placement/dignity/house-support ones. Both
# stay small relative to the primary role-placement evidence -- they are
# corroborating signals (does the chain of rulership/connection also point
# this way), not independent proof.
_D24_DISPOSITOR_CAP = 4.0
_D24_RELATIONAL_CAP = 4.0
# GAP-FIX (2026-07-24, explicit user request, item #3): a separate bounded
# negative channel for D24 debilitation/retrogression of a role lord itself
# (previously the affliction block only looked at D1 combustion and
# DISPOSITOR debilitation, never the role planet's own D24 dignity or its
# retrograde state).
_D24_SELF_AFFLICTION_CAP = 3.0

_KENDRA_HOUSES = (1, 4, 7, 10)
_TRIKONA_HOUSES = (1, 5, 9)
_DUSTHANA_HOUSES = (6, 8, 12)


def _functional_nature(house_lords: Dict[str, str]) -> Dict[str, str]:
    """Lagna-relative functional benefic/malefic classification (item #6).

    Distinct from NATURAL benefic/malefic (Jupiter/Venus/Mercury/waxing-Moon
    are naturally benefic regardless of chart; Saturn/Mars/Sun/Rahu/Ketu are
    naturally malefic regardless of chart) -- FUNCTIONAL nature depends on
    which houses a planet rules FOR THIS SPECIFIC LAGNA. A planet ruling a
    kendra (1/4/7/10) or trikona (1/5/9) house is functionally benefic for
    this chart even if naturally malefic (e.g. Mars is a yogakaraka for
    Cancer/Leo lagna); a planet ruling ONLY dusthana houses (6/8/12) and no
    kendra/trikona is functionally malefic even if naturally benefic.

    Deliberately simplified (documented, not hidden): does not implement the
    full classical yogakaraka/dual-lordship weighting rules (e.g. a planet
    that rules both a kendra AND a dusthana, or the specific
    Venus-for-Libra/Taurus and Saturn-for-Libra/Aquarius yogakaraka special
    cases) -- it uses a single rule: rules-any-kendra-or-trikona ->
    FUNCTIONAL_BENEFIC; rules-dusthana-only -> FUNCTIONAL_MALEFIC; rules
    neither (2/3/11 only, or no house_lords data for that planet) ->
    NEUTRAL. This is an engineering approximation of a real classical
    technique, not the full technique itself.
    """
    planet_houses: Dict[str, List[int]] = {}
    for h_str, planet in (house_lords or {}).items():
        if not planet:
            continue
        try:
            h = int(h_str)
        except (TypeError, ValueError):
            continue
        planet_houses.setdefault(planet, []).append(h)
    result: Dict[str, str] = {}
    for planet, houses_ruled in planet_houses.items():
        rules_kendra_trikona = any(h in _KENDRA_HOUSES or h in _TRIKONA_HOUSES for h in houses_ruled)
        rules_dusthana = any(h in _DUSTHANA_HOUSES for h in houses_ruled)
        if rules_kendra_trikona:
            result[planet] = "FUNCTIONAL_BENEFIC"
        elif rules_dusthana:
            result[planet] = "FUNCTIONAL_MALEFIC"
        else:
            result[planet] = "NEUTRAL"
    return result


# GAP-FIX (2026-07-22i, audit gaps 4/5): planets whose in-house-recomputed
# D24 sign disagrees with the upstream-supplied D24 sign are excluded from
# BOTH the role-placement loop and the dignity-confirmation average below --
# a disagreement means this section cannot trust what house/dignity that
# specific planet's D24 data implies, so it is treated as NOT confirmed
# (excluded) rather than either blindly trusted or used to veto the whole
# section for every stream.
def _d24_construction_mismatches(payload: Any) -> Dict[str, str]:
    """Returns {planet: "upstream_sign vs in_house_sign"} for every planet
    where the in-house Chaturvimshamsha recomputation (compute_d24_chart)
    disagrees with the upstream divisional_charts['D24_siddhamsam'] sign.
    Empty dict if upstream data is missing (nothing to compare) or all
    planets agree."""
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    divisional = getattr(payload, "divisional_charts", {}) or {}
    upstream_d24 = divisional.get("D24_siddhamsam", {}) or {}
    if not upstream_d24 or not planets_d1:
        return {}
    in_house = compute_d24_chart(planets_d1)
    mismatches: Dict[str, str] = {}
    for planet, in_house_sign in in_house.items():
        upstream_sign = upstream_d24.get(planet, "")
        if upstream_sign and in_house_sign and upstream_sign != in_house_sign:
            mismatches[planet] = f"upstream={upstream_sign} vs in_house_recompute={in_house_sign}"
    return mismatches


def _d24_confirmation_section(payload: Any, stream_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    d24_house_lords = getattr(payload, "d24_house_lords", {}) or {}
    d24_occupancy = getattr(payload, "d24_house_occupancy", {}) or {}
    d24_dignities = getattr(payload, "d24_planet_dignities", {}) or {}
    houses: List[int] = meta["houses"]
    house_weights: Dict[int, float] = meta.get("house_weights", {})

    def d24_learning_weight(house: int) -> float:
        """Keep broad D1 houses from becoming false D24 aptitude proof.

        In Siddhamsha, H4/H5/H9 are direct learning houses. H12 can describe
        foreign/retreat/spiritual contexts and is not, by itself, evidence for
        any school stream; H6/H7 are secondary. They remain visible in traces
        but receive only bounded confirmation credit.
        """
        base = house_weights.get(house, 1.0)
        if house == 12:
            return min(base, 0.10)
        if house in (6, 7):
            return min(base, 0.25)
        return base

    if not d24_house_lords or not d24_occupancy:
        return {
            "raw": 0.0, "matches": [],
            "data_status": "MISSING",
            "note": "D24 (Siddhamsha) house lords/occupancy not available on this chart.",
        }

    mismatches = _d24_construction_mismatches(payload)
    # GAP-FIX (2026-07-24, item #6): D1 house_lords is what defines "which
    # houses does this planet rule FOR THIS LAGNA" -- functional nature is a
    # D1 concept (lordship is fixed by the D1 lagna sign) applied here to
    # weight D24-derived confirmation/affliction.
    functional_nature = _functional_nature(getattr(payload, "house_lords", {}) or {})

    d24_planet_house: Dict[str, int] = {}
    for h_str, planets in d24_occupancy.items():
        try:
            h = int(h_str)
        except (TypeError, ValueError):
            continue
        for p in planets or []:
            d24_planet_house[p] = h

    role_planets = {
        "d24_lagna_lord": d24_house_lords.get("1", ""),
        "d24_h5_lord": d24_house_lords.get("5", ""),
        "d24_h9_lord": d24_house_lords.get("9", ""),
        # GAP-FIX (2026-07-24, explicit user request): 4th (vidya-sthana,
        # foundational schooling) and 10th (professional specialization)
        # lords now checked alongside lagna/5th/9th -- see _D24_ROLE_WEIGHTS
        # comment for the weighting rationale.
        "d24_h4_lord": d24_house_lords.get("4", ""),
        "d24_h10_lord": d24_house_lords.get("10", ""),
    }
    raw = 0.0
    matches: List[str] = []
    # GAP-FIX (2026-07-22l): tracks the ACTUAL (house-weighted) contribution
    # each role earned, not just its configured base weight -- the
    # affliction-discount block below needs this to avoid discounting a role
    # by more than it actually earned (see that block's comment for the bug
    # this closes).
    role_earned_contribution: Dict[str, float] = {}
    # GAP-FIX (2026-07-24, item #8/#9, correlation discount): tracks every
    # planet that actually earned credit anywhere in THIS section (role
    # placement, D24 house-support, dispositor chain) so score_stream can
    # compare it against role_placement's own credited-planet set -- see
    # score_stream's correlation-discount comment for why this matters.
    d24_planets_credited: set = set()
    for role, planet in role_planets.items():
        if not planet:
            continue
        if planet in mismatches:
            matches.append(
                f"{role}={planet} EXCLUDED: in-house D24 recompute disagrees with upstream "
                f"({mismatches[planet]}) -- D24_CONSTRUCTION_MISMATCH, not counted as confirmed."
            )
            continue
        placed_house = d24_planet_house.get(planet)
        if placed_house in houses:
            w = d24_learning_weight(placed_house)
            contribution = _D24_ROLE_WEIGHTS[role] * w
            raw += contribution
            role_earned_contribution[role] = contribution
            d24_planets_credited.add(planet)
            matches.append(
                f"{role}={planet} in D24 house {placed_house} "
                f"(house_weight={w:.2f} -> +{contribution:.2f})"
            )
        else:
            # GAP-FIX (2026-07-22l, caught auditing a Ramsunder report):
            # role_placement explicitly lists which roles are unavailable
            # (roles_missing) vs which were checked and didn't match --
            # this section previously stayed silent for a role that WAS
            # known (planet identified, no construction mismatch) but
            # simply didn't land in this stream's houses, indistinguishable
            # from a role that was never evaluated at all. Now explicit.
            matches.append(
                f"{role}={planet} checked, no match: D24 house {placed_house if placed_house else 'unknown'} "
                f"not in {meta['label']}'s houses {houses}."
            )

    # GAP-FIX (2026-07-22h, audit gap 9, CONFIRMED real weakness): dignity
    # confirmation used to average across EVERY one of the stream's D1
    # signature planets, regardless of whether any of them actually hold an
    # educational role in D24 -- so a stream could receive a dignity bonus
    # carried entirely by one strong-but-D24-irrelevant planet while the
    # chart's real D24 lagna/5th/9th lords were weak or unplaced. The chain
    # is now: educational lord (D24 lagna/5th/9th) -> confirmed placement in
    # this stream's D24 houses (from the role loop above) -> THAT planet's
    # own D24 dignity. Only planets that already matched a role above (i.e.
    # actually appear in `matches`) feed the dignity average. If none matched,
    # dignity is neutral: a general stream planet cannot substitute for a
    # missing D24 educational-lord chain.
    matched_role_planets = [role_planets[role] for role, planet in role_planets.items()
                             if planet and planet not in mismatches and d24_planet_house.get(planet) in houses]
    # Construction mismatches are excluded; without a matched educational
    # lord, the dignity source is intentionally empty (neutral confirmation).
    stream_planets = [p for p in meta["planets"].keys() if p not in mismatches]
    if matched_role_planets:
        dig_source = matched_role_planets
        chain_note = "tied to this stream's confirmed D24 educational-lord placement(s)"
    else:
        # Do not manufacture stream confirmation from the dignity of a general
        # signature planet when D24 Lagna/5th/9th lords did not support the
        # stream. That old fallback produced large positive D24 scores for
        # mutually incompatible streams in the batch audit. No educational-
        # lord chain means neutral/no signal, not a second independent bonus.
        dig_source = []
        chain_note = "no D24 educational lord matched this stream's houses -- dignity is neutral"
    dig_values = [
        _DIGNITY_MOD.get(d24_dignities.get(p, ""), 1.0)
        for p in dig_source if p in d24_dignities
    ]
    if dig_values:
        dig_avg = sum(dig_values) / len(dig_values)
        # dig_avg=1.0 (all neutral) -> 0 contribution; dig_avg=1.40 (all
        # exalted) -> the full cap. Floor at 0 (debilitated averages don't
        # go negative here -- D24 is confirmatory-only, not a penalty channel).
        dignity_contribution = max(0.0, min(_D24_DIGNITY_CAP, (dig_avg - 1.0) / 0.40 * _D24_DIGNITY_CAP))
        if dignity_contribution > 0:
            matches.append(
                f"D24 dignity confirmation for {meta['label']} ({chain_note}): "
                f"{', '.join(dig_source)} avg dignity multiplier {dig_avg:.2f} "
                f"-> +{dignity_contribution:.2f}"
            )
        raw += dignity_contribution

    # GAP-FIX (2026-07-22j, audit gap 6): D24 house-support -- do this
    # stream's OWN D1 signature planets (not just the lagna/5th/9th lords)
    # actually sit in this stream's houses when read in D24 house-space?
    # This is the D24 analogue of the D1 house_support section, and is what
    # makes the D24 section "subject-relevant" rather than only checking
    # three fixed lord roles -- a stream can now be confirmed by its own
    # planets' D24 placement even when none of them happen to be the D24
    # lagna/5th/9th lord.
    _D24_HOUSE_SUPPORT_CAP = 6.0
    d24_house_support_raw = 0.0
    d24_house_support_hits: List[str] = []
    for p in stream_planets:
        placed_house = d24_planet_house.get(p)
        if placed_house in houses:
            w = d24_learning_weight(placed_house)
            d24_house_support_raw += 1.5 * w
            d24_house_support_hits.append(f"{p} in D24 house {placed_house}")
            d24_planets_credited.add(p)
    d24_house_support_raw = min(_D24_HOUSE_SUPPORT_CAP, d24_house_support_raw)
    if d24_house_support_raw > 0:
        matches.append(
            f"D24 house-support for {meta['label']}'s own signature planets: "
            f"{'; '.join(d24_house_support_hits)} -> +{d24_house_support_raw:.2f} "
            f"(capped at {_D24_HOUSE_SUPPORT_CAP})"
        )
    raw += d24_house_support_raw

    # GAP-FIX (2026-07-22j, audit gap 6; corrected 2026-07-22l): dispositor +
    # combustion affliction check on the D24 lagna/5th/9th lords -- a lord
    # "confirmed" placed in a favourable D24 house is a weaker signal if
    # that same lord is itself combust (D1 combustion carries into every
    # divisional chart the planet participates in) or if its D24 dispositor
    # (the lord of the D24 sign it actually sits in) is severely debilitated
    # there. This is a bounded DISCOUNT on the role-placement credit that
    # lord already earned above (up to 50% of what that role ACTUALLY
    # contributed), not an independent new penalty channel piled on top of
    # unrelated positives.
    # GAP-FIX (2026-07-22l, CONFIRMED real bug, caught auditing a Ramsunder
    # report): the discount used to be 50% of the role's CONFIGURED base
    # weight (_D24_ROLE_WEIGHTS[role], e.g. 5.0), not 50% of what that role
    # actually earned after house-weighting (role_earned_contribution[role],
    # e.g. 5.0*0.45=2.25) -- so whenever house_weight < 1.0 (the normal
    # case), a "50% discount" could exceed 100% of the lord's own earned
    # credit and bleed into the section's unrelated components (here, it ate
    # through Commerce's d24_h5_lord=Mercury's own +2.25 AND part of the
    # separate D24 house_support total). Fixed to discount 50% of the
    # role_earned_contribution actually recorded above, so the discount can
    # never exceed what that specific role contributed.
    combust_planets = set(getattr(payload, "combust_planets", []) or [])
    in_house_d24_signs = compute_d24_chart(getattr(payload, "planets_d1", {}) or {})
    affliction_notes: List[str] = []
    affliction_discount_total = 0.0
    for role, planet in role_planets.items():
        if not planet or planet in mismatches or planet not in in_house_d24_signs:
            continue
        d24_sign = in_house_d24_signs[planet]
        dispositor = _SIGN_LORD.get(d24_sign, "")
        dispositor_dignity = d24_dignities.get(dispositor, "") if dispositor else ""
        is_combust = planet in combust_planets
        is_dispositor_debilitated = dispositor_dignity == "DEBILITATED"
        if is_combust or is_dispositor_debilitated:
            earned = role_earned_contribution.get(role, 0.0)
            suppress_amount = earned * 0.5
            if suppress_amount <= 0.0:
                continue
            affliction_discount_total += suppress_amount
            reason = []
            if is_combust:
                reason.append(f"{planet} is combust in D1 (carries into D24)")
            if is_dispositor_debilitated:
                reason.append(f"D24 dispositor {dispositor} is debilitated in D24")
            affliction_notes.append(
                f"{role}={planet} affliction check: {'; '.join(reason)} -- "
                f"role-placement credit discounted by {suppress_amount:.2f} "
                f"(50% of the +{earned:.2f} this role actually earned, not its base weight)"
            )
    # GAP-FIX (2026-07-24, explicit user request -- "cancellation"): a role
    # lord afflicted in D24 (combust, or sitting in a sign whose dispositor
    # is debilitated there) is a weaker signal, but classical technique
    # (neecha-bhanga and its analogues) recognises that a planet strong in
    # its OWN D1 nature -- exalted or in its own sign natally -- carries
    # enough independent strength that a derivative-chart affliction should
    # not be read at full weight. This does not erase the affliction (it is
    # still real for D24-specific purposes) but halves the discount already
    # computed above when the afflicted role planet is D1-exalted or D1-own-
    # sign, using the unmutated true_planet_dignities map (not the
    # Parivartana-stomped planet_dignities -- see engine_io.py's own
    # true_planet_dignities comment for why that distinction matters).
    true_d1_dignities = getattr(payload, "true_planet_dignities", {}) or {}
    if affliction_discount_total > 0:
        cancelled_notes: List[str] = []
        for role, planet in role_planets.items():
            if not planet or planet in mismatches:
                continue
            d1_dignity = true_d1_dignities.get(planet, "")
            if d1_dignity in ("EXALTED", "OWN"):
                # Recover half of whatever this role's own affliction note
                # discounted -- approximate per-role reversal, bounded so it
                # can never push raw back above what the role loop + dignity
                # + house-support blocks already established before the
                # affliction pass.
                earned = role_earned_contribution.get(role, 0.0)
                had_afflicted = any(f"{role}={planet} affliction check" in n for n in affliction_notes)
                if had_afflicted and earned > 0:
                    cancellation_amount = earned * 0.25
                    raw = min(raw + cancellation_amount, raw + affliction_discount_total)
                    cancelled_notes.append(
                        f"{role}={planet} affliction PARTIALLY CANCELLED: {planet} is "
                        f"{d1_dignity} in D1 (natal strength offsets half of the D24-derived "
                        f"affliction) -- +{cancellation_amount:.2f} restored."
                    )
        if cancelled_notes:
            matches.extend(cancelled_notes)

    if affliction_discount_total > 0:
        raw = max(0.0, raw - affliction_discount_total)
        matches.extend(affliction_notes)

    # GAP-FIX (2026-07-24, explicit user request, item #3): the block above
    # only ever looked at D1 combustion carrying in, or the role lord's D24
    # DISPOSITOR being debilitated -- it never checked the role lord's OWN
    # D24 dignity, its retrograde state, or its functional nature for this
    # lagna. Those are added here as a separate, small, explicitly-capped
    # negative channel (kept apart from the role-earned-contribution discount
    # above so a role with zero earned contribution -- e.g. placed outside
    # the stream's houses -- can still register this as a real, if muted,
    # negative signal rather than silently doing nothing).
    retrograde_planets = set(getattr(payload, "retrograde_planets", set()) or set())
    self_affliction_raw = 0.0
    self_affliction_notes: List[str] = []
    for role, planet in role_planets.items():
        if not planet or planet in mismatches:
            continue
        own_d24_dignity = d24_dignities.get(planet, "")
        reasons = []
        amount = 0.0
        if own_d24_dignity == "DEBILITATED":
            reasons.append(f"{planet} is itself DEBILITATED in D24")
            amount += 1.25
        if planet in retrograde_planets:
            reasons.append(f"{planet} is retrograde (weakens direct-expression educational signification)")
            amount += 0.5
        if functional_nature.get(planet) == "FUNCTIONAL_MALEFIC":
            reasons.append(f"{planet} is a functional malefic for this Lagna (rules only dusthana houses)")
            amount += 0.75
        if reasons:
            self_affliction_raw += amount
            self_affliction_notes.append(
                f"{role}={planet} D24 self-affliction check: {'; '.join(reasons)} -> -{amount:.2f}"
            )
    self_affliction_raw = min(_D24_SELF_AFFLICTION_CAP, self_affliction_raw)
    if self_affliction_raw > 0:
        raw = max(0.0, raw - self_affliction_raw)
        matches.extend(self_affliction_notes)
        matches.append(
            f"D24 self-affliction total for {meta['label']}: -{self_affliction_raw:.2f} "
            f"(capped at {_D24_SELF_AFFLICTION_CAP}; distinct from the D1-combustion/"
            f"dispositor-debilitation discount above -- this is the role lord's own D24 "
            f"weakness, not an inherited one)"
        )

    # GAP-FIX (2026-07-24, explicit user request -- "dispositors"): for each
    # matched role lord, check its D24 dispositor's OWN placement -- if the
    # dispositor (the lord of the D24 sign the role planet sits in) is
    # itself also placed in one of this stream's D24 houses, that is a
    # corroborating "chain" signal (the rulership chain doubles back into
    # the stream's own territory), distinct from the dispositor-debilitation
    # check already used above as a negative/affliction signal.
    # GAP-FIX (2026-07-24, explicit user request, item #7): the chain above
    # only ever REWARDED a dispositor that lands well -- it never penalized a
    # role lord whose dispositor is itself weak. A planet "confirmed"
    # placed in a favourable D24 house is a materially weaker signal if the
    # sign-lord it depends on for that placement's own strength is
    # debilitated or functionally malefic for this Lagna -- classically, a
    # planet's placement is only as strong as the house/sign it depends on.
    # This is a separate small discount on the role's earned contribution
    # (bounded like the existing combustion/dispositor-debilitation discount
    # above), not a duplicate of it -- that block checks the dispositor's D24
    # DIGNITY only; this checks the dispositor's OWN D24 house-placement
    # relevance and functional nature, a different failure mode (a
    # dispositor can be dignified yet functionally malefic, or undignified
    # yet still land in the stream's houses).
    dispositor_notes: List[str] = []
    dispositor_raw = 0.0
    dispositor_drag_notes: List[str] = []
    dispositor_drag_total = 0.0
    for role, planet in role_planets.items():
        if not planet or planet in mismatches or planet not in in_house_d24_signs:
            continue
        if d24_planet_house.get(planet) not in houses:
            continue  # only chase the dispositor chain for roles already confirmed placed
        d24_sign = in_house_d24_signs[planet]
        dispositor = _SIGN_LORD.get(d24_sign, "")
        if not dispositor or dispositor == planet:
            continue  # planet in its own D24 sign -- already reflected in dignity, not a separate chain
        dispositor_house = d24_planet_house.get(dispositor)
        if dispositor_house in houses:
            w = d24_learning_weight(dispositor_house)
            contribution = 1.5 * w
            dispositor_raw += contribution
            d24_planets_credited.add(dispositor)
            dispositor_notes.append(
                f"{role}={planet}'s D24 dispositor {dispositor} (lord of {d24_sign}) is ALSO "
                f"placed in D24 house {dispositor_house} ({meta['label']}'s territory) -- "
                f"dispositor chain confirms -> +{contribution:.2f}"
            )
        dispositor_own_dignity = d24_dignities.get(dispositor, "")
        dispositor_functional = functional_nature.get(dispositor, "NEUTRAL")
        drag_reasons = []
        if dispositor_own_dignity == "DEBILITATED":
            drag_reasons.append(f"dispositor {dispositor} is itself DEBILITATED in D24")
        if dispositor_functional == "FUNCTIONAL_MALEFIC":
            drag_reasons.append(f"dispositor {dispositor} is a functional malefic for this Lagna")
        if drag_reasons:
            earned = role_earned_contribution.get(role, 0.0)
            drag_amount = max(0.3, earned * 0.3)  # floor so a weak dispositor still registers even if earned==0
            dispositor_drag_total += drag_amount
            dispositor_drag_notes.append(
                f"{role}={planet} weak-dispositor drag: {'; '.join(drag_reasons)} -- "
                f"this role's apparent strength depends on a weak dispositor -> -{drag_amount:.2f}"
            )
    dispositor_raw = min(_D24_DISPOSITOR_CAP, dispositor_raw)
    if dispositor_raw > 0:
        matches.extend(dispositor_notes)
        matches.append(f"D24 dispositor-chain total for {meta['label']}: +{dispositor_raw:.2f} (capped at {_D24_DISPOSITOR_CAP})")
    raw += dispositor_raw
    dispositor_drag_total = min(_D24_DISPOSITOR_CAP, dispositor_drag_total)
    if dispositor_drag_total > 0:
        raw = max(0.0, raw - dispositor_drag_total)
        matches.extend(dispositor_drag_notes)
        matches.append(
            f"D24 weak-dispositor drag total for {meta['label']}: -{dispositor_drag_total:.2f} "
            f"(capped at {_D24_DISPOSITOR_CAP})"
        )

    # GAP-FIX (2026-07-24, explicit user request -- "aspects, conjunctions"):
    # same relational pattern already used in _relational_d1_section, applied
    # here in D24 house-space to the D24 role lords themselves (lagna/4/5/9/10
    # lords) -- do any two of them sit together (conjunction) or aspect each
    # other within the D24 chart? A connected set of educational-role lords
    # in D24 is a corroborating signal distinct from any one of them being
    # individually placed in the stream's houses.
    relational_raw = 0.0
    relational_notes: List[str] = []
    if d24_planet_house:
        d24_aspects = _get_planetary_aspects(d24_planet_house)
        seen_d24_pairs = set()
        role_items = [(r, p) for r, p in role_planets.items() if p and p not in mismatches]
        for i in range(len(role_items)):
            for j in range(i + 1, len(role_items)):
                role_a, planet_a = role_items[i]
                role_b, planet_b = role_items[j]
                if planet_a == planet_b:
                    continue
                pair_key = tuple(sorted((planet_a, planet_b)))
                if pair_key in seen_d24_pairs:
                    continue
                house_a = d24_planet_house.get(planet_a)
                house_b = d24_planet_house.get(planet_b)
                conjunct = house_a is not None and house_a == house_b
                aspecting = (house_b in d24_aspects.get(planet_a, [])) or (house_a in d24_aspects.get(planet_b, []))
                if not (conjunct or aspecting):
                    continue
                # GAP-FIX (2026-07-24, real-bug fix caught re-auditing this
                # section): this block used to credit ANY conjunction/aspect
                # between two role lords regardless of whether either lord
                # actually sits in THIS stream's D24 houses -- so two role
                # lords conjunct in a house irrelevant to this stream (e.g.
                # H11 for Science, whose houses are [3,5,6,8,9]) still
                # produced positive "D24 confirmation" evidence for Science
                # out of thin air. That contradicts this module's own design
                # intent (corroborating signal, "not independent proof" --
                # see _D24_RELATIONAL_CAP's comment) and broke the neutral-
                # signal guarantee role_placement/dignity above rely on when
                # no educational lord matched this stream at all. Now
                # requires at least one of the two connected lords to
                # already be placed in this stream's own D24 houses --
                # the connection can only CORROBORATE an existing signal,
                # never manufacture one where neither lord supports the
                # stream at all.
                if not ({house_a, house_b} - {None}) & set(houses):
                    continue
                seen_d24_pairs.add(pair_key)
                relation = "conjunction" if conjunct else "aspect"
                excl_a = _planet_exclusivity(planet_a) if planet_a in stream_planets else 0.6
                excl_b = _planet_exclusivity(planet_b) if planet_b in stream_planets else 0.6
                exclusivity = max(excl_a, excl_b)
                contribution = 1.5 * exclusivity
                relational_raw += contribution
                relational_notes.append(
                    f"D24 {role_a}={planet_a} (H{house_a}) <-{relation}-> D24 {role_b}={planet_b} "
                    f"(H{house_b}) -- role-lord connection in Siddhamsha (exclusivity "
                    f"{exclusivity:.2f} -> +{contribution:.2f})"
                )
    # GAP-FIX (2026-07-24, explicit user request, item #2): the block above
    # only checked role-lord <-> role-lord connections; it never checked
    # whether a D24 role lord connects (by conjunction or aspect) to this
    # stream's own D1 SIGNATURE planets that aren't themselves a role lord --
    # e.g. the D24 5th lord aspecting the stream's Mercury even though
    # Mercury isn't the lagna/4/5/9/10 lord. Same relational mechanics,
    # scoped to role-lord-to-signature-planet pairs only (signature-to-
    # signature pairs are intentionally excluded here -- that would start
    # re-deriving D24 house-support/dignity evidence already scored above
    # through a third channel).
    if d24_planet_house:
        d24_aspects = _get_planetary_aspects(d24_planet_house)
        role_planet_set = {p for p in role_planets.values() if p and p not in mismatches}
        signature_only = [p for p in stream_planets if p not in role_planet_set]
        seen_sig_pairs = set()
        for role_a, planet_a in [(r, p) for r, p in role_planets.items() if p and p not in mismatches]:
            for planet_b in signature_only:
                if planet_a == planet_b:
                    continue
                pair_key = (planet_a, planet_b)
                if pair_key in seen_sig_pairs:
                    continue
                house_a = d24_planet_house.get(planet_a)
                house_b = d24_planet_house.get(planet_b)
                conjunct = house_a is not None and house_a == house_b
                aspecting = (house_b in d24_aspects.get(planet_a, [])) or (house_a in d24_aspects.get(planet_b, []))
                if not (conjunct or aspecting):
                    continue
                # GAP-FIX (2026-07-24, same real-bug fix as the role-lord
                # <-> role-lord block above): require at least one side of
                # the connection to already be placed in this stream's own
                # D24 houses, so a role lord/signature-planet pair sitting
                # together in a house irrelevant to this stream cannot
                # manufacture "D24 confirmation" evidence on its own.
                if not ({house_a, house_b} - {None}) & set(houses):
                    continue
                seen_sig_pairs.add(pair_key)
                relation = "conjunction" if conjunct else "aspect"
                exclusivity = _planet_exclusivity(planet_b)
                contribution = 1.0 * exclusivity
                relational_raw += contribution
                relational_notes.append(
                    f"D24 {role_a}={planet_a} (H{house_a}) <-{relation}-> {meta['label']} signature "
                    f"planet {planet_b} (H{house_b}) -- role-lord/signature-planet connection in "
                    f"Siddhamsha (exclusivity {exclusivity:.2f} -> +{contribution:.2f})"
                )
    relational_raw = min(_D24_RELATIONAL_CAP, relational_raw)
    if relational_raw > 0:
        matches.extend(relational_notes)
        matches.append(f"D24 role-lord aspect/conjunction total for {meta['label']}: +{relational_raw:.2f} (capped at {_D24_RELATIONAL_CAP})")
    raw += relational_raw

    # GAP-FIX (2026-07-22g, audit gap 7): a raw score of 0 here can mean two
    # very different things, and the report previously collapsed them into
    # the same "no match" text -- (a) the D24 lords genuinely are NOT placed
    # in this stream's houses (a real, if weak, non-confirmation), vs (b)
    # this section's own house-membership template just didn't happen to
    # recognise a pattern that a fuller D24 reading (subject-specific houses,
    # aspects, dispositors -- explicitly out of scope for this bounded
    # section, see the note below) might have credited. Callers must not read
    # "no match" as "D24 rejects this stream" -- it means "this narrow
    # section found nothing to add," which is a statement about the
    # section's own coverage, not a contradiction verdict.
    signal_state = "POSITIVE_SUPPORT" if raw > 0 else "NEUTRAL_NO_SIGNAL"
    if mismatches:
        signal_state = "D24_CONSTRUCTION_MISMATCH_PARTIAL" if raw > 0 else "D24_CONSTRUCTION_MISMATCH"
    return {
        "raw": raw,
        "matches": matches,
        "data_status": "COMPUTED",
        "signal_state": signal_state,
        "d24_construction_mismatches": mismatches,
        "planets_credited": d24_planets_credited,
        "note": (
            "D24 (Siddhamsha) confirmation -- D24 lagna/4th/5th/9th/10th lord "
            "placement in this stream's houses (D24 house-space) + average D24 "
            "dignity of confirmed role planets + this stream's own D1 signature "
            "planets' D24 house-support + dispositor-chain confirmation (does each "
            "role lord's D24 dispositor also land in the stream's territory) + "
            "aspect/conjunction connections among the D24 role lords themselves + "
            "an affliction/cancellation pass (D1 combustion / D24-dispositor "
            "debilitation discounts a role's earned credit, partially reversed if "
            "that role planet is D1-exalted or D1-own-sign). Still NOT a complete "
            "classical D24 methodology (no subject-specific house ontology beyond "
            "lagna/4/5/9/10, no varga-strength/Shadbala-style weighting of the "
            "dispositor chain) -- a materially fuller, but still bounded, additive "
            "confirmation. IMPORTANT: "
            "signal_state=NEUTRAL_NO_SIGNAL means this narrow section found no "
            "recognised pattern, NOT that D24 astrologically rejects this stream -- "
            "treat 0 here as 'no additional confirmation available', never as "
            "a contradiction. "
            + (
                f"D24_CONSTRUCTION_MISMATCH (audit gaps 4/5): in-house Chaturvimshamsha "
                f"recompute (compute_d24_chart, BPHS majority convention) disagrees with "
                f"upstream D24 data for: {', '.join(sorted(mismatches))} -- these planets "
                f"were EXCLUDED from this section's role-placement and dignity evidence "
                f"rather than trusted either way. D24 Lagna itself could not be "
                f"independently re-derived (no lagna_degree field on this payload), so it "
                f"remains UNVERIFIABLE, not confirmed."
                if mismatches else
                "In-house D24 planet-sign recompute agrees with upstream data for every "
                "planet checked (D24 Lagna itself remains UNVERIFIABLE -- no lagna_degree "
                "field available to independently re-derive it)."
            )
        ),
    }


# GAP-FIX (2026-07-22h, audit gap 16): subject_evidence is built from
# per-subject scores that are THEMSELVES a weighted function of the same
# planet_strengths already scored directly in planetary_strength -- so a
# stream whose subjects' planet signatures closely mirror its own
# stream-level planet-weight table is partly re-counting one testimony
# twice, not adding independent evidence. This does not eliminate the
# correlation (the subjects genuinely ARE astrologically tied to the
# stream's planets -- that's not a bug, it's the domain), but it discounts
# subject_evidence's contribution in proportion to how closely the core
# subjects actually used echo the stream's own planet-weight vector,
# following the same idea as Field_Determination's
# correlation_discount_factor (field_methods/common.py) applied to
# cross-method convergence there.
def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    keys = set(vec_a) | set(vec_b)
    if not keys:
        return 0.0
    dot = sum(vec_a.get(k, 0.0) * vec_b.get(k, 0.0) for k in keys)
    norm_a = sum(v * v for v in vec_a.values()) ** 0.5
    norm_b = sum(v * v for v in vec_b.values()) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


_SUBJECT_EVIDENCE_MAX_CIRCULARITY_DISCOUNT = 0.40


def _subject_evidence_circularity_discount(meta: Dict[str, Any], used_subjects: List[Dict[str, Any]]) -> float:
    """Returns a multiplier in [1 - MAX_DISCOUNT, 1.0]; 1.0 means the used
    subjects' planetary signature is essentially unrelated to the stream's
    own planet-weight vector (independent evidence, no discount); the floor
    means it's nearly identical (heavily circular, discounted toward the cap)."""
    if not used_subjects:
        return 1.0
    combined: Dict[str, float] = {}
    for s in used_subjects:
        for p, w in (s.get("_planet_weights") or {}).items():
            combined[p] = combined.get(p, 0.0) + w
    if not combined:
        return 1.0
    overlap = _cosine_similarity(meta["planets"], combined)
    return 1.0 - _SUBJECT_EVIDENCE_MAX_CIRCULARITY_DISCOUNT * overlap


def _subject_evidence_section(stream_id: str, subjects_ranked: List[Dict[str, Any]], meta: Dict[str, Any]) -> Dict[str, Any]:
    """Fold subject-level evidence into a bounded rubric section, so the
    dominant-stream decision cannot rest on the stream's signature
    planets/houses alone while ignoring what the stream's own subject
    scores say.

    GAP-FIX (2026-07-22, audit gap 12/13): a stream's "core average" is no
    longer a flat average across every core subject regardless of whether
    a real student would ever combine them:
      - Science: scores every named feasible bundle (PCM/PCB/PCMB from
        SCIENCE_SUBJECT_BUNDLES) and uses whichever bundle is strongest,
        reporting which one -- a clear PCM chart is no longer diluted by a
        weak Biology score it would never actually need.
       - Humanities: a real student picks a SUBSET of the (many) core
         options, not all of them -- uses the average of the best 3 core
         subjects, matching the three-subject decision breadth used by the
         other streams after selection adjustment.
      - Commerce: only 3 fixed core subjects exist (Accountancy, Business
        Studies, Economics) -- averaging all 3 remains the correct model,
        there is no smaller "bundle" concept for Commerce's core.

    GAP-FIX (2026-07-22, audit gap 14): electives flagged shared_elective
    (offered identically across multiple streams, e.g. Physical Education)
    are excluded from the "best elective" pick -- a subject that cannot
    distinguish between streams should not be allowed to decide between them.
    """
    core = [s for s in subjects_ranked if s.get("core")]
    non_shared_electives = [s for s in subjects_ranked if not s.get("core") and not s.get("shared_elective")]

    bundle_note = ""
    all_core_avg = sum(s["score"] for s in core) / len(core) if core else 0.0
    used_core_subjects: List[Dict[str, Any]] = []
    if stream_id == "science" and core:
        by_id = {s["subject_id"]: s for s in core}
        bundle_scores = []
        for bundle_name, member_ids in SCIENCE_SUBJECT_BUNDLES.items():
            members = [by_id[mid] for mid in member_ids if mid in by_id]
            if len(members) == len(member_ids):
                bundle_scores.append((bundle_name, sum(m["score"] for m in members) / len(members), members))
        if bundle_scores:
            best_bundle_name, selected_core_avg, best_members = max(bundle_scores, key=lambda x: x[1])
            # Shrink the best-of-bundles result toward the complete core mean.
            # This preserves real PCM/PCB choice without giving Science a free
            # multiple-comparisons advantage over Commerce's fixed bundle.
            core_avg = all_core_avg + 0.50 * (selected_core_avg - all_core_avg)
            core_labels = [m["label"] for m in best_members]
            used_core_subjects = best_members
            bundle_note = (f"best-fit bundle {best_bundle_name}, selection-adjusted "
                           f"from {selected_core_avg:.1f} toward all-core mean {all_core_avg:.1f}")
        else:
            core_avg = sum(s["score"] for s in core) / len(core)
            core_labels = [s["label"] for s in core]
            used_core_subjects = core
            bundle_note = "no complete named bundle available -- fell back to all-core average"
    elif stream_id == "humanities" and core:
        # Use the same three-subject decision breadth as Science's PCM/PCB
        # bundles and Commerce's three fixed cores. Selecting four of six
        # Humanities cores gave that stream a structural multiple-choice
        # advantage unrelated to chart evidence.
        top_subset = sorted(core, key=lambda s: -s["score"])[: min(3, len(core))]
        selected_core_avg = sum(s["score"] for s in top_subset) / len(top_subset)
        core_avg = all_core_avg + 0.50 * (selected_core_avg - all_core_avg)
        core_labels = [s["label"] for s in top_subset]
        used_core_subjects = top_subset
        bundle_note = (f"best {len(top_subset)}-of-{len(core)} core subset, selection-adjusted "
                       f"from {selected_core_avg:.1f} toward all-core mean {all_core_avg:.1f}")
    elif core:
        core_avg = sum(s["score"] for s in core) / len(core)
        core_labels = [s["label"] for s in core]
        used_core_subjects = core
        bundle_note = "all core subjects (fixed, small core list)"
    else:
        core_avg = 0.0
        core_labels = []
        bundle_note = "no core subjects configured"

    # Use breadth across all distinguishing electives. A raw maximum rewards
    # registries with more options even when the chart is no better suited.
    best_elective_row = max(non_shared_electives, key=lambda s: s["score"], default=None)
    best_elective = (
        sum(s["score"] for s in non_shared_electives) / len(non_shared_electives)
        if non_shared_electives else 0.0
    )
    best_elective_label = (
        f"breadth average of {len(non_shared_electives)} electives"
        if non_shared_electives else ""
    )

    # GAP-FIX (2026-07-22h, audit gap 16): discount both components by how
    # circular the USED subjects' planetary signature is relative to this
    # stream's own planet-weight vector (see
    # _subject_evidence_circularity_discount) -- a stream whose core
    # subjects are basically a restatement of its own signature planets gets
    # less net credit here than one whose subjects bring genuinely
    # additional (if correlated-by-domain) testimony.
    core_discount = _subject_evidence_circularity_discount(meta, used_core_subjects)
    elective_discount = _subject_evidence_circularity_discount(meta, non_shared_electives)

    # GAP-FIX (2026-07-22e): section cap reduced 22->18 to make room for the
    # new relational_d1/jaimini_apparatus sections; core/elective sub-weights
    # scaled down in the same proportion (15->12.27, 7->5.73) so the internal
    # core-vs-elective balance is unchanged.
    # GAP-FIX (2026-07-22j): cap reduced again 18->14 to make room for the
    # expanded d24_confirmation/jaimini_apparatus sections (audit gaps 6/8/15);
    # sub-weights scaled proportionally again (12.27->9.55, 5.73->4.46).
    core_component_raw = (core_avg / 100.0) * 13.64 * core_discount
    elective_component_raw = (best_elective / 100.0) * 6.36 * elective_discount
    raw = core_component_raw + elective_component_raw

    return rubric_section(
        "subject_evidence", raw, 20.0,
        note=(
            f"Core-subject evidence ({bundle_note}): {core_avg:.1f}/100 across "
            f"{', '.join(core_labels) if core_labels else 'none'} (circularity discount "
            f"{core_discount:.2f}x -- lower means these subjects' planet signature closely "
            f"echoes this stream's own planet-weight table, audit gap 16). Non-shared "
            f"elective evidence: {best_elective_label or 'none'} at {best_elective:.1f}/100 "
            f"(discount {elective_discount:.2f}x; shared_elective subjects excluded from "
            f"this pick per audit gap 14)."
        ),
    )


# GAP-FIX (2026-07-22e, audit gap 7): relational D1 analysis -- the engine
# previously only ever looked at a planet's OWN strength/house placement in
# isolation. Classical Parashari practice puts real weight on whether the
# chart's own education-authority lords (5th=vidya, 9th=higher
# learning/dharma, 10th=career/karma) are actually CONNECTED to each other
# (conjunction or mutual/one-way Parashari aspect) -- an unconnected set of
# lords scattered with no relationship carries much weaker educational
# promise than the same three lords linked by aspect or conjunction, even at
# identical individual planetary strength. This is a first version: it only
# asks "are these lords connected, and if so, is that connection relevant to
# THIS stream" (one of the connected planets is a stream signature planet or
# sits in a stream house) -- not a full aspect-quality/benefic-malefic
# analysis, which is out of scope for this pass.
_RELATIONAL_D1_PAIR_WEIGHT = 4.0


def _relational_d1_section(payload: Any, stream_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    stream_planets = set(meta["planets"].keys())
    houses: List[int] = meta["houses"]

    edu_lords = {
        "h5_lord": house_lords.get("5", "") or "",
        "h9_lord": house_lords.get("9", "") or "",
        "h10_lord": getattr(payload, "h10_lord", "") or house_lords.get("10", "") or "",
    }
    known = {role: p for role, p in edu_lords.items() if p}
    if len(known) < 2:
        return {
            "raw": 0.0, "matches": [],
            "data_status": "MISSING" if not known else "PARTIAL",
            "note": "Fewer than two of the 5th/9th/10th lords are available -- cannot assess connections.",
        }

    if not planet_house:
        return {"raw": 0.0, "matches": [], "data_status": "MISSING",
                "note": "planet_house not available -- cannot assess aspect/conjunction connections."}

    aspects = _get_planetary_aspects(planet_house)
    raw = 0.0
    matches: List[str] = []
    seen_pairs = set()
    # GAP-FIX (2026-07-24, item #8/#9, correlation discount): planets that
    # earned credit in this section -- consumed by score_stream to build the
    # cross-section correlation discount.
    relational_planets_credited: set = set()
    roles = list(known.items())
    for i in range(len(roles)):
        for j in range(i + 1, len(roles)):
            role_a, planet_a = roles[i]
            role_b, planet_b = roles[j]
            if planet_a == planet_b:
                continue  # same planet holding two roles is already scored via role_placement
            pair_key = tuple(sorted((planet_a, planet_b)))
            if pair_key in seen_pairs:
                continue
            house_a = planet_house.get(planet_a)
            house_b = planet_house.get(planet_b)
            conjunct = house_a is not None and house_a == house_b
            aspecting = (house_b in aspects.get(planet_a, [])) or (house_a in aspects.get(planet_b, []))
            if not (conjunct or aspecting):
                continue
            relevant = (
                planet_a in stream_planets or planet_b in stream_planets or
                house_a in houses or house_b in houses
            )
            if not relevant:
                continue
            seen_pairs.add(pair_key)
            relation = "conjunction" if conjunct else "aspect"
            # GAP-FIX (2026-07-22g, audit gap 10, CONFIRMED live on Samyuhtha/
            # Ananyaa/Ramsunder): the SAME 5th/9th/10th-lord connection was
            # being credited at full weight to every stream whose signature-
            # planet list happened to contain one of the two planets (Mercury,
            # Jupiter, Sun etc. sit on 2+ streams' lists) -- so one underlying
            # D1 fact ("these lords are connected") was being read as if it
            # were separate, stream-specific testimony for Humanities AND
            # Science AND Commerce simultaneously. Scaled here by the
            # qualifying planet's cross-stream exclusivity (1.0 if it's on
            # only this stream's list, 0.5 if shared by two streams' lists,
            # 0.33 if shared by all three) -- a genuinely stream-exclusive
            # connection still earns full credit; a generic one is discounted
            # in proportion to how many streams could equally claim it.
            excl_a = _planet_exclusivity(planet_a) if planet_a in stream_planets else 0.0
            excl_b = _planet_exclusivity(planet_b) if planet_b in stream_planets else 0.0
            house_only = house_a in houses or house_b in houses
            exclusivity = max(excl_a, excl_b) if (excl_a or excl_b) else (0.6 if house_only else 1.0)
            contribution = _RELATIONAL_D1_PAIR_WEIGHT * exclusivity
            raw += contribution
            if planet_a in stream_planets:
                relational_planets_credited.add(planet_a)
            if planet_b in stream_planets:
                relational_planets_credited.add(planet_b)
            matches.append(
                f"{role_a}={planet_a} (H{house_a}) <-{relation}-> {role_b}={planet_b} (H{house_b}) "
                f"-- relevant to {meta['label']} (exclusivity {exclusivity:.2f} -> +{contribution:.2f})"
            )

    # GAP-FIX (audit #62): same POSITIVE_SUPPORT/NEUTRAL_NO_SIGNAL convention
    # as d24_confirmation/role_placement -- "no relevant connection found"
    # is a neutral absence of evidence, not a contradiction (contraindications
    # is the only section with an actual negative branch).
    signal_state = "POSITIVE_SUPPORT" if raw > 0 else "NEUTRAL_NO_SIGNAL"
    return {
        "raw": raw,
        "matches": matches,
        "data_status": "COMPLETE" if len(known) == 3 else "PARTIAL",
        "signal_state": signal_state,
        "planets_credited": relational_planets_credited,
        "note": (
            "D1 relational check: conjunction/Parashari-aspect connections between the "
            "5th/9th/10th lords, counted only where at least one end is this stream's "
            "own signature planet or house. First-pass -- does not yet weigh aspect "
            "strength (Drishti Bala) or benefic/malefic quality."
        ),
    }


# GAP-FIX (2026-07-22e, audit gap 8): first-pass Jaimini apparatus, reusing
# fields already computed elsewhere in the codebase (payload.karakamsha,
# payload.arudha_lagna, payload.a10_sign) and the same argala/virodhargala
# helpers Field_Determination/field_methods/jaimini.py already uses -- not a
# re-derivation of Jaimini math, just a stream-scoped confirmation layer on
# top of it. Deliberately narrow: sign-lord-of-karakamsha/arudha/A10 alignment
# with the stream's signature planets, plus surviving (post-Virodhargala)
# argala on the 10th house (career) from stream-aligned planets. NOT a full
# Jaimini reading (no chara-dasha, no raja-yoga detection, no karaka-role
# weighting beyond what's already in payload) -- see conversation scope note.
# GAP-FIX (2026-07-22g, audit gaps 12/14): Karakamsha (soul-level Jaimini
# testimony) keeps the highest weight; Arudha Lagna/A10 (public-image/
# career-manifestation significators) are lowered relative to it -- the
# audit's point that AL/A10 are secondary, career-image indicators and
# shouldn't carry equal weight to Karakamsha for an under-15 STREAM decision
# (as opposed to a later career/vocation decision, where they'd matter more).
_JAIMINI_KARAKAMSHA_WEIGHT = 4.5
_JAIMINI_ARUDHA_WEIGHT = 2.0
_JAIMINI_A10_WEIGHT = 2.0
_JAIMINI_ARGALA_WEIGHT = 2.0
_JAIMINI_ARGALA_MAX_PLANETS = 2
# GAP-FIX (2026-07-22i, audit gap 13): the audit's own list of what a
# complete Jaimini reading needs explicitly names chara-dasha alongside
# karakamsha/argala/AK-AmK -- this reuses the SAME
# _get_active_chara_dasha_sign already trusted elsewhere in this codebase
# (Field_Determination/field_methods/jaimini.py's own T1-C chara-dasha
# signal), rather than re-deriving chara-dasha math from scratch. Kept at a
# modest weight: for an under-15 chart, the currently-active chara dasha is
# a WEAKER signal than it would be for an adult career decision (a school-
# age child's active dasha lord says less about their own aptitude and more
# about the general life-period the family is in) -- see the note in the
# section's own trace text.
_JAIMINI_CHARA_DASHA_WEIGHT = 1.5
# GAP-FIX (2026-07-22j, audit gap 8): karakamsha occupants and 5th/9th/10th-
# from-karakamsha lords, and (below) AK/AmK raja-yoga -- the audit's own
# list of what's missing from a "merely ruler-membership" Jaimini apparatus.
_JAIMINI_KARAKAMSHA_OCCUPANT_WEIGHT = 2.5
_JAIMINI_KARAKAMSHA_HOUSE_WEIGHT = 1.5
_JAIMINI_RAJYOGA_WEIGHT = 2.5

# GAP-FIX (2026-07-22k, "port jaimini.py logic here"): the three pieces
# explicitly named as not-yet-ported -- Upapada Lagna, Karakamsha's own
# rasi-drishti onto the D1 lagna, and the AK/AmK-weighted chara-karaka
# house-distance/drishti matrix -- ported from
# Field_Determination/field_methods/jaimini.py's score_jaimini(), adapted
# from that function's field_affinity-weighted design (0..1 per field) to
# this engine's stream-weighted design (each stream's meta['planets'] dict
# IS this engine's affinity table -- a planet at weight 0.30 for Science is
# structurally the same kind of number jaimini.py's field_affinity[planet]
# was).
_JAIMINI_UPAPADA_WEIGHT = 2.0
_JAIMINI_KARAKAMSHA_LAGNA_DRISHTI_WEIGHT = 2.0
# Karaka matrix: mirrors jaimini.py's karaka_weights/house_modifier/drishti_boost
# tiers exactly, scaled down for this engine's smaller stream-planet-weight
# range (jaimini.py's field_affinity commonly runs 0.05-0.40; this engine's
# per-stream planet weights run in roughly the same 0.15-0.35 band, so the
# same x10 scalar jaimini.py uses would be reasonable here too, but is
# instead set lower (x4) since this section's cap (16) is much smaller than
# jaimini.py's own 105-point full-method ceiling).
_JAIMINI_KARAKA_WEIGHTS: Dict[str, float] = {"AmK": 2.0, "AK": 1.6}
_JAIMINI_MATRIX_SCALE = 4.0
_JAIMINI_MATRIX_CAP = 6.0
# GAP-FIX (2026-07-22l, CONFIRMED live on a Ramsunder report): jaimini_apparatus's
# section cap (16.0, see score_stream) was being enforced by a hard clip
# AFTER summing every component's raw contribution -- but the components are
# scaled by each qualifying planet's cross-stream EXCLUSIVITY (see
# _planet_exclusivity), so a chart whose Karakamsha sign-lord happens to be
# exclusive to one stream (exclusivity=1.0) stacks up much larger individual
# contributions than a chart whose Karakamsha lord is shared across streams
# (each contribution proportionally smaller) -- even at genuinely equal
# underlying Jaimini strength. The exclusive-lord chart then hits the hard
# cap and loses real signal (observed: 19.5 raw hard-clipped to 16.0, a flat
# -3.5), while the shared-lord chart never approaches the cap at all. A flat
# post-hoc clip treats "just over the cap" and "far over the cap" identically
# once truncated, which amplifies that unfairness. Soft-compressing the
# total above 75% of the cap (same tanh-toward-ceiling shape clamp_score
# already uses elsewhere in this codebase) doesn't eliminate the underlying
# tension -- a cap is still a cap -- but it makes the falloff continuous
# instead of a cliff, so a stronger raw signal still counts for
# meaningfully more, right up to (never quite reaching) the cap.
def _soft_cap(raw: float, cap: float) -> float:
    threshold = cap * 0.75
    if raw <= threshold:
        return raw
    headroom = cap * 0.25
    import math as _math
    return threshold + headroom * _math.tanh((raw - threshold) / headroom)


# Single source of truth for jaimini_apparatus's rubric cap -- used both by
# _jaimini_apparatus_section's soft-cap (below) and score_stream's
# rubric_section call, so the two can never drift out of sync.
_JAIMINI_APPARATUS_CAP = 7.0
# The raw Jaimini apparatus contains many correlated confirmations (sign lord,
# occupants, house lords, argala, matrix, and image padas). Without a scale,
# almost every complete chart reaches the 7-point cap, destroying stream
# discrimination. Compress the aggregate before the final smooth cap.
_JAIMINI_PRECAP_SCALE = 0.45


def _chara_dasha_confirmation(payload: Any, stream_planets: set) -> tuple[float, str]:
    lagna_sign = getattr(payload, "lagna_sign", "") or ""
    current_age = float(getattr(payload, "current_age", 0.0) or 0.0)
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    if not lagna_sign or not planets_d1:
        return 0.0, ""
    active_sign = (
        getattr(payload, "active_chara_dasha_sign", "")
        or getattr(payload, "chara_dasha_sign", "")
        or _get_active_chara_dasha_sign(lagna_sign, current_age, planets_d1)
    )
    if not active_sign:
        return 0.0, ""
    lord = _SIGN_LORD.get(active_sign, "")
    if not lord or lord not in stream_planets:
        return 0.0, ""
    excl = _planet_exclusivity(lord)
    contribution = _JAIMINI_CHARA_DASHA_WEIGHT * excl
    note = (
        f"Active Chara Dasha sign {active_sign} (lord {lord}, a signature planet here) -- "
        f"weighted lower than an adult career reading would use it, since a school-age "
        f"chara dasha reflects the family/life-period more than the child's own aptitude "
        f"(exclusivity {excl:.2f} -> +{contribution:.2f})."
    )
    return contribution, note


def _jaimini_apparatus_section(payload: Any, stream_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    stream_planets = set(meta["planets"].keys())
    planet_house = getattr(payload, "planet_house", {}) or {}

    karakamsha_sign = getattr(payload, "karakamsha", "") or getattr(payload, "karakamsha_sign", "") or ""
    arudha_lagna_sign = getattr(payload, "arudha_lagna", "") or ""
    a10_sign = getattr(payload, "a10_sign", "") or ""
    # GAP-FIX (audit #33): fetched here (once) so the Karakamsha sign-lord
    # trace below can state explicitly whether that lord IS or IS NOT the
    # same planet as the Atmakaraka itself -- these are two distinct Jaimini
    # facts (Karakamsha's dispositor vs. AK, the highest-degree planet) that
    # commonly get elided in prose as if "Karakamsha confirmation" were
    # automatically an "Atmakaraka confirmation." They can coincide (when
    # AK's own sign happens to be the Karakamsha's ruling sign) but are not
    # the same claim.
    _ak_for_trace = getattr(payload, "atmakaraka", "") or ""

    raw = 0.0
    matches: List[str] = []
    fields_available = 0

    # GAP-FIX (2026-07-22g, audit gap 12): Mercury/Jupiter/Saturn/Venus/Sun
    # each sit on 2 (or all 3) streams' signature-planet lists, so "this
    # sign's lord is on the stream's list" was confirming almost every
    # stream almost every time -- not a discriminating signal. Each
    # confirmation below is now scaled by the lord's cross-stream
    # exclusivity (_planet_exclusivity): a planet unique to this stream's
    # list still earns the full weight; one shared across 2-3 streams earns
    # proportionally less, since it cannot actually distinguish between them.
    if karakamsha_sign:
        fields_available += 1
        lord = _SIGN_LORD.get(karakamsha_sign, "")
        if lord and lord in stream_planets:
            excl = _planet_exclusivity(lord)
            contribution = _JAIMINI_KARAKAMSHA_WEIGHT * excl
            raw += contribution
            _ak_relation = (
                f" (this IS also the Atmakaraka, {_ak_for_trace})" if lord == _ak_for_trace and _ak_for_trace
                else f" (distinct from the Atmakaraka, {_ak_for_trace})" if _ak_for_trace else ""
            )
            matches.append(
                f"Karakamsha ({karakamsha_sign}) SIGN-LORD is {lord}{_ak_relation}, a {meta['label']} "
                f"signature planet -- soul-level (Jaimini) confirmation (exclusivity {excl:.2f} -> +{contribution:.2f})."
            )

        # GAP-FIX (2026-07-22j, audit gap 8): karakamsha OCCUPANTS (planets
        # physically sitting in the Karakamsha sign, not just its sign-lord)
        # are a distinct, classically-cited Jaimini confirmation -- a
        # stream-aligned planet actually occupying the soul-lagna carries
        # more weight than merely being that sign's lord from elsewhere.
        occupants = set(getattr(payload, "karakamsha_occupants", []) or [])
        aligned_occupants = [p for p in occupants if p in stream_planets]
        if aligned_occupants:
            fields_available += 1
            occ_excl = max((_planet_exclusivity(p) for p in aligned_occupants), default=0.0)
            occ_contribution = _JAIMINI_KARAKAMSHA_OCCUPANT_WEIGHT * occ_excl
            raw += occ_contribution
            matches.append(
                f"Karakamsha occupant(s) {', '.join(sorted(aligned_occupants))} ({meta['label']} "
                f"signature planet(s)) physically sit in the soul-lagna -- "
                f"+{occ_contribution:.2f} (exclusivity {occ_excl:.2f})."
            )

        # GAP-FIX (2026-07-22j, audit gap 8): 5th/9th/10th-from-Karakamsha --
        # Jaimini's own equivalent of D1's 5th/9th/10th-house reading, but
        # counted from the soul-lagna (Karakamsha) rather than the physical
        # D1 lagna. The house-lord there is found via that house's sign-lord
        # (no separate D9/Navamsha house-lord table is exposed on payload,
        # so this uses karakamsha's own sign-arithmetic, consistent with how
        # jaimini.py's _house_distance/_check_chara_drishti helpers already
        # operate on plain sign names elsewhere in this codebase).
        if karakamsha_sign in _SIGN_NUM:
            k_num = _SIGN_NUM[karakamsha_sign]
            _zodiac_signs = [s for s, _ in sorted(_SIGN_NUM.items(), key=lambda kv: kv[1])]
            for offset, role in ((4, "5th_from_karakamsha"), (8, "9th_from_karakamsha"), (9, "10th_from_karakamsha")):
                target_sign = _zodiac_signs[(k_num - 1 + offset) % 12]
                target_lord = _SIGN_LORD.get(target_sign, "")
                if target_lord and target_lord in stream_planets:
                    fields_available += 1
                    kexcl = _planet_exclusivity(target_lord)
                    kcontribution = _JAIMINI_KARAKAMSHA_HOUSE_WEIGHT * kexcl
                    raw += kcontribution
                    matches.append(
                        f"{role.replace('_', ' ')} ({target_sign}) is ruled by {target_lord}, a "
                        f"{meta['label']} signature planet -- +{kcontribution:.2f} (exclusivity {kexcl:.2f})."
                    )

    if arudha_lagna_sign:
        fields_available += 1
        lord = _SIGN_LORD.get(arudha_lagna_sign, "")
        if lord and lord in stream_planets:
            excl = _planet_exclusivity(lord)
            contribution = _JAIMINI_ARUDHA_WEIGHT * excl * 0.5
            raw += contribution
            matches.append(
                f"Arudha Lagna ({arudha_lagna_sign}) is ruled by {lord}, a {meta['label']} signature "
                f"planet -- perceived-image confirmation (exclusivity {excl:.2f} -> +{contribution:.2f})."
            )

    # GAP-FIX (audit #24/#32, CONFIRMED): A10 (Karma Pada) is a career/
    # public-status significator, not an education/aptitude one -- this
    # section previously scored it identically to genuinely educational
    # indicators (Karakamsha, 5th/9th-from-karakamsha lords), quietly mixing
    # "will this person have public career standing" into "does this stream
    # suit a school-age chart." Upapada (also career/relationship-oriented)
    # was already correctly marked CONTEXT ONLY (+0.00) in this same
    # function -- A10 gets the identical treatment now, for consistency.
    if a10_sign:
        fields_available += 1
        lord = _SIGN_LORD.get(a10_sign, "")
        if lord and lord in stream_planets:
            matches.append(
                f"A10/Karma Pada ({a10_sign}) is ruled by {lord}, a {meta['label']} signature "
                f"planet -- CONTEXT ONLY, +0.00: A10 concerns career/public-image "
                f"manifestation, not school-stream aptitude evidence."
            )

    # GAP-FIX (2026-07-22k, "port jaimini.py logic here"): Upapada Lagna
    # (marriage/partnership-image significator, but also a general Arudha-
    # style confirmation point in jaimini.py's own G11 note) -- ported
    # directly from score_jaimini()'s own upapada handling.
    upapada_sign = getattr(payload, "upapada_lagna", "") or ""
    if upapada_sign:
        fields_available += 1
        lord = _SIGN_LORD.get(upapada_sign, "")
        if lord and lord in stream_planets:
            matches.append(
                f"Upapada Lagna ({upapada_sign}) is ruled by {lord}, a {meta['label']} signature "
                "planet -- CONTEXT ONLY, +0.00: Upapada primarily concerns relationship/partnership "
                "manifestation and is not treated as school-stream aptitude evidence."
            )

    if planet_house:
        fields_available += 1
        argala_raw = _compute_jaimini_argala(10, planet_house)
        argala_surviving = _compute_jaimini_virodhargala(10, planet_house)
        aligned = [p for p in argala_surviving if p in stream_planets]
        if aligned:
            n = min(len(aligned), _JAIMINI_ARGALA_MAX_PLANETS)
            contribution = _JAIMINI_ARGALA_WEIGHT * n * 0.25
            raw += contribution
            cancelled = sorted(set(argala_raw) - set(argala_surviving))
            matches.append(
                f"Surviving (post-Virodhargala) argala on the 10th house from "
                f"{', '.join(aligned)} ({meta['label']} signature planet(s)) -- +{contribution:.1f}"
                + (f"; cancelled: {', '.join(cancelled)}" if cancelled else "")
            )

    # GAP-FIX (2026-07-22i, audit gap 13): chara-dasha confirmation, reusing
    # the same _get_active_chara_dasha_sign already trusted by
    # Field_Determination/field_methods/jaimini.py -- not a new derivation.
    dasha_contribution, dasha_note = _chara_dasha_confirmation(payload, stream_planets)
    if dasha_contribution > 0:
        fields_available += 1
        matches.append(f"{dasha_note} CONTEXT ONLY, +0.00: timing is not inherent aptitude.")

    # GAP-FIX (2026-07-22k, "port jaimini.py logic here"): Karakamsha's own
    # rasi-drishti (chara aspect) onto the D1 lagna -- ported directly from
    # score_jaimini()'s own "Karakamsha's rasi drishti (chara drishti) onto
    # D1 lagna" block, reusing the same _check_chara_drishti imported above.
    # jaimini.py reads this as "the soul's purpose actively directs the
    # native's worldly life" when it fires; credited here only when the
    # planet actually carrying that soul-purpose (the Atmakaraka) is also
    # this stream's own signature planet.
    lagna_sign = getattr(payload, "lagna_sign", "") or ""
    ak_for_drishti = getattr(payload, "atmakaraka", "") or ""
    if karakamsha_sign and lagna_sign and _check_chara_drishti(karakamsha_sign, lagna_sign):
        if ak_for_drishti and ak_for_drishti in stream_planets:
            fields_available += 1
            dexcl = _planet_exclusivity(ak_for_drishti)
            dcontribution = _JAIMINI_KARAKAMSHA_LAGNA_DRISHTI_WEIGHT * dexcl
            raw += dcontribution
            matches.append(
                f"Karakamsha ({karakamsha_sign}) casts rasi drishti onto D1 lagna ({lagna_sign}) -- "
                f"soul purpose (AK={ak_for_drishti}, a {meta['label']} signature planet) directly "
                f"shapes embodied life -- +{dcontribution:.2f} (exclusivity {dexcl:.2f})."
            )

    # GAP-FIX (2026-07-22k, "port jaimini.py logic here"): the AK/AmK-
    # weighted chara-karaka house-distance/drishti matrix, ported from
    # score_jaimini()'s own jaimini_matrix_score loop. jaimini.py weights
    # each planet's contribution by field_affinity[planet]; this engine has
    # no per-field affinity table, so it substitutes this STREAM's own
    # per-planet weight (meta['planets'].get(planet, 0.0)) as the equivalent
    # "how much does this planet matter to this stream" signal -- structurally
    # the same role field_affinity played there.
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    ak_matrix = getattr(payload, "atmakaraka", "") or ""
    amk_matrix = getattr(payload, "amatyakaraka", "") or ""
    if karakamsha_sign and planets_d1:
        matrix_raw = 0.0
        matrix_hits: List[str] = []
        for planet, info in planets_d1.items():
            planet_sign = info.get("sign", "") if isinstance(info, dict) else ""
            planet_stream_weight = meta["planets"].get(planet, 0.0)
            if not planet_sign or planet_stream_weight <= 0.0:
                continue
            base_weight = _JAIMINI_KARAKA_WEIGHTS.get(
                "AmK" if planet == amk_matrix else ("AK" if planet == ak_matrix else ""), 1.0
            )
            house_from_kl = _house_distance(karakamsha_sign, planet_sign)
            if house_from_kl in (1, 10):
                house_modifier = 1.5
            elif house_from_kl in (2, 5):
                house_modifier = 1.3
            elif house_from_kl in (6, 8, 12):
                house_modifier = 0.8
            else:
                house_modifier = 1.0
            drishti_boost = 0.5 if _check_chara_drishti(planet_sign, karakamsha_sign) else 0.0
            jaimini_strength = (base_weight * house_modifier) + drishti_boost
            contribution = planet_stream_weight * jaimini_strength * _JAIMINI_MATRIX_SCALE
            matrix_raw += contribution
            matrix_hits.append(f"{planet}(h{house_from_kl},w{jaimini_strength:.2f})")
        matrix_raw = min(_JAIMINI_MATRIX_CAP, matrix_raw)
        if matrix_raw > 0:
            fields_available += 1
            raw += matrix_raw
            matches.append(
                f"Chara-karaka matrix from Karakamsha ({karakamsha_sign}) for {meta['label']}: "
                f"{', '.join(matrix_hits)} -> +{matrix_raw:.2f} (capped at {_JAIMINI_MATRIX_CAP})"
            )

    # GAP-FIX (2026-07-22j, audit gap 8): AK/AmK Jaimini raja-yoga, reusing
    # the same _detect_jaimini_raj_yogas already trusted by
    # Field_Determination/field_methods/jaimini.py -- credited here only
    # when the AK or AmK carrying that yoga is also this stream's own
    # signature planet, since a raja-yoga on a stream-irrelevant planet says
    # nothing about which stream it favours.
    ak = _ak_for_trace  # GAP-FIX (audit #33): reuse the single fetch above, no re-derivation
    amk = getattr(payload, "amatyakaraka", "") or ""
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    if ak or amk:
        try:
            raj_yogas = _detect_jaimini_raj_yogas(ak, amk, planets_d1)
        except Exception:
            raj_yogas = []
        yoga_planets = [p for p in (ak, amk) if p and p in stream_planets]
        # GAP-FIX (audit #24/#32, CONFIRMED): raja-yoga signifies general
        # achievement/status potential -- it says a person may rise in
        # standing, not WHICH school stream suits them. Scoring it here
        # mixed a career/achievement indicator into stream-discrimination
        # evidence exactly like A10 above -- now CONTEXT ONLY, matching that
        # fix and Upapada's existing treatment. fields_available is still
        # incremented (a raja-yoga touching this stream's signature planet
        # IS a real astrological fact worth naming in the trace), just no
        # longer scored.
        if raj_yogas and yoga_planets:
            fields_available += 1
            matches.append(
                f"Jaimini raja-yoga ({', '.join(raj_yogas)}) involving {', '.join(yoga_planets)} "
                f"({meta['label']} signature planet(s)) -- CONTEXT ONLY, +0.00: raja-yoga "
                f"indicates general achievement/status potential, not which stream suits this chart."
            )

    # GAP-FIX (2026-07-22l): soft-compress instead of letting the caller's
    # hard rubric_section clip do all the work -- see _soft_cap's docstring
    # for why (jaimini_apparatus's exclusivity-scaled components make a hard
    # post-hoc clip land very differently depending on how many streams
    # happen to share a chart's Karakamsha lord, not on the underlying
    # Jaimini strength itself).
    raw_before_soft_cap = raw
    raw = _soft_cap(raw * _JAIMINI_PRECAP_SCALE, _JAIMINI_APPARATUS_CAP)

    # GAP-FIX (2026-07-24, item #8/#9, correlation discount): approximate
    # (not exhaustive) credited-planet set for this section -- AK, AmK, and
    # the Karakamsha sign-lord are Jaimini's core identity planets and the
    # ones most likely to already be credited elsewhere (role_placement
    # scores AK/AmK directly; d24_confirmation's dignity chain can rest on
    # the same karakamsha-lord planet). Not every minor sub-bonus in this
    # function (5th/9th/10th-from-karakamsha, Arudha, Upapada, chara-dasha)
    # is individually tracked here -- those are already soft-capped and
    # comparatively small; tracking only the dominant identity planets keeps
    # this correlation signal meaningful without a much larger refactor.
    _karakamsha_lord = _SIGN_LORD.get(karakamsha_sign, "") if karakamsha_sign else ""
    _amk_for_trace = getattr(payload, "amatyakaraka", "") or ""
    jaimini_planets_credited = {
        p for p in (_ak_for_trace, _amk_for_trace, _karakamsha_lord)
        if p and p in stream_planets
    }

    return {
        "raw": raw,
        "raw_before_soft_cap": round(raw_before_soft_cap, 3),
        "matches": matches,
        "data_status": "COMPUTED" if fields_available > 0 else "MISSING",
        "planets_credited": jaimini_planets_credited,
        "note": (
            "Jaimini apparatus: karakamsha sign-lord + karakamsha OCCUPANTS + "
            "5th/9th/10th-from-karakamsha lords, Arudha Lagna/A10/Upapada Lagna "
            "sign-lord alignment (all scaled by each lord's cross-stream exclusivity "
            "-- a planet shared by 2-3 streams' lists earns proportionally less, "
            "since it cannot actually discriminate between them), surviving "
            "(post-Virodhargala) 10th-house argala, Karakamsha's own rasi-drishti onto "
            "the D1 lagna, the AK/AmK-weighted chara-karaka house-distance/drishti "
            "matrix, AK/AmK Jaimini raja-yoga, and active Chara Dasha lord alignment. "
            "This now covers every component named in "
            "Field_Determination/field_methods/jaimini.py's score_jaimini() except "
            "brahma/maheshwara special lords and the life-science/space-aerospace "
            "career-cluster bonuses, which are career-branch-specific and have no "
            "meaningful under-15 stream-level analogue."
            + (
                f" SOFT-CAPPED (audit fix 2026-07-22l): raw component sum was "
                f"{raw_before_soft_cap:.2f}, pre-cap scaled by {_JAIMINI_PRECAP_SCALE:.2f} "
                f"and compressed to {raw:.2f} (section cap "
                f"{_JAIMINI_APPARATUS_CAP:.0f}) -- see _soft_cap for why this is a smooth "
                f"compression rather than a hard clip."
                if raw_before_soft_cap > _JAIMINI_APPARATUS_CAP * 0.75 else ""
            )
        ),
    }


def _stream_contraindication_section(
    payload: Any, stream_id: str, subjects_ranked: List[Dict[str, Any]],
    planet_strengths: Dict[str, float | None],
) -> Dict[str, Any]:
    """Bounded negative evidence, kept separate from positive support.

    This deliberately uses only high-confidence contradictions: widespread
    weakness among mandatory core planets, combustion of an education lord,
    and placement of the 5th/9th lord in D1 dusthanas. It does not interpret a
    missing field as weakness.
    """
    penalty = 0.0
    notes: List[str] = []

    mandatory_core = [s for s in subjects_ranked if s.get("core") and s.get("mandatory_planet")]
    known_mandatory = [s for s in mandatory_core if planet_strengths.get(s["mandatory_planet"]) is not None]
    if known_mandatory:
        weak = [s for s in known_mandatory if float(planet_strengths[s["mandatory_planet"]]) < 0.85]
        weak_fraction = len(weak) / len(known_mandatory)
        if weak_fraction:
            amount = 6.0 * weak_fraction
            penalty += amount
            notes.append(
                f"{len(weak)}/{len(known_mandatory)} mandatory core-subject planets are below 0.85 "
                f"({', '.join(s['label'] for s in weak)}) -> -{amount:.2f}"
            )

    house_lords = getattr(payload, "house_lords", {}) or {}
    planet_house = getattr(payload, "planet_house", {}) or {}
    combust = set(getattr(payload, "combust_planets", []) or [])
    seen_planets = set()
    for house_no, role in ((5, "5th lord"), (9, "9th lord")):
        lord = house_lords.get(str(house_no), "")
        if not lord or lord in seen_planets:
            continue
        seen_planets.add(lord)
        placed = planet_house.get(lord)
        if placed in (6, 8, 12):
            penalty += 1.5
            notes.append(f"{role} {lord} is placed in dusthana H{placed} -> -1.50")
        if lord in combust:
            penalty += 1.5
            notes.append(f"{role} {lord} is combust -> -1.50")

    # GAP-FIX (2026-07-24, explicit user request, item #23): compound
    # contraindication patterns -- the checks above are each independent
    # single-fact penalties; they don't catch the case where TWO weak facts
    # about the SAME planet compound into a materially stronger
    # contraindication than either fact alone would suggest. Deliberately
    # scoped to two concrete, high-confidence compound patterns (not the
    # full list a redesign could eventually cover) so this stays a bounded
    # addition, not a new penalty architecture:
    #   (i) a mandatory subject planet that is BOTH weak (<0.85) AND is
    #       itself the 5th or 9th lord already flagged combust/dusthana
    #       above -- the same planet failing two independent tests is a
    #       stronger signal than either alone, not merely additive.
    #   (ii) D1/D24 contradiction -- a stream signature planet that is
    #       strong in D1 (>=1.10, comfortably above the 1.0 baseline) but
    #       DEBILITATED in D24 specifically: natal promise that the
    #       education-chart (Siddhamsha) itself contradicts, which is a
    #       different and additional concern from D1 weakness alone.
    afflicted_5_9_planets = {
        n.split(" ")[2] for n in notes if n.startswith(("5th lord", "9th lord"))
    }
    compound_notes: List[str] = []
    compound_penalty = 0.0
    if known_mandatory and afflicted_5_9_planets:
        weak_planets = {s["mandatory_planet"] for s in known_mandatory
                         if float(planet_strengths[s["mandatory_planet"]]) < 0.85}
        double_hit = weak_planets & afflicted_5_9_planets
        for planet in sorted(double_hit):
            compound_penalty += 1.5
            compound_notes.append(
                f"COMPOUND: {planet} is both a weak (<0.85) mandatory subject planet AND "
                f"already flagged as an afflicted 5th/9th lord above -- the same weakness "
                f"showing up in two independent tests -> -1.50"
            )

    d24_dignities = getattr(payload, "d24_planet_dignities", {}) or {}
    meta = STREAM_META.get(stream_id, {})
    stream_planets = meta.get("planets", {})
    for planet in sorted(stream_planets):
        strength = planet_strengths.get(planet)
        if strength is None or float(strength) < 1.10:
            continue
        if d24_dignities.get(planet, "") == "DEBILITATED":
            compound_penalty += 1.0
            compound_notes.append(
                f"COMPOUND: {planet} is D1-strong (strength {float(strength):.2f}) but "
                f"DEBILITATED in D24 -- the education-chart (Siddhamsha) specifically "
                f"contradicts this planet's natal promise -> -1.00"
            )
    compound_penalty = min(3.0, compound_penalty)
    if compound_penalty > 0:
        penalty += compound_penalty
        notes.extend(compound_notes)

    penalty = min(12.0, penalty)
    return {
        "raw": -penalty,
        "matches": notes,
        "data_status": "COMPUTED" if (known_mandatory or house_lords) else "MISSING",
    }


def score_stream(
    payload: Any, stream_id: str, planet_strengths: Dict[str, float | None],
    subjects_ranked: List[Dict[str, Any]], *,
    field_derived_evidence: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Score one broad stream (Science/Commerce/Humanities) for this chart.

    Rubric (mirrors Field_Determination/field_methods method files' shape so
    downstream report code can render it the same way); caps sum to 100.
    GAP-FIX (2026-07-22m): this docstring's per-section cap numbers had
    drifted out of sync with the actual rubric_section() calls below --
    still showing (cap 28)/(cap 13) from an earlier rebalancing pass after
    later passes moved those to 19/16 (2026-07-22j/k) -- the same kind of
    stale-label bug already caught once in role_placement's own note text
    (2026-07-22l). Corrected below to match the CURRENT values, which are
    the actual rubric_section() cap arguments a few lines down, not this
    docstring:
      planetary_strength (cap 19) -- weighted planetary strength across the
                                      stream's signature planets
      house_support      (cap  6) -- house-weighted occupancy/lordship bonus
                                      for those same signature planets
      role_placement      (cap 12) -- 5th(vidya)/9th(higher-learning) lord /
                                      10th lord / AK / AmK placement, deduped
                                      per planet (see _role_placement_bonus)
       subject_evidence    (cap 20) -- bundle-aware core-subject evidence +
                                      best non-shared elective, discounted
                                      for circularity (see _subject_evidence_section)
       d24_confirmation    (cap 18) -- D24 (education-chart) confirmation:
                                      lagna/5th/9th lord placement + dignity
                                      + D24 house-support for this stream's
                                      own signature planets + dispositor/
                                      combustion affliction check on the D24
                                      lords, with an in-house D24 construction
                                      cross-check (see _d24_confirmation_section)
      relational_d1       (cap  8) -- 5th/9th/10th lord conjunction/aspect
                                      connections relevant to this stream
                                      (see _relational_d1_section)
       jaimini_apparatus    (cap 7) -- karakamsha sign-lord + occupants +
                                      5th/9th/10th-from-karakamsha lords +
                                      Arudha Lagna/A10/Upapada Lagna sign-lord
                                      + Karakamsha rasi-drishti onto D1 lagna +
                                      chara-karaka matrix + surviving 10th-house
                                      argala + AK/AmK raja-yoga + chara-dasha,
                                      soft-capped rather than hard-clipped
                                      (see _jaimini_apparatus_section, _soft_cap)

    Cap-history summary (for anyone reading old trace text/reports against
    this code): 2026-07-22e introduced relational_d1/jaimini_apparatus at
    8/8 (taking planetary_strength 35->28, subject_evidence 22->18);
    2026-07-22j raised d24_confirmation/jaimini_apparatus to 25/13 (taking
    planetary_strength 28->22, subject_evidence 18->14); 2026-07-22k raised
    jaimini_apparatus again to 16 (taking planetary_strength 22->19).
    Nothing has changed the cap since 22k -- only this docstring's own
    numbers needed catching up.
    """
    meta = STREAM_META[stream_id]
    weights: Dict[str, float] = meta["planets"]
    houses: List[int] = meta["houses"]
    house_weights: Dict[int, float] = meta.get("house_weights", {})

    available_weights = {p: w for p, w in weights.items() if planet_strengths.get(p) is not None}
    available_weight = sum(available_weights.values())
    configured_weight = sum(weights.values()) or 1.0
    planet_data_coverage = available_weight / configured_weight
    weighted_strength = (
        sum(float(planet_strengths[p]) * w for p, w in available_weights.items()) / available_weight
        if available_weight else 0.0
    )
    # Missing planets do not become synthetic strength=1.0. Coverage scales
    # this section, so a partial vector cannot look as certain as a complete one.
    # GAP-FIX (audit #64, contract-level documentation only -- no behavior
    # change): the "15.80" multiplier below is an ENGINEERED scale constant,
    # not a derived one. eff_strengths' own convention treats 1.0 as the
    # minimum-viable Shadbala-based strength (see _planet_strength's
    # docstring/jyotish/astro.py::_compute_eff_strengths) with no fixed
    # ceiling -- values commonly range roughly 0.5-2.0 in practice for real
    # charts, but nothing in the astrological literature specifies that a
    # strength of, say, 1.3 should be worth exactly 30% more section credit
    # than 1.0. 15.80 was tuned so a "typical" weighted_strength (~1.0-1.5)
    # lands this section in a reasonable fraction of its cap, not derived
    # from any formal strength-to-aptitude mapping. Same caveat applies to
    # every other engineered multiplier in this file (house_bonus_raw's
    # 1.6, subject_evidence's 13.64/6.36, etc.) -- see SCORING_CONTRACT
    # note at module top and score_interpretation_note in stream_report.py.
    # GAP-FIX (field-derived-evidence rebudget): when the optional 8th
    # section (field_determination_evidence, cap 6) is enabled, its 6 points
    # are taken entirely from this section (24->18) rather than touching
    # subject_evidence/jaimini_apparatus's own internally-tuned sub-weights.
    # Disabled (default) mode is byte-identical to pre-existing behavior --
    # verified via regression that disabled-mode scores are unchanged.
    _planetary_strength_cap = 18.0 if field_derived_evidence is not None else 24.0
    core_raw = weighted_strength * 15.80 * planet_data_coverage
    core = rubric_section("planetary_strength", core_raw, _planetary_strength_cap,
                           note=(f"Weighted strength of {', '.join(weights)} for {meta['label']} "
                                 f"(planet-data coverage {planet_data_coverage:.0%}; missing values "
                                 "remain unknown and earn no credit)."
                                 + (f" [cap reduced to {_planetary_strength_cap:.0f} to make room for "
                                    "the experimental field_determination_evidence section]"
                                    if field_derived_evidence is not None else "")))

    house_bonus_raw = sum(_house_support(payload, p, houses, house_weights) for p in weights) * 1.6
    support = rubric_section("house_support", house_bonus_raw, 8.0,
                              note=f"House-weighted occupancy/lordship of {houses} by {meta['label']}'s signature planets.")

    subject_evidence = _subject_evidence_section(stream_id, subjects_ranked, meta)

    # GAP-FIX (2026-07-24, explicit user request, item #8/#9): these four
    # sections (role_placement, d24_confirmation, relational_d1,
    # jaimini_apparatus) all draw evidence from the SAME small set of
    # "special" planets for this stream -- house lords, AK/AmK, karakamsha
    # lord -- so the same underlying astrological fact (e.g. "Mercury is the
    # 5th lord AND well-placed") can surface as independent-looking
    # testimony in three or four sections at once. This is a REAL
    # correlation, not a fabricated one -- it does not eliminate it (that
    # would need the sections themselves redesigned into non-overlapping
    # evidence layers, out of scope for a bounded fix), but discounts the
    # SUM of these four sections' raw contributions in proportion to how
    # concentrated the credit is in few planets, using the same
    # "1.0 - MAX_DISCOUNT*overlap" shape already established for
    # subject_evidence's own circularity discount above.
    role = _role_placement_bonus(payload, houses, house_weights)
    d24 = _d24_confirmation_section(payload, stream_id, meta)
    relational = _relational_d1_section(payload, stream_id, meta)
    jaimini = _jaimini_apparatus_section(payload, stream_id, meta)

    _CROSS_SECTION_MAX_DISCOUNT = 0.20
    _sections_planets = [
        role.get("planets_credited") or set(),
        d24.get("planets_credited") or set(),
        relational.get("planets_credited") or set(),
        jaimini.get("planets_credited") or set(),
    ]
    _sections_with_credit = [s for s in _sections_planets if s]
    _all_credited = set().union(*_sections_planets) if _sections_planets else set()
    if len(_sections_with_credit) >= 2 and _all_credited:
        # Average, over each pair of sections that both credited at least one
        # planet, how much their credited-planet sets overlap (Jaccard) --
        # high average overlap means the same few planets are doing double
        # (or quadruple) duty across sections; low overlap means the
        # sections are drawing on genuinely different planets, i.e.
        # independent-ish testimony.
        _pair_overlaps = []
        for i in range(len(_sections_with_credit)):
            for j in range(i + 1, len(_sections_with_credit)):
                a, b = _sections_with_credit[i], _sections_with_credit[j]
                union = a | b
                if union:
                    _pair_overlaps.append(len(a & b) / len(union))
        _avg_overlap = sum(_pair_overlaps) / len(_pair_overlaps) if _pair_overlaps else 0.0
    else:
        _avg_overlap = 0.0
    _cross_section_factor = 1.0 - _CROSS_SECTION_MAX_DISCOUNT * _avg_overlap
    _cross_section_note_suffix = (
        f" [cross-section correlation discount x{_cross_section_factor:.2f}: "
        f"credited planets {sorted(_all_credited) or 'none'} overlap "
        f"avg {_avg_overlap:.2f} across role_placement/d24_confirmation/"
        f"relational_d1/jaimini_apparatus -- see score_stream's item #8/#9 comment]"
        if _avg_overlap > 0 else ""
    )

    role_section = rubric_section(
        "role_placement", role["raw"] * _cross_section_factor, 15.0,
        note=(
            # GAP-FIX (2026-07-22l): this label previously said "10th lord /
            # AK / AmK / 5th(vidya) lord" only -- stale since the 2026-07-22g
            # rebalance added h9_lord as its own checked role (weighted 6.0,
            # tied for the highest weight in the table). A reader had no way
            # to know 9th-lord placement was being evaluated at all.
            # GAP-FIX (audit, this turn): same staleness risk -- h4_lord
            # (basic/foundational schooling, distinct from 5th's aptitude
            # and 9th's higher-learning significations) added here too.
            f"4th(basic schooling)/5th(vidya/aptitude)/9th(higher-learning) lord / "
            f"10th lord / AK / AmK placement in "
            f"{meta['label']}'s houses {houses} (data_status={role['data_status']}"
            + (f", roles not available: {', '.join(role['roles_missing'])}" if role["roles_missing"] else "")
            + "): " + ("; ".join(role["matches"]) if role["matches"] else "no match")
            + _cross_section_note_suffix
        ),
    )

    d24_section = rubric_section(
        "d24_confirmation", d24["raw"] * _cross_section_factor, 18.0,
        note=(
            f"(data_status={d24['data_status']}, signal_state={d24.get('signal_state', 'UNKNOWN')}) "
            + ("; ".join(d24["matches"]) if d24["matches"] else
               "no recognised house-membership pattern -- NEUTRAL_NO_SIGNAL, not a rejection of this stream")
            + _cross_section_note_suffix
        ),
    )

    relational_section = rubric_section(
        "relational_d1", relational["raw"] * _cross_section_factor, 8.0,
        note=f"(data_status={relational['data_status']}) " + ("; ".join(relational["matches"]) if relational["matches"] else "no match")
             + _cross_section_note_suffix,
    )

    jaimini_section = rubric_section(
        "jaimini_apparatus", jaimini["raw"] * _cross_section_factor, _JAIMINI_APPARATUS_CAP,
        note=f"(data_status={jaimini['data_status']}) " + ("; ".join(jaimini["matches"]) if jaimini["matches"] else "no match")
             + _cross_section_note_suffix,
    )

    contraindication = _stream_contraindication_section(
        payload, stream_id, subjects_ranked, planet_strengths,
    )
    contraindication_section = rubric_section(
        "contraindications", contraindication["raw"], 12.0, kind="penalty",
        note=(f"(data_status={contraindication['data_status']}) "
              + ("; ".join(contraindication["matches"]) if contraindication["matches"] else
                 "no high-confidence contraindication found")),
    )

    sections = [core, support, role_section, subject_evidence, d24_section,
                relational_section, jaimini_section, contraindication_section]

    field_derived_section = None
    if field_derived_evidence is not None:
        fde_marks = field_derived_evidence.get("marks", {}) or {}
        fde_raw = float(fde_marks.get(stream_id, 0.0) or 0.0)
        fde_status = field_derived_evidence.get("data_status", "UNAVAILABLE")
        field_derived_section = rubric_section(
            "field_determination_evidence", fde_raw, FIELD_DERIVED_EVIDENCE_CAP,
            note=(
                f"(EXPERIMENTAL, default-off; data_status={fde_status}, "
                f"independence_class={field_derived_evidence.get('independence_class', 'UNKNOWN')}) "
                + (
                    f"reliability={field_derived_evidence.get('reliability', 0.0):.2f}, "
                    f"adjusted_distribution={field_derived_evidence.get('adjusted_distribution', {})}"
                    if fde_status == "COMPUTED" else
                    "; ".join(field_derived_evidence.get("warnings", [])) or "no data"
                )
            ),
        )
        sections.append(field_derived_section)

    rubric = build_score_rubric(f"stream_{stream_id}", sections)

    # GAP-FIX (2026-07-22f, audit P0-1, CONFIRMED real bug): this used to sum
    # each section's UNCAPPED `actual` value into total_raw, while the
    # rubric's per-section `display` field (and build_score_rubric's own
    # `display_total`) already correctly capped each section. Every section
    # whose raw contribution exceeded its advertised cap (e.g. house_support
    # actual=7.92 vs cap=6, role_placement actual=16 vs cap=12, relational_d1
    # actual=12 vs cap=8) was silently smuggling the overflow into the final
    # score -- on Samyuhtha this added ~10 points beyond every declared cap,
    # and on Lakshman/Ramsunder it was large enough to flip which stream
    # ranked first once caps were actually enforced. The rubric's own
    # display_total (== sum of min(actual, cap) per section, with penalty
    # sections handled via rubric_section's existing sign convention) is now
    # the single source of truth for the score that feeds ranking/close-call.
    total_raw = rubric["display_total"]

    _trace = [
        f"{meta['label']}: planetary_strength={core['actual']:.2f}/{_planetary_strength_cap:.0f}, "
        f"house_support={support['actual']:.2f}/8, "
        f"role_placement={role_section['actual']:.2f}/15 ({role_section['note']}), "
        f"subject_evidence={subject_evidence['actual']:.2f}/20 ({subject_evidence['note']}), "
        f"d24_confirmation={d24_section['actual']:.2f}/18 ({d24_section['note']}), "
        f"relational_d1={relational_section['actual']:.2f}/8 ({relational_section['note']}), "
        f"jaimini_apparatus={jaimini_section['actual']:.2f}/7 ({jaimini_section['note']})",
        f"contraindications={contraindication_section['display']:.2f} "
        f"(cap -12; {contraindication_section['note']})",
    ]
    if field_derived_section is not None:
        _trace.append(
            f"field_determination_evidence={field_derived_section['actual']:.2f}/"
            f"{FIELD_DERIVED_EVIDENCE_CAP:.0f} ({field_derived_section['note']})"
        )

    result = method_result(
        name=f"stream_{stream_id}",
        score=total_raw,
        trace=_trace,
        components={p: (round(float(planet_strengths[p]), 3) if planet_strengths.get(p) is not None else None)
                    for p in weights},
        rubric=rubric,
        normalization_cap=100.0,
    )
    result["stream_id"] = stream_id
    result["label"] = meta["label"]
    result["description"] = meta["description"]
    # GAP-FIX (2026-07-22h, audit gaps 22/23/24): sub-archetype label from
    # whichever core subject(s) actually ranked highest, so "Science" or
    # "Humanities" alone doesn't hide whether the chart leans technical vs
    # life-science, or governance vs language/arts. Labeling only -- does
    # not affect scoring.
    core_rows = [s for s in subjects_ranked if s.get("core")]
    top_core = sorted(core_rows, key=lambda s: -s["score"])[:2]
    archetype_votes: Dict[str, int] = {}
    for s in top_core:
        arch = SUBJECT_SUB_ARCHETYPES.get(s["subject_id"], "")
        if arch:
            archetype_votes[arch] = archetype_votes.get(arch, 0) + 1
    result["sub_archetype"] = (
        max(archetype_votes, key=archetype_votes.get) if archetype_votes else "General"
    )
    result["role_placement_data_status"] = role["data_status"]
    # GAP-FIX (audit #62): now populated for role_placement/relational_d1 too
    # (previously only d24_confirmation had this distinction).
    result["role_placement_signal_state"] = role.get("signal_state", "UNKNOWN")
    result["d24_confirmation_data_status"] = d24["data_status"]
    result["d24_confirmation_signal_state"] = d24.get("signal_state", "UNKNOWN")
    result["d24_construction_mismatches"] = d24.get("d24_construction_mismatches", {})
    result["relational_d1_data_status"] = relational["data_status"]
    result["relational_d1_signal_state"] = relational.get("signal_state", "UNKNOWN")
    result["jaimini_apparatus_data_status"] = jaimini["data_status"]
    result["contraindication_data_status"] = contraindication["data_status"]
    result["planet_data_coverage"] = round(planet_data_coverage, 3)
    if field_derived_section is not None:
        result["field_determination_evidence_data_status"] = field_derived_evidence.get("data_status", "UNAVAILABLE")

    result["score_compression"] = {
        "raw_total_before_compression": round(total_raw, 2),
        "compressed_score": result["score"],
        "compression_applied": total_raw > 80.0,
        "note": (
            "score/normalized_score apply clamp_score's smooth tanh compression "
            "above 80 (rank order preserved, headline number pulled toward a "
            "100 ceiling); raw_total_before_compression is the sum of each "
            "section's CAPPED display value (rubric['display_total']) -- fixed "
            "2026-07-22f, previously this summed uncapped actual values, which "
            "could exceed the sum of the advertised caps."
        ),
    }
    return result


# GAP-FIX (2026-07-22, audit gaps 16/17; steepened 2026-07-22g per audit gap
# 19): bounded ceiling multiplier applied when a subject's designated
# `mandatory` planet is weaker than eff_strengths' own normalization baseline
# of 1.0 (see jyotish/astro.py's _PLANET_MIN_SHADBALA convention).
# GAP-FIX (audit gap 17): the threshold is an ENGINEERED minimum-support
# reference point chosen for this scoring model, not a classically
# prescribed number -- language below was corrected accordingly (was
# "classical minimum-viable baseline", which overstated its doctrinal
# authority).
# GAP-FIX (audit gap 19, CONFIRMED live): the old linear curve
# (floor + (1-floor)*strength) was nearly cosmetic near strength~0.85-0.96 --
# e.g. strength=0.96 only cut the ceiling by ~2%, strength=0.85 by ~7%, far
# too weak to act as a genuine gate for a supposedly "mandatory" planet. The
# curve is now driven by the SHORTFALL below the 1.0 threshold, scaled by
# _MANDATORY_SHORTFALL_SCALE before being subtracted from 1.0 (floored at
# _MANDATORY_FLOOR_MULT_AT_ZERO) -- so a mild shortfall (0.96) now costs a
# meaningful ~12%, and a real shortfall (0.85) drives the ceiling all the way
# to its floor, instead of a token few points either way.
_MANDATORY_FLOOR_MULT_AT_ZERO = 0.55
_MANDATORY_SHORTFALL_SCALE = 3.0


def _mandatory_ceiling_multiplier(mandatory_strength: float) -> float:
    if mandatory_strength >= 1.0:
        return 1.0
    shortfall = (1.0 - mandatory_strength) * _MANDATORY_SHORTFALL_SCALE
    return max(_MANDATORY_FLOOR_MULT_AT_ZERO, 1.0 - shortfall)


def score_subjects(stream_id: str, planet_strengths: Dict[str, float | None]) -> List[Dict[str, Any]]:
    """Rank every subject under one stream from the chart's planetary strengths."""
    rows = []
    for subj in SUBJECT_REGISTRY.get(stream_id, []):
        weights: Dict[str, float] = subj["planets"]
        total_w = sum(weights.values()) or 1.0
        available = {p: w for p, w in weights.items() if planet_strengths.get(p) is not None}
        available_w = sum(available.values())
        data_coverage = available_w / total_w
        raw = (
            sum(float(planet_strengths[p]) * w for p, w in available.items()) / available_w
            if available_w else 0.0
        )
        # Coverage is part of the score rather than merely a warning. This
        # prevents a single available strong planet from impersonating the
        # subject's complete multi-planet signature.
        score_pct = clamp_score(raw * 60.0 * data_coverage)

        mandatory_planet = subj.get("mandatory", "")
        mandatory_note = ""
        if mandatory_planet:
            mandatory_strength = planet_strengths.get(mandatory_planet)
            ceiling_mult = (
                _MANDATORY_FLOOR_MULT_AT_ZERO if mandatory_strength is None
                else _mandatory_ceiling_multiplier(float(mandatory_strength))
            )
            if ceiling_mult < 1.0:
                pre_ceiling_score = score_pct
                score_pct = score_pct * ceiling_mult
                mandatory_note = (
                    f" Contraindication: {mandatory_planet} is this subject's mandatory "
                    f"planet and is {'unavailable' if mandatory_strength is None else 'below this engine’s engineered minimum-support threshold'} "
                    + ("" if mandatory_strength is None else f"(strength index {mandatory_strength:.2f} < 1.00, not a classically prescribed cutoff) ")
                    + f"-- score capped from "
                    f"{pre_ceiling_score:.1f} to {score_pct:.1f} ({ceiling_mult:.2f}x ceiling)."
                )

        # GAP-FIX (2026-07-22, audit gap 20): "leading contributor" used to
        # be whichever planet had the highest CONFIGURED weight in the
        # registry, regardless of how strong that planet actually is on
        # this chart -- so a subject's rationale could name a planet that
        # contributes LESS to the actual score than a lower-weighted one
        # that happens to be much stronger here. Now computed from the
        # actual weight x strength contribution.
        contributions = {p: float(planet_strengths[p]) * w for p, w in weights.items()
                         if planet_strengths.get(p) is not None}
        lead_planet = max(contributions, key=contributions.get) if contributions else ""
        lead_strength = planet_strengths.get(lead_planet) if lead_planet else None
        ordered_planets = sorted(weights.items(), key=lambda kv: -kv[1])
        rationale = (
            f"{subj['label']} draws mainly on {', '.join(p for p, _ in ordered_planets)}; "
            f"{lead_planet} is this chart's leading ACTUAL contributor here "
            f"(strength index {lead_strength:.2f}, weight {weights.get(lead_planet, 0):.2f}); "
            f"planet-data coverage is {data_coverage:.0%}."
            if lead_planet else f"{subj['label']}: planetary-strength data unavailable."
        ) + mandatory_note
        rows.append({
            "subject_id": subj["id"],
            "label": subj["label"],
            "core": bool(subj.get("core", False)),
            "shared_elective": bool(subj.get("shared_elective", False)),
            "mandatory_planet": mandatory_planet or None,
            "mandatory_contraindication": bool(mandatory_note),
            "calculation_status": "COMPUTED" if data_coverage >= 0.999 else (
                "PARTIAL" if data_coverage > 0 else "INSUFFICIENT_DATA"
            ),
            "data_coverage": round(data_coverage, 3),
            "score": round(min(100.0, score_pct), 2),
            "signature_planets": list(weights.keys()),
            # GAP-FIX (2026-07-22h, audit gap 16): kept internally (not part
            # of the public report contract) so _subject_evidence_section can
            # measure how circular a given subject's planet signature is
            # relative to its stream's own planet-weight vector.
            "_planet_weights": dict(weights),
            "rationale": rationale,
        })
    rows.sort(key=lambda r: -r["score"])
    return rows


_NEAR_TIE_MARGIN = 3.0  # normalized-score points; below this, treat top-2 streams as a tie


def _calculation_identity(payload: Any) -> Dict[str, Any]:
    """GAP-FIX (2026-07-22, audit gap 24): surface the same calculation
    identity (ayanamsha, node type, house system) jyotish/engine_io.py
    already computes, so a report states what chart-calculation convention
    it was scored under and whether birth-time precision was exact.

    GAP-FIX (2026-07-22g, audit gap 26, CONFIRMED real inconsistency):
    previously defaulted birth_time_uncertainty_minutes to 0 regardless of
    whether birth_time_precision was actually known -- so a chart whose
    precision is genuinely UNKNOWN could report "0 minutes uncertainty",
    which reads as EXACT. These must not be conflated: uncertainty_minutes
    is now only ever a number when precision is actually known to be
    approximate/rectified with a numeric window attached; otherwise it is
    explicitly None, distinct from "confirmed exact" (0).
    """
    calc_identity = getattr(payload, "calculation_identity", {}) or {}
    raw_precision = getattr(payload, "birth_time_precision", None)
    precision = (raw_precision or "UNKNOWN")
    if isinstance(precision, str):
        precision_norm = precision.strip().upper() or "UNKNOWN"
        # Normalize legacy free-text values into the small closed vocabulary
        # the report contract expects: EXACT_RECORDED / APPROXIMATE /
        # RECTIFIED / UNKNOWN.
        if precision_norm in ("EXACT", "EXACT_RECORDED"):
            precision_norm = "EXACT_RECORDED"
        elif precision_norm in ("APPROX", "APPROXIMATE"):
            precision_norm = "APPROXIMATE"
        elif precision_norm == "RECTIFIED":
            precision_norm = "RECTIFIED"
        else:
            precision_norm = "UNKNOWN"
    else:
        precision_norm = "UNKNOWN"

    raw_uncertainty = getattr(payload, "birth_time_uncertainty_minutes", None)
    if precision_norm == "EXACT_RECORDED":
        uncertainty_minutes = 0
    elif precision_norm in ("APPROXIMATE", "RECTIFIED") and raw_uncertainty is not None:
        # Only trust an upstream-supplied uncertainty number when precision
        # is deliberately flagged non-exact -- if precision itself is
        # UNKNOWN, a payload default of 0 minutes cannot be trusted as a
        # real "confirmed exact to the minute" claim; it is almost certainly
        # just an unset numeric field, not a measured window.
        try:
            uncertainty_minutes = float(raw_uncertainty)
        except (TypeError, ValueError):
            uncertainty_minutes = None
    else:
        uncertainty_minutes = None

    return {
        "ayanamsha": calc_identity.get("ayanamsa", "UNKNOWN"),
        "node_type": calc_identity.get("node_type", "UNKNOWN"),
        "house_system": calc_identity.get("house_system", "UNKNOWN"),
        "birth_time_precision": precision_norm,
        "birth_time_uncertainty_minutes": uncertainty_minutes,
        "note": (
            "role_placement (house-based) can shift if birth time is imprecise "
            "enough to move a planet across a house cusp -- treat results as "
            "more provisional when birth_time_precision != 'EXACT_RECORDED'. "
            "birth_time_uncertainty_minutes is null (not 0) whenever precision "
            "is not confirmed exact and no numeric uncertainty window was "
            "supplied -- null and 0 are NOT interchangeable here. "
            "HONEST SCOPE NOTE (audit gap 6): this engine does NOT re-run the "
            "chart calculation at birth_time +/- uncertainty to test whether "
            "role_placement/relational_d1/d24_confirmation would flip -- doing "
            "so needs re-deriving D1/D9/D24 from scratch at perturbed times, "
            "which sits in jyotish/astro.py's calculation layer, not this "
            "scoring layer, and the payload does not currently expose a "
            "lagna-degree/cusp-proximity figure this section could use as a "
            "cheaper proxy either. A warning is a placeholder, not a "
            "computed sensitivity result -- do not read the absence of a "
            "flip warning as 'verified stable'. "
            "HONEST SCOPE NOTE (audit #66): current_age (reported at the top "
            "level of this report, used for the eligibility age-gate and the "
            "age_routing_note below) is computed upstream by "
            "jyotish/astro.py::_calc_age(dob, system_config.current_date) -- "
            "if the source chart JSON did not supply system_config.current_date, "
            "that function silently falls back to the wall-clock date the "
            "engine happened to run on. The SAME chart file can therefore "
            "report a different current_age (and, near the 15-year boundary, "
            "a different eligibility outcome) depending on which calendar day "
            "it was scored -- this payload does not expose which of the two "
            "paths was actually taken, so this note can only warn that the "
            "ambiguity exists, not resolve it from within Stream_Determination."
        ),
    }


# ============================================================================
# D24/JAIMINI ARBITRATION POLICY (2026-07-24, explicit user decision --
# "Option 1" from md/STREAM_DETERMINATION_FINAL_AUDIT_20260724.md's D1-vs-D24
# conflict finding, audit/current_stream_execution_audit.json)
#
# CLASSICAL RATIONALE (per the domain-expert user's explicit decision, not
# this engine's own invention): a divisional chart (varga) does not carry
# EQUAL, INDEPENDENT evidentiary weight to the natal (D1) chart for a given
# life-question -- D1 establishes the raw CANDIDATE significations (which
# stream(s) this chart has genuine capacity/inclination toward at all), and
# a relevant varga (here D24/Siddhamsha, the education-varga, read together
# with the Jaimini apparatus) REFINES/ARBITRATES among those candidates when
# D1's own signal is not already decisive on its own. Treating D1 and D24 as
# two independent additive buckets summed regardless of how clear D1 already
# was (this engine's behavior before this policy existed) lets D24 silently
# outweigh a D1 lead any time D24's numbers happen to run large for a
# different stream -- backwards from classical precedence, and confirmed
# live on 7/19 real charts in the 2026-07-24 audit where this engine's
# top-ranked stream disagreed with an independent multi-factor check
# specifically along this D1-vs-D24 fault line.
#
# THRESHOLD CHOICE: "D1 inconclusive" = the D1-derived subtotal
# (planetary_strength + house_support + role_placement display/capped
# values -- the three sections that are pure D1 evidence; combined cap
# ~24+8+15=47, or ~18+8+15=41 when the experimental field_derived_evidence
# section is enabled and planetary_strength's own cap shrinks) is within
# D1_ARBITRATION_MARGIN points of the D1-leading stream for this chart.
# D1_ARBITRATION_MARGIN=3.0 deliberately reuses, in absolute points, the
# engine's own pre-existing _NEAR_TIE_MARGIN (3.0 points, used for the FINAL
# normalized 0-100 score's own close-call check) rather than inventing a new
# number -- note this makes it a PROPORTIONALLY WIDER tolerance band on the
# ~41-47-point D1 subtotal (~6-7%) than the same 3.0 points is on the
# 100-point final score (3%), which is appropriate: a 3-section partial sum
# is noisier than the fully-combined 7-8-section final score, so a wider
# band before calling it "inconclusive" is defensible. Checked against real
# report data (2026-07-24 batch, stream_records_full_audit/*.json): D1
# subtotal gaps between the top-2 streams on real charts range from ~0.06
# points (Ramsunder) up to ~8.5 points (a clearly decisive D1 lead) -- 3.0
# sits inside that observed range, catching the genuinely-close cases
# (Hemant M 2.81, Mithila 2.41, Sindhuja Lakshman 2.57, Ajay Siddarth
# 0.74-2.78, Ramsunder ~0.06-2.13, Rithul 1.33) while correctly leaving
# Lakshman Kumar's clear 3.55-point D1 lead untouched.
#
# MECHANISM: when the D1 subtotal is inconclusive (>=2 streams within
# D1_ARBITRATION_MARGIN of the D1 leader), ONLY those near-tied streams get
# their (d24_confirmation + jaimini_apparatus) combined contribution boosted
# by D24_ARBITRATION_BOOST (x1.5, re-capped at the two sections' own
# combined cap of 25.0) before it is folded into the final total -- giving
# D24/Jaimini genuine, visible extra say specifically to break THAT tie.
# Streams outside the near-tied set (already a clear D1 also-ran) are not
# touched. When D1 is NOT inconclusive (a single clear D1 leader), nothing
# changes at all -- D24/Jaimini remain exactly as additive/confirmatory as
# they were before this policy existed, per explicit user instruction not to
# let this fix dampen D24's role in the clear-D1 case.
#
# REVERSIBLE / AUDITABLE: gated behind d24_arbitration_enabled (default
# True on compute_stream_determination(); pass False to restore the
# pre-2026-07-24 pure-additive behavior byte-for-byte -- see that
# function's own parameter). Every report carries top-level
# "d1_arbitration_status" ("clear_d1_signal" | "d24_arbitrated" |
# "still_tied" | "disabled") plus a "d1_arbitration_detail" block (each
# stream's D1 subtotal, which streams were near-tied, the boost applied,
# top-ranked stream before/after) so this never fires silently. When it
# fires, each affected stream's own score_rubric also gains a visible
# "d24_arbitration_boost" section spelling out exactly how many points
# D24/Jaimini's tie-breaking vote added -- never folded invisibly into an
# existing section.
# ============================================================================
D1_ARBITRATION_MARGIN = 3.0  # points, on the D1-subtotal (planetary_strength+house_support+role_placement display-value) scale -- see rationale above
D24_ARBITRATION_BOOST = 1.5  # multiplier applied to (d24_confirmation + jaimini_apparatus) display sum, for near-tied D1 streams only
_D24_JAIMINI_COMBINED_CAP = 18.0 + _JAIMINI_APPARATUS_CAP  # re-cap ceiling after boosting (matches d24_confirmation's own cap literal + jaimini_apparatus's cap constant)


def _apply_d24_arbitration_policy(streams: List[Dict[str, Any]], *, enabled: bool = True) -> Dict[str, Any]:
    """Cross-stream post-process implementing the D24/JAIMINI ARBITRATION
    POLICY documented in the comment block directly above. Called once per
    chart, after all 3 streams have been independently scored by
    score_stream() (which has no cross-stream visibility of its own -- this
    function is where that cross-stream comparison happens).

    Mutates each dict in `streams` in place (adds d1_subtotal/
    d24_jaimini_subtotal/d1_arbitration_applied fields to every stream;
    when arbitration fires, also appends a "d24_arbitration_boost" rubric
    section and recomputes score/normalized_score/score_rubric totals for
    the affected streams only) and re-sorts `streams` by the post-
    arbitration normalized_score. Returns the chart-level summary dict
    stored as the report's "d1_arbitration_detail".
    """
    def _section_display(stream: Dict[str, Any], name: str) -> float:
        for sec in stream["score_rubric"]["sections"]:
            if sec["section"] == name:
                return float(sec["display"])
        return 0.0

    per_stream = []
    for s in streams:
        d1_subtotal = (
            _section_display(s, "planetary_strength")
            + _section_display(s, "house_support")
            + _section_display(s, "role_placement")
        )
        d24j_subtotal = _section_display(s, "d24_confirmation") + _section_display(s, "jaimini_apparatus")
        per_stream.append({
            "stream_id": s["stream_id"], "label": s["label"],
            "d1_subtotal": round(d1_subtotal, 2), "d24_jaimini_subtotal": round(d24j_subtotal, 2),
        })
        s["d1_subtotal"] = round(d1_subtotal, 2)
        s["d24_jaimini_subtotal"] = round(d24j_subtotal, 2)

    if not enabled:
        for s in streams:
            s["d1_arbitration_applied"] = False
        return {
            "status": "disabled", "margin": D1_ARBITRATION_MARGIN, "boost": D24_ARBITRATION_BOOST,
            "per_stream": per_stream, "tied_streams": [],
            "note": "d24_arbitration_enabled=False -- pure pre-2026-07-24 additive behavior, unchanged.",
        }

    d1_leader = max(per_stream, key=lambda r: r["d1_subtotal"])
    tied_ids = {r["stream_id"] for r in per_stream
                if d1_leader["d1_subtotal"] - r["d1_subtotal"] <= D1_ARBITRATION_MARGIN}

    pre_ranked = sorted(streams, key=lambda r: -r["normalized_score"])
    pre_top = pre_ranked[0]["stream_id"] if pre_ranked else None

    if len(tied_ids) < 2:
        for s in streams:
            s["d1_arbitration_applied"] = False
        return {
            "status": "clear_d1_signal", "margin": D1_ARBITRATION_MARGIN, "boost": D24_ARBITRATION_BOOST,
            "per_stream": per_stream, "tied_streams": [], "d1_leader": d1_leader["stream_id"],
            "top_before": pre_top, "top_after": pre_top, "top_ranked_stream_changed": False,
            "note": (f"D1 subtotal clearly favors {d1_leader['label']} (no other stream within "
                     f"{D1_ARBITRATION_MARGIN:.1f} points) -- D24/Jaimini remain purely confirmatory/"
                     "additive, unchanged from pre-arbitration behavior."),
        }

    tied_labels = sorted(r["label"] for r in per_stream if r["stream_id"] in tied_ids)
    for s in streams:
        if s["stream_id"] in tied_ids:
            old_d24j = s["d24_jaimini_subtotal"]
            boosted_d24j = min(old_d24j * D24_ARBITRATION_BOOST, _D24_JAIMINI_COMBINED_CAP)
            delta = round(boosted_d24j - old_d24j, 2)
            boost_section = rubric_section(
                "d24_arbitration_boost", delta, _D24_JAIMINI_COMBINED_CAP * (D24_ARBITRATION_BOOST - 1.0),
                note=(f"D1 subtotal ({s['d1_subtotal']:.2f}) is within {D1_ARBITRATION_MARGIN:.1f} pts of the "
                      f"D1 leader ({d1_leader['label']}, {d1_leader['d1_subtotal']:.2f}) -- D1 alone is "
                      f"inconclusive among {', '.join(tied_labels)}, so d24_confirmation+jaimini_apparatus "
                      f"({old_d24j:.2f}) are boosted x{D24_ARBITRATION_BOOST:.1f} to {boosted_d24j:.2f} "
                      "(re-capped) to arbitrate specifically this tie -- see D24/JAIMINI ARBITRATION "
                      "POLICY comment block above compute_stream_determination()."),
            )
            s["score_rubric"]["sections"].append(boost_section)
            s["score_rubric"]["actual_total"] = round(s["score_rubric"]["actual_total"] + delta, 2)
            s["score_rubric"]["display_total"] = round(s["score_rubric"]["display_total"] + delta, 2)
            new_total = s["score_rubric"]["display_total"]
            s["score"] = round(clamp_score(new_total), 2)
            s["normalized_score"] = normalize_method_score(new_total, 100.0)
            s["raw_signed_score"] = round(new_total, 2)
            s["is_net_negative"] = new_total < 0.0
            s["signal_state"] = "NEGATIVE" if new_total < 0 else "NEUTRAL" if new_total == 0 else "POSITIVE"
            s["score_compression"]["raw_total_before_compression"] = round(new_total, 2)
            s["score_compression"]["compressed_score"] = s["score"]
            s["score_compression"]["compression_applied"] = new_total > 80.0
            s["trace"].append(
                f"D24_ARBITRATION: D1 was inconclusive among {', '.join(tied_labels)} -- "
                f"d24_confirmation+jaimini_apparatus boosted x{D24_ARBITRATION_BOOST:.1f} "
                f"({old_d24j:.2f} -> {boosted_d24j:.2f}), new total={new_total:.2f}."
            )
            s["d1_arbitration_applied"] = True
        else:
            s["d1_arbitration_applied"] = False

    post_ranked = sorted(streams, key=lambda r: -r["normalized_score"])
    streams[:] = post_ranked
    post_top = post_ranked[0]["stream_id"] if post_ranked else None

    tied_post = [r for r in post_ranked if r["stream_id"] in tied_ids]
    still_tied = (
        len(tied_post) >= 2
        and (tied_post[0]["normalized_score"] - tied_post[1]["normalized_score"]) <= _NEAR_TIE_MARGIN
    )
    status = "still_tied" if still_tied else "d24_arbitrated"

    return {
        "status": status, "margin": D1_ARBITRATION_MARGIN, "boost": D24_ARBITRATION_BOOST,
        "per_stream": per_stream, "tied_streams": tied_labels, "d1_leader": d1_leader["stream_id"],
        "top_before": pre_top, "top_after": post_top, "top_ranked_stream_changed": pre_top != post_top,
        "note": (
            f"D1 subtotal was inconclusive among {', '.join(tied_labels)} (all within "
            f"{D1_ARBITRATION_MARGIN:.1f} pts of leader {d1_leader['label']}) -- d24_confirmation + "
            f"jaimini_apparatus were boosted x{D24_ARBITRATION_BOOST:.1f} for those streams only to "
            "arbitrate the tie. "
            + (f"Top-ranked stream changed from {pre_top} to {post_top}. " if pre_top != post_top else
               f"Top-ranked stream ({post_top}) unchanged by arbitration. ")
            + ("Even after arbitration the leading near-tied streams remain within the engine's own "
               f"{_NEAR_TIE_MARGIN:.1f}-point close-call margin -- genuinely still a toss-up, not a "
               "confident single pick." if still_tied else
               "Arbitration produced a clear leader among the previously-tied set.")
        ),
    }



# ============================================================================
# CLASSICAL PRECEDENCE CHAIN (2026-07-24, replaces the D24/JAIMINI
# ARBITRATION POLICY above as the primary D1-vs-D24 tie resolver)
#
# CLASSICAL RATIONALE: the arbitration policy above resolves a D1-vs-D24
# disagreement with a single blunt mechanism (multiply D24+Jaimini's
# contribution by a fixed factor). Classical jyotish actually arbitrates
# genuine ties through a real PRECEDENCE ORDER of independent evidence
# classes, each one only consulted once the previous class has failed to
# separate the tied candidates:
#   1. VARGOTTAMA -- a planet occupying the SAME sign in D1 and the varga
#      under study (here D24/Siddhamsha) is doctrinally treated as giving
#      unusually reliable, reinforced testimony (Parashara/Phaladeepika) --
#      not "extra points", but a reason to trust that stream's D1 promise
#      more, because the education-varga independently reproduces it.
#   2. DIGNITY/STRENGTH -- among still-tied streams, whichever stream's key
#      significators sit in a stronger classical dignity state (exalted >
#      moolatrikona > own > friend-tier > neutral > enemy-tier >
#      debilitated) has the more capable testimony, per the ordinary rule
#      that a strong planet's promise outweighs a weak planet's.
#   3. JAIMINI AK/AmK -- among still-tied streams, alignment with the
#      Atmakaraka (soul-purpose significator) / Amatyakaraka (career
#      significator) and Karakamsha is Jaimini's own dedicated mechanism for
#      picking among otherwise-close candidates -- consulted third because
#      it is a smaller, more specialized apparatus than dignity/strength.
#   4. DASHA RELEVANCE -- among still-tied streams, whichever stream's key
#      significator is the CURRENTLY ACTIVE dasha lord (mahadasha, or the
#      active Jaimini chara-dasha sign's lord) is the stream most likely to
#      be operative RIGHT NOW for this native -- timing is classically the
#      final word when static strength alone cannot separate two
#      candidates.
# If all 4 stages fail to separate the tied streams, the tie is REAL and is
# reported honestly as "still_tied_after_full_chain" -- this function never
# invents a winner to force agreement with an external checker (explicit
# user instruction, 2026-07-24).
#
# SCOPE: only ever invoked among streams that are ALREADY tied on the full,
# final normalized_score (within _NEAR_TIE_MARGIN of the leader) -- i.e.
# after ordinary additive scoring (planetary_strength + house_support +
# role_placement + subject_evidence + d24_confirmation + relational_d1 +
# jaimini_apparatus [+ field_derived_evidence] - contraindications) has
# already been computed for all 3 streams. A stream with a clear outright
# lead is untouched ("d1_clear") -- this chain NEVER overrides a decisive
# score, it only adjudicates genuine near-ties, exactly like the arbitration
# policy above but through 4 real, inspectable classical mechanisms instead
# of one blunt multiplier.
#
# DOES NOT MUTATE SCORES: unlike _apply_d24_arbitration_policy, this
# function does not add points to any section -- it only decides the
# ORDER among already-tied streams (re-sorting `streams` in place when a
# stage resolves the tie) and records which real evidence resolved it.
# Fabricating points for a stage that produced no real evidence would
# violate the same "don't force a winner" instruction this function exists
# to honor.
#
# GATED behind classical_precedence_chain_enabled (default True on
# compute_stream_determination() -- this is now the DEFAULT tie-resolution
# mechanism; the old D24/JAIMINI ARBITRATION POLICY above is deprecated,
# left in place for A/B comparison/regression debugging, and now defaults
# to d24_arbitration_enabled=False so the two do not both fire on the same
# report).
# ============================================================================

_DIGNITY_STATE_SCORE = {
    "EXALTED": 6, "MOOLATRIKONA": 5, "OWN_SIGN": 4, "NEECHA_BHANGA": 3,
    "GREAT_FRIEND": 3, "FRIEND": 2, "NEUTRAL": 1, "ENEMY": 0,
    "GREAT_ENEMY": -1, "DEBILITATED": -2,
}
# Effective-strength values in this engine cluster around 1.0. Differences
# below 0.10 are not treated as a classical superiority claim; they remain
# tied and pass to Jaimini/timing. Without this tolerance, arbitrary decimal
# noise makes the later precedence stages unreachable in real charts.
_STRENGTH_TIE_TOLERANCE = 0.10


def _stream_key_significators(payload: Any, stream_id: str) -> List[str]:
    """Real, non-fabricated significator set for one stream: that stream's
    own classical signature planets (STREAM_META[stream_id]['planets'] --
    the same set driving planetary_strength/house_support everywhere else
    in this engine) unioned with the chart's universal educational role
    lords (5th/9th lord, Atmakaraka, Amatyakaraka) and Mercury/Jupiter
    (buddhi/guru karakas for any stream of learning). Deduplicated, empty
    entries dropped. Every stage below evaluates real D1/D24/dignity/dasha
    facts about exactly this set -- nothing here is invented per stream.
    """
    house_lords = getattr(payload, "house_lords", {}) or {}
    meta = STREAM_META.get(stream_id, {})
    sig = set(meta.get("planets", {}).keys())
    for extra in (
        house_lords.get("5", ""), house_lords.get("9", ""),
        getattr(payload, "atmakaraka", "") or "",
        getattr(payload, "amatyakaraka", "") or "",
        "Mercury", "Jupiter",
    ):
        if extra:
            sig.add(extra)
    return sorted(sig)


_D1_PRECEDENCE_SECTIONS = {
    "planetary_strength", "house_support", "role_placement",
    "subject_evidence", "relational_d1", "contraindications",
}
_RASI_SIGNS = (
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
)


def _d1_promise_score(stream: Dict[str, Any]) -> float:
    """D1-only promise used to decide whether refinement is permissible.

    D24, Jaimini, field-derived evidence and timing are intentionally absent:
    they refine an already-established rasi promise; they do not create it.
    """
    sections = (stream.get("score_rubric") or {}).get("sections") or []
    matching = [section for section in sections
                if section.get("section") in _D1_PRECEDENCE_SECTIONS]
    if not matching:
        # Compatibility for compact synthetic callers that predate rubric
        # sections. Production reports always take the explicit D1 path.
        return round(float(stream.get("normalized_score") or 0.0), 4)
    return round(sum(
        float(section.get("display") or 0.0)
        for section in matching
    ), 4)


def _stage1_vargottama(payload: Any, tied_ids: set, stream_by_id: Dict[str, Dict]) -> Dict[str, Any]:
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    divisional = getattr(payload, "divisional_charts", {}) or {}
    d24_signs = divisional.get("D24_siddhamsam", {}) or {}
    if not planets_d1 or not d24_signs:
        return {"resolved": False, "scores": {}, "detail": {},
                "note": "planets_d1 or D24_siddhamsam missing from payload -- vargottama check skipped, not fabricated."}
    scores: Dict[str, int] = {}
    detail: Dict[str, Any] = {}
    for sid in tied_ids:
        # Only a planet that actually signifies this stream may reinforce
        # that stream. Universal learning karakas/role lords are weighted
        # more strongly when they are also part of its signature, but are
        # never copied as identical evidence into every stream.
        own_planets = set((STREAM_META.get(sid, {}).get("planets") or {}).keys())
        house_lords = getattr(payload, "house_lords", {}) or {}
        hits = []
        weighted_score = 0
        for planet in own_planets:
            d1_info = planets_d1.get(planet)
            d1_sign = d1_info.get("sign", "") if isinstance(d1_info, dict) else ""
            d24_sign = d24_signs.get(planet, "")
            if d1_sign and d24_sign and d1_sign == d24_sign:
                hits.append(f"{planet}({d1_sign})")
                if planet in {house_lords.get("5"), house_lords.get("9")}:
                    weighted_score += 3
                elif planet in {"Mercury", "Jupiter"}:
                    weighted_score += 2
                else:
                    weighted_score += 1
        scores[sid] = weighted_score
        detail[sid] = {"vargottama_significators": hits, "weighted_reliability": weighted_score}
    if not scores:
        return {"resolved": False, "scores": scores, "detail": detail}
    max_score = max(scores.values())
    leaders = [sid for sid, v in scores.items() if v == max_score]
    resolved = max_score > 0 and len(leaders) == 1
    return {"resolved": resolved, "winner": leaders[0] if resolved else None,
            "scores": scores, "detail": detail, "leaders": leaders}


def _stage2_dignity(payload: Any, tied_ids: set) -> Dict[str, Any]:
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    if not planets_d1:
        return {"resolved": False, "scores": {}, "detail": {},
                "note": "planets_d1 missing -- dignity check skipped, not fabricated."}
    signs_by_planet = {p: (info.get("sign", "") if isinstance(info, dict) else "")
                        for p, info in planets_d1.items()}
    eff_strengths = getattr(payload, "eff_strengths", {}) or {}
    scores: Dict[str, float] = {}
    detail: Dict[str, Any] = {}
    for sid in tied_ids:
        weights = (STREAM_META.get(sid, {}).get("planets") or {})
        weighted = 0.0
        weight_total = 0.0
        states = []
        strengths = []
        for planet, planet_weight in weights.items():
            sign = signs_by_planet.get(planet, "")
            if not sign:
                continue
            degree = None
            info = planets_d1.get(planet)
            if isinstance(info, dict):
                degree = info.get("degree")
            state = dignity_state(planet, sign, degree, planet_signs=signs_by_planet)
            strength = eff_strengths.get(planet)
            if strength is not None:
                strength = float(strength)
                source = "effective_strength"
            else:
                # GAP-FIX (2026-07-24, CRITICAL bug #2): eff_strengths is on
                # a ~1-3 "shadbala/min_sv ratio" scale (jyotish/payload.py).
                # shadbala_virupas is a RAW ~0-450 virupa total -- comparing
                # it directly against eff_strengths (as the old code did)
                # let a planet with only a raw-shadbala fallback "win" this
                # stage purely from unit mismatch (e.g. Mars raw=300 beating
                # Venus eff_strength=2.0). Normalize onto the SAME reference
                # eff_strengths uses (_PLANET_MIN_SHADBALA) before it is
                # allowed to participate in this comparison at all.
                raw_virupas = info.get("shadbala_virupas") if isinstance(info, dict) else None
                if raw_virupas is not None:
                    min_v = _PLANET_MIN_SHADBALA.get(planet, 300.0)
                    strength = float(raw_virupas) / min_v if min_v else None
                    source = "raw_shadbala_normalized"
                else:
                    strength = None
                    source = None
                if strength is None:
                    # Neither a computed effective strength nor a raw
                    # shadbala total is available -- dignity state is the
                    # ONLY remaining signal, and only as a last resort; it
                    # is never allowed to silently replace a real strength
                    # value on a different, unnormalized scale.
                    strength = float(_DIGNITY_STATE_SCORE.get(state, 0)) / 6.0
                    source = "dignity_fallback"
            weighted += strength * float(planet_weight)
            weight_total += float(planet_weight)
            strengths.append(f"{planet}:{strength:.3f}({source})")
            states.append(f"{planet}:{state}")
        total = weighted / weight_total if weight_total else 0.0
        scores[sid] = round(total, 6)
        detail[sid] = {"computed_strengths": strengths, "dignity_states": states,
                       "weighted_strength": round(total, 6)}
    if not scores:
        return {"resolved": False, "scores": scores, "detail": detail}
    max_score = max(scores.values())
    leaders = [sid for sid, v in scores.items()
               if max_score - v <= _STRENGTH_TIE_TOLERANCE]
    resolved = len(leaders) == 1
    return {"resolved": resolved, "winner": leaders[0] if resolved else None,
            "scores": scores, "detail": detail, "leaders": leaders}


_SIGN_MODALITY = {
    "Aries": "movable", "Cancer": "movable", "Libra": "movable", "Capricorn": "movable",
    "Taurus": "fixed", "Leo": "fixed", "Scorpio": "fixed", "Aquarius": "fixed",
    "Gemini": "dual", "Virgo": "dual", "Sagittarius": "dual", "Pisces": "dual",
}
_NATURAL_MALEFICS = {"Saturn", "Mars", "Rahu", "Ketu", "Sun"}
_NATURAL_BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
_DUSTHANA_HOUSES = {6, 8, 12}


def _rasi_drishti_targets(sign: str) -> set:
    """Jaimini whole-sign (rasi) aspect targets of `sign`, per BPHS/Jaimini
    Sutras: movable signs aspect all fixed signs except the one immediately
    following them (the "adjacent" fixed sign); fixed signs aspect all
    movable signs except the one immediately preceding them; dual signs
    aspect the other two dual signs. Sign-arithmetic only -- no external
    helper for Jaimini rasi drishti was found under jyotish/ (searched
    drishti/aspect/sign_aspect; jyotish/astro.py's _get_planetary_aspects*
    are the unrelated graha/house-based Parashari aspect system), so this is
    implemented directly here per the classical rule.
    """
    if sign not in _RASI_SIGNS:
        return set()
    modality = _SIGN_MODALITY.get(sign)
    idx = _RASI_SIGNS.index(sign)
    if modality == "movable":
        adjacent_fixed = _RASI_SIGNS[(idx + 1) % 12]
        return {s for s in _RASI_SIGNS if _SIGN_MODALITY.get(s) == "fixed" and s != adjacent_fixed}
    if modality == "fixed":
        adjacent_movable = _RASI_SIGNS[(idx - 1) % 12]
        return {s for s in _RASI_SIGNS if _SIGN_MODALITY.get(s) == "movable" and s != adjacent_movable}
    if modality == "dual":
        return {s for s in _RASI_SIGNS if _SIGN_MODALITY.get(s) == "dual" and s != sign}
    return set()


def _stage3_jaimini_akamk(payload: Any, tied_ids: set) -> Dict[str, Any]:
    """Jaimini AK/AmK Stage 3 -- extended (2026-07-24) with 5 additional
    classical checks beyond the original AK/AmK-placement + Karakamsha-lord
    baseline (checks 0a/0b/0c below, kept unchanged for continuity):

      1. 10th-from-Karakamsha occupants/lord (classical Jaimini "career from
         Karakamsha" house).
      2. Rasi-drishti (Jaimini whole-sign aspect) onto Karakamsha and its
         10th from other planets.
      3. AK-AmK sambandha (conjunction or mutual rasi-drishti) -- strengthens
         AmK's signal when present; surfaced as an explicit, confidence-
         lowering contradiction when AK/AmK point to different streams with
         no sambandha.
      4. AmK's own dignity/strength (jyotish/dignity.py, same source Stage 2
         uses) scales AmK's contribution instead of a flat bonus.
      5. Affliction on AmK/Karakamsha (unmitigated malefic conjunction/
         aspect, or AmK in a dusthana from Karakamsha) reduces Stage 3
         confidence and is surfaced explicitly.

    `jaimini_depth_detail` on the returned dict documents which checks fired
    and how each nudged the outcome -- nothing here is a black box.
    """
    ak = getattr(payload, "atmakaraka", "") or ""
    amk = getattr(payload, "amatyakaraka", "") or ""
    karakamsha = (getattr(payload, "karakamsha", "") or
                   getattr(payload, "karakamsha_sign", "") or "")
    karakamsha_lord = _SIGN_LORD.get(karakamsha, "") if karakamsha else ""
    divisional = getattr(payload, "divisional_charts", {}) or {}
    d9_signs = divisional.get("D9_navamsha", {}) or {}
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    eff_strengths = getattr(payload, "eff_strengths", {}) or {}
    if not ak and not amk and not karakamsha_lord:
        return {"resolved": False, "scores": {}, "detail": {},
                "note": "atmakaraka/amatyakaraka/karakamsha all unavailable -- Jaimini stage skipped, not fabricated."}

    # ---- shared (not per-stream) Jaimini depth facts, computed once ----
    jaimini_depth: Dict[str, Any] = {"checks_run": [], "checks_skipped": []}

    tenth_from_karakamsha = ""
    if karakamsha in _RASI_SIGNS:
        tenth_from_karakamsha = _RASI_SIGNS[(_RASI_SIGNS.index(karakamsha) + 9) % 12]
        jaimini_depth["checks_run"].append("10th_from_karakamsha")
        jaimini_depth["tenth_from_karakamsha_sign"] = tenth_from_karakamsha
    else:
        jaimini_depth["checks_skipped"].append("10th_from_karakamsha (karakamsha sign unavailable)")

    tenth_lord = _SIGN_LORD.get(tenth_from_karakamsha, "") if tenth_from_karakamsha else ""
    tenth_occupants_d1 = [p for p, info in planets_d1.items()
                          if isinstance(info, dict) and info.get("sign") == tenth_from_karakamsha]

    # rasi-drishti: which planets (by D1 sign) aspect Karakamsha or its 10th
    aspecting_planets: List[str] = []
    if karakamsha in _RASI_SIGNS or tenth_from_karakamsha in _RASI_SIGNS:
        jaimini_depth["checks_run"].append("rasi_drishti")
        for planet, info in planets_d1.items():
            p_sign = info.get("sign", "") if isinstance(info, dict) else ""
            if not p_sign or p_sign in (karakamsha, tenth_from_karakamsha):
                continue
            targets = _rasi_drishti_targets(p_sign)
            if karakamsha in targets or tenth_from_karakamsha in targets:
                aspecting_planets.append(planet)
        jaimini_depth["rasi_drishti_aspecting_planets"] = aspecting_planets
    else:
        jaimini_depth["checks_skipped"].append("rasi_drishti (karakamsha/10th sign unavailable)")

    # AK-AmK sambandha
    sambandha = None
    if ak and amk:
        jaimini_depth["checks_run"].append("ak_amk_sambandha")
        ak_sign = d9_signs.get(ak, "") or (planets_d1.get(ak, {}) or {}).get("sign", "")
        amk_sign = d9_signs.get(amk, "") or (planets_d1.get(amk, {}) or {}).get("sign", "")
        if ak_sign and amk_sign:
            if ak_sign == amk_sign:
                sambandha = "conjunction"
            elif amk_sign in _rasi_drishti_targets(ak_sign) or ak_sign in _rasi_drishti_targets(amk_sign):
                sambandha = "mutual_rasi_drishti"
        jaimini_depth["ak_amk_sambandha"] = sambandha
    else:
        jaimini_depth["checks_skipped"].append("ak_amk_sambandha (AK or AmK unavailable)")

    # AmK dignity/strength -- reuse the same source/scale Stage 2 uses.
    amk_confidence = 1.0
    amk_dignity_state = None
    if amk:
        jaimini_depth["checks_run"].append("amk_dignity_strength")
        amk_sign_d1 = (planets_d1.get(amk, {}) or {}).get("sign", "") if isinstance(planets_d1.get(amk), dict) else ""
        signs_by_planet = {p: (info.get("sign", "") if isinstance(info, dict) else "")
                            for p, info in planets_d1.items()}
        if amk_sign_d1:
            degree = (planets_d1.get(amk, {}) or {}).get("degree")
            amk_dignity_state = dignity_state(amk, amk_sign_d1, degree, planet_signs=signs_by_planet)
            strength = eff_strengths.get(amk)
            if strength is not None:
                # eff_strengths clusters ~1-3; normalize to a 0.3-1.3-ish
                # confidence multiplier so a weak AmK genuinely damps its
                # own signal instead of contributing full flat credit.
                amk_confidence = max(0.3, min(1.3, float(strength) / 2.0))
            else:
                amk_confidence = max(0.3, float(_DIGNITY_STATE_SCORE.get(amk_dignity_state, 0)) / 6.0 + 0.5)
        jaimini_depth["amk_dignity_state"] = amk_dignity_state
        jaimini_depth["amk_confidence_multiplier"] = round(amk_confidence, 3)
    else:
        jaimini_depth["checks_skipped"].append("amk_dignity_strength (AmK unavailable)")

    # Affliction on AmK/Karakamsha: unmitigated malefic conjunction/aspect,
    # or AmK placed in a dusthana (6/8/12) from Karakamsha.
    afflicted = False
    affliction_notes: List[str] = []
    if amk or karakamsha:
        jaimini_depth["checks_run"].append("affliction_check")
        amk_sign_d1 = (planets_d1.get(amk, {}) or {}).get("sign", "") if amk and isinstance(planets_d1.get(amk), dict) else ""
        for target_label, target_planet, target_sign in (
            ("AmK", amk, amk_sign_d1), ("Karakamsha", "", karakamsha),
        ):
            if not target_sign:
                continue
            conjunct_malefics = {p for p, info in planets_d1.items()
                                  if p != target_planet and isinstance(info, dict)
                                  and info.get("sign") == target_sign and p in _NATURAL_MALEFICS}
            conjunct_benefics = {p for p, info in planets_d1.items()
                                  if p != target_planet and isinstance(info, dict)
                                  and info.get("sign") == target_sign and p in _NATURAL_BENEFICS}
            aspecting_malefics = {p for p, info in planets_d1.items()
                                   if isinstance(info, dict) and p in _NATURAL_MALEFICS
                                   and target_sign in _rasi_drishti_targets(info.get("sign", ""))}
            malefic_hit = conjunct_malefics | aspecting_malefics
            if malefic_hit and not conjunct_benefics:
                afflicted = True
                affliction_notes.append(
                    f"{target_label} ({target_sign}) afflicted by unmitigated malefic "
                    f"conjunction/rasi-drishti from {', '.join(sorted(malefic_hit))}")
        if karakamsha in _RASI_SIGNS and amk_sign_d1 in _RASI_SIGNS:
            house_from_karakamsha = ((_RASI_SIGNS.index(amk_sign_d1) - _RASI_SIGNS.index(karakamsha)) % 12) + 1
            if house_from_karakamsha in _DUSTHANA_HOUSES:
                afflicted = True
                affliction_notes.append(f"AmK is in dusthana H{house_from_karakamsha} from Karakamsha")
        jaimini_depth["afflicted"] = afflicted
        jaimini_depth["affliction_notes"] = affliction_notes
    else:
        jaimini_depth["checks_skipped"].append("affliction_check (AmK/Karakamsha unavailable)")

    affliction_confidence = 0.6 if afflicted else 1.0

    scores: Dict[str, float] = {}
    detail: Dict[str, Any] = {}
    stream_pointed_by: Dict[str, set] = {"AK": set(), "AmK": set()}
    for sid in tied_ids:
        meta = STREAM_META.get(sid, {})
        own_planets = set(meta.get("planets", {}).keys())
        hits = []
        pts = 0.0
        for planet, base, role in ((amk, 3, "AmK"), (ak, 2, "AK")):
            if not planet or planet not in own_planets:
                continue
            stream_pointed_by[role].add(sid)
            placement = 0
            planet_sign = d9_signs.get(planet, "")
            if karakamsha in _RASI_SIGNS and planet_sign in _RASI_SIGNS:
                placement = ((_RASI_SIGNS.index(planet_sign) - _RASI_SIGNS.index(karakamsha)) % 12) + 1
            component = float(base + 2) if placement in {1, 5, 9, 10} else float(base)
            if placement in {1, 5, 9, 10}:
                hits.append(f"{role}={planet} is a stream significator placed H{placement} from Karakamsha")
            else:
                suffix = f", H{placement} from Karakamsha" if placement else ""
                hits.append(f"{role}={planet} is a stream significator{suffix}")
            if role == "AmK":
                # CHECK 4/5: scale AmK's contribution by its real dignity/
                # strength and dampen it if AmK/Karakamsha is afflicted --
                # a flat dignity-blind bonus is no longer applied.
                component = component * amk_confidence * affliction_confidence
            pts += component
        if karakamsha_lord and karakamsha_lord in own_planets:
            pts += 1
            hits.append(f"Karakamsha ({karakamsha}) lord {karakamsha_lord} is a {meta.get('label', sid)} signature planet")
        # CHECK 1: 10th-from-Karakamsha occupants/lord.
        if tenth_lord and tenth_lord in own_planets:
            pts += 1.5
            hits.append(f"10th-from-Karakamsha ({tenth_from_karakamsha}) lord {tenth_lord} "
                        f"is a {meta.get('label', sid)} signature planet")
        for occ in tenth_occupants_d1:
            if occ in own_planets:
                pts += 1.0
                hits.append(f"{occ} occupies the 10th-from-Karakamsha sign ({tenth_from_karakamsha}) "
                            f"and is a {meta.get('label', sid)} signature planet")
        # CHECK 2: rasi-drishti onto Karakamsha/its 10th from other planets.
        for asp_planet in aspecting_planets:
            if asp_planet in own_planets:
                pts += 1.0
                hits.append(f"{asp_planet} casts rasi-drishti (Jaimini sign aspect) onto "
                            f"Karakamsha/its 10th house and is a {meta.get('label', sid)} signature planet")
        scores[sid] = round(pts, 3)
        detail[sid] = {"jaimini_hits": hits, "jaimini_score": round(pts, 3)}

    # CHECK 3: AK-AmK contradiction surfacing (does not change scores --
    # it is an honesty/confidence signal on the stage as a whole, per spec:
    # "lower Stage 3 confidence, don't arbitrarily pick one").
    ak_streams = stream_pointed_by["AK"]
    amk_streams = stream_pointed_by["AmK"]
    contradiction = bool(ak_streams and amk_streams and not (ak_streams & amk_streams) and not sambandha)
    if sambandha and ak_streams and amk_streams and (ak_streams & amk_streams):
        jaimini_depth["ak_amk_agreement_note"] = (
            f"AK and AmK both signify the same stream and have sambandha ({sambandha}) -- "
            "mutually reinforcing, not contradictory.")
    jaimini_depth["ak_amk_contradiction"] = contradiction
    if contradiction:
        jaimini_depth["ak_amk_contradiction_note"] = (
            "AK and AmK point to different streams with no sambandha (no conjunction and no "
            "mutual rasi-drishti) between them -- a genuine internal Jaimini contradiction for "
            "this chart. Stage 3 confidence is lowered rather than arbitrarily picking one.")

    if not scores:
        return {"resolved": False, "scores": scores, "detail": detail,
                "jaimini_depth_detail": jaimini_depth}
    max_score = max(scores.values())
    leaders = [sid for sid, v in scores.items() if v == max_score]
    resolved = max_score > 0 and len(leaders) == 1
    # A genuine AK/AmK contradiction with no sambandha means Stage 3's
    # evidence is internally conflicted -- it should not be allowed to
    # resolve the tie on the strength of a thin score margin alone.
    if contradiction and resolved and max_score < 4.0:
        resolved = False
        jaimini_depth["resolution_suppressed_by_contradiction"] = True
    return {"resolved": resolved, "winner": leaders[0] if resolved else None,
            "scores": scores, "detail": detail, "leaders": leaders,
            "jaimini_depth_detail": jaimini_depth}


def _resolve_as_of_date(as_of_date: Any) -> "_date":
    """Normalize an as_of_date argument (date, ISO string, or None) into a
    real datetime.date. None means "not explicitly supplied" -- callers
    default to date.today() only at this single point, so the actual date
    used is always traceable (see evaluation_as_of_date on the report) and
    the SAME explicit date always reproduces the SAME dasha-stage result
    (GAP-FIX 2026-07-24, dasha as_of_date reproducibility).
    """
    from datetime import date as _date
    if as_of_date is None:
        return _date.today()
    if isinstance(as_of_date, _date):
        return as_of_date
    return _date.fromisoformat(str(as_of_date))


def _stage4_dasha_relevance(payload: Any, tied_ids: set, as_of_date: Any = None) -> Dict[str, Any]:
    dasha_sequence = getattr(payload, "dasha_sequence", None) or []
    current_age = getattr(payload, "current_age", None)
    lagna_sign = getattr(payload, "lagna_sign", "") or ""
    planets_d1 = getattr(payload, "planets_d1", {}) or {}
    if not dasha_sequence or current_age is None:
        return {"resolved": False, "scores": {}, "detail": {},
                "note": "dasha_sequence or current_age unavailable -- dasha stage skipped, not fabricated."}
    try:
        current_age_f = float(current_age)
    except (TypeError, ValueError):
        return {"resolved": False, "scores": {}, "detail": {},
                "note": "current_age not numeric -- dasha stage skipped, not fabricated."}
    active_md_lord = _get_active_dasha_lord(dasha_sequence, current_age_f)
    active_ad_lord = ""
    imminent_md_lord = ""
    # Prefer the fully dated Vimshottari sequence when present: it contains
    # actual bhukti windows. The age-only sequence remains the MD fallback.
    from datetime import date as _date
    dated_sequence = getattr(payload, "vimshottari_dasha_full", None) or []
    today = _resolve_as_of_date(as_of_date)
    for md in dated_sequence:
        try:
            start = _date.fromisoformat(str(md.get("start_date")))
            end = _date.fromisoformat(str(md.get("end_date")))
        except (TypeError, ValueError):
            continue
        if start <= today < end:
            active_md_lord = md.get("planet", "") or active_md_lord
            for ad in md.get("antardashas", []) or []:
                try:
                    ad_start = _date.fromisoformat(str(ad.get("start_date")))
                    ad_end = _date.fromisoformat(str(ad.get("end_date")))
                except (TypeError, ValueError):
                    continue
                if ad_start <= today < ad_end:
                    active_ad_lord = ad.get("planet", "") or ""
                    break
            break
    for md in dasha_sequence:
        try:
            start_age = float(md.get("start_age"))
        except (TypeError, ValueError):
            continue
        if current_age_f < start_age <= current_age_f + 3.0:
            imminent_md_lord = md.get("lord", "") or md.get("md_planet", "")
            break
    active_chara_lord = ""
    if lagna_sign and planets_d1:
        active_chara_sign = _get_active_chara_dasha_sign(lagna_sign, current_age_f, planets_d1)
        active_chara_lord = _SIGN_LORD.get(active_chara_sign, "") if active_chara_sign else ""
    if not active_md_lord and not active_chara_lord:
        return {"resolved": False, "scores": {}, "detail": {},
                "note": "no active mahadasha/chara-dasha lord could be determined -- dasha stage skipped, not fabricated."}
    scores: Dict[str, int] = {}
    detail: Dict[str, Any] = {}
    for sid in tied_ids:
        meta = STREAM_META.get(sid, {})
        own_planets = set(meta.get("planets", {}).keys())
        hits = []
        pts = 0
        if active_md_lord and active_md_lord in own_planets:
            pts += 3
            hits.append(f"active mahadasha lord {active_md_lord} is a {meta.get('label', sid)} signature planet")
        if active_ad_lord and active_ad_lord in own_planets:
            pts += 2
            hits.append(f"active antardasha/bhukti lord {active_ad_lord} is a {meta.get('label', sid)} signature planet")
        if active_chara_lord and active_chara_lord in own_planets:
            pts += 1
            hits.append(f"active chara-dasha sign lord {active_chara_lord} is a {meta.get('label', sid)} signature planet")
        if imminent_md_lord and imminent_md_lord in own_planets:
            pts += 1
            hits.append(f"imminent mahadasha lord {imminent_md_lord} is a {meta.get('label', sid)} signature planet")
        scores[sid] = pts
        detail[sid] = {"dasha_hits": hits, "dasha_score": pts}
    if not scores:
        return {"resolved": False, "scores": scores, "detail": detail,
                "evaluation_as_of_date": today.isoformat()}
    max_score = max(scores.values())
    leaders = [sid for sid, v in scores.items() if v == max_score]
    resolved = max_score > 0 and len(leaders) == 1
    return {"resolved": resolved, "winner": leaders[0] if resolved else None,
            "scores": scores, "detail": detail, "leaders": leaders,
            "evaluation_as_of_date": today.isoformat()}


def _apply_classical_precedence_chain(payload: Any, streams: List[Dict[str, Any]], *, enabled: bool = True,
                                       as_of_date: Any = None) -> Dict[str, Any]:
    """Cross-stream post-process implementing the CLASSICAL PRECEDENCE CHAIN
    documented in the comment block above. Called once per chart, AFTER
    streams have been sorted by normalized_score (and after the deprecated
    D24/JAIMINI arbitration policy, if that was separately enabled). Only
    re-sorts `streams` (never mutates any score/rubric section) -- see
    module note above for why.

    Returns the chart-level detail dict stored as the report's
    "precedence_chain_detail"; the report's top-level
    "precedence_chain_resolution_stage" is derived from this dict's
    "resolution_stage" key.

    GAP-FIX (2026-07-24, CRITICAL bug #1): this function used to reorder
    `streams` in place so streams[0] became "whichever stream the chain
    picked." Every downstream reader that assumed streams[0] == the
    highest normalized_score (top_score / close-call / low-support checks,
    disagreement_ledger's final_leader, top_ranked_stream) silently started
    reading the PRECEDENCE winner instead -- producing reports where the
    recommended stream displayed a lower score than a stream listed below
    it. `streams` is no longer reordered here; it stays in the pure
    normalized_score-descending order the caller already sorted it into.
    The precedence chain's pick is returned via this dict's "winner" key
    only -- callers must read that explicitly (surfaced on the report as
    "precedence_decision"/"recommended_stream") rather than inferring it
    from list order.
    """
    # GAP-FIX (2026-07-24, dasha as_of_date reproducibility): resolved once
    # here and stamped onto every returned detail dict as
    # "evaluation_as_of_date" so a saved report always records exactly what
    # calendar date its Stage 4 dasha-relevance evaluation used -- re-running
    # the SAME chart with the SAME explicit as_of_date must reproduce
    # byte-identical dasha-stage output; only the None (unsupplied) default
    # is wall-clock-dependent.
    resolved_as_of_date = _resolve_as_of_date(as_of_date).isoformat()

    if not enabled or not streams:
        return {"resolution_stage": "disabled" if not enabled else "no_streams",
                "note": "classical_precedence_chain_enabled=False -- chain not run." if not enabled else "no streams to evaluate",
                "tied_streams": [], "stages": {}, "evaluation_as_of_date": resolved_as_of_date}

    stream_by_id = {s["stream_id"]: s for s in streams}
    d1_scores = {sid: _d1_promise_score(stream) for sid, stream in stream_by_id.items()}
    d1_leader = max(d1_scores, key=d1_scores.get)
    leader_score = d1_scores[d1_leader]
    tied_ids = {sid for sid, score in d1_scores.items()
                if leader_score - score <= _NEAR_TIE_MARGIN}

    # GAP-FIX (2026-07-24, CRITICAL bug #1): this used to re-sort `streams`
    # in place (tied-D1-candidates first, by d1 promise score) as the
    # "tree-before-fruit" gate. `streams` is now kept in pure
    # normalized_score order throughout; the D1-candidate gate is enforced
    # purely through tied_ids/d1_scores (used below and by the stage
    # functions), never by mutating list order. d1_scores is exposed on the
    # returned detail dict ("d1_promise_scores") for any caller that wants
    # the D1-only candidate ranking explicitly.

    if len(tied_ids) < 2:
        return {
            "resolution_stage": "d1_clear", "tied_streams": [], "stages": {},
            "winner": d1_leader, "d1_promise_scores": d1_scores,
            "evaluation_as_of_date": resolved_as_of_date,
            "note": (f"{stream_by_id[d1_leader]['label']} has a clear D1-only promise lead "
                     f"({leader_score:.2f}; no other stream within {_NEAR_TIE_MARGIN:.1f}) -- "
                     "D24 cannot create or overturn the underlying promise."),
        }

    tied_labels = sorted(stream_by_id[sid]["label"] for sid in tied_ids)
    stages_run: Dict[str, Any] = {}
    stage_order = [
        ("vargottama", _stage1_vargottama),
        ("dignity_strength", _stage2_dignity),
        ("jaimini_akamk", _stage3_jaimini_akamk),
        ("dasha_relevance", _stage4_dasha_relevance),
    ]
    current_tied = set(tied_ids)
    for stage_name, stage_fn in stage_order:
        if stage_name == "vargottama":
            result = stage_fn(payload, current_tied, stream_by_id)
        elif stage_name == "dasha_relevance":
            result = stage_fn(payload, current_tied, as_of_date)
        else:
            result = stage_fn(payload, current_tied)
        stages_run[stage_name] = result
        if result.get("resolved"):
            winner_id = result["winner"]
            winner_entry = stream_by_id[winner_id]
            # GAP-FIX (2026-07-24, CRITICAL bug #1): `streams` is
            # deliberately NOT reordered here anymore -- it stays in pure
            # normalized_score order. The precedence winner is communicated
            # only through this dict's "winner" key.
            return {
                "resolution_stage": stage_name,
                "tied_streams": tied_labels,
                "winner": winner_id,
                "winner_label": winner_entry["label"],
                "d1_promise_scores": d1_scores,
                "stages": stages_run,
                "evaluation_as_of_date": resolved_as_of_date,
                "note": (f"D1-promise tie among {', '.join(tied_labels)} resolved at refinement stage "
                         f"'{stage_name}' -- see stages['{stage_name}'] for the real evidence used."),
            }
        # Narrow to the leaders of this stage (if the stage produced any
        # non-empty scores) before trying the next stage -- a stage that
        # could not separate ANY of the tied streams leaves the full tied
        # set for the next stage; a stage that separated some but not all
        # (e.g. 3-way tied, 2 remain tied after this stage) narrows the
        # set genuinely, which is the whole point of a precedence chain.
        leaders = result.get("leaders")
        if leaders and len(leaders) >= 2:
            current_tied = set(leaders)
        # else: leave current_tied unchanged (stage had no discriminating
        # evidence at all -- narrowing to a meaningless leaders=[] would
        # incorrectly drop legitimate candidates).

    return {
        "resolution_stage": "still_tied_after_full_chain",
        "tied_streams": tied_labels,
        "winner": None,
        "evaluation_as_of_date": resolved_as_of_date,
        "d1_promise_scores": d1_scores,
        "stages": stages_run,
        "note": (
            f"{', '.join(tied_labels)} remain within {_NEAR_TIE_MARGIN:.1f} points of each other "
            "even after vargottama, dignity/strength, Jaimini AK/AmK, and dasha-relevance were all "
            "checked -- this is a genuine astrological tie for this chart, not a gap in the chain. "
            "Reported honestly rather than forcing a winner."
        ),
    }


def compute_stream_determination(
    payload: Any, *, include_field_derived_evidence: bool = False,
    field_engine_snapshot: Any = None, d24_arbitration_enabled: bool = False,
    classical_precedence_chain_enabled: bool = True,
    as_of_date: Any = None,
) -> Dict[str, Any]:
    """Main entry: rank subjects within each stream FIRST, then score all 3
    streams (folding that subject-level evidence in), so the dominant-stream
    decision considers every core subject and each stream's best non-shared
    elective -- not just the stream's own signature planets/houses in
    isolation.

    `include_field_derived_evidence=True` (default False -- experimental,
    off by default) additionally runs Field_Determination's adult engine
    ONCE per chart (see field_derived_stream.py) and folds its result into
    an 8th, small-capped rubric section for all 3 streams. Off by default
    both because it is the newest, least-regression-tested section, and
    because it is DERIVED_CORRELATED evidence (reuses the same underlying
    chart facts through the adult engine's lens), not independent evidence.

    `field_engine_snapshot=` lets a caller (early_age_stream_engine.py) pass
    in an adult-engine snapshot it already fetched for cross_validate.py in
    the same CLI run, so this doesn't trigger a second, redundant adult-
    engine run for the same chart. Ignored if include_field_derived_evidence
    is False.

    `d24_arbitration_enabled=True` (deprecated; default off) applies the D24/JAIMINI
    ARBITRATION POLICY documented in the large comment block directly above
    this function -- D24/Jaimini get extra, visible weight ONLY to break a
    genuine D1-inconclusive tie between candidate streams; a clear D1 leader
    is left untouched. Pass False to restore the pre-2026-07-24 pure-
    additive scoring exactly (e.g. for A/B comparison or regression
    debugging) -- see _apply_d24_arbitration_policy().

    `as_of_date=` (a datetime.date, ISO date string, or None) is the
    calendar date the classical precedence chain's Stage 4 (dasha-relevance)
    check treats as "today" when locating the active mahadasha/antardasha
    window. None (the default) resolves to date.today() at call time, same
    as before this parameter existed. Passing an explicit date makes the
    dasha stage (and therefore precedence_chain_detail/
    precedence_chain_resolution_stage) fully reproducible run-to-run --
    see _resolve_as_of_date()/_stage4_dasha_relevance(). The resolved value
    is echoed back on the report as "evaluation_as_of_date".
    """
    planet_strengths = _stream_planet_strengths(payload)

    # Run the (optional) adult-engine bridge ONCE per chart, not once per
    # stream -- three separate adult-engine runs for the same chart would be
    # both wasteful and a source of drift if anything about the run were
    # ever non-deterministic. Reuses field_engine_snapshot if the caller
    # already fetched one (see docstring above).
    field_derived_evidence = None
    if include_field_derived_evidence:
        from .field_derived_stream import safe_derive_stream_marks
        field_derived_evidence = safe_derive_stream_marks(payload, snapshot=field_engine_snapshot)

    # GAP-FIX (audit #45): the age gate previously lived ONLY in
    # early_age_stream_engine.py's is_eligible()/run_for_chart_file() CLI
    # path -- any caller that constructs a payload and calls
    # compute_stream_determination() directly (skipping that CLI layer
    # entirely, e.g. a future batch job or another script importing this
    # module) got no warning at all that it was scoring an adult chart
    # through the under-15 engine. This is a second, independent check at
    # the actual scoring entry point itself -- advisory only (does not
    # block the calculation, since forced/test runs are a legitimate use
    # case handled by the CLI layer's own forced_override/eligibility_status
    # stamping), but now no direct caller of this function can miss it.
    age_routing_note = None
    _current_age = getattr(payload, "current_age", None)
    input_quality_issues: List[str] = []
    if _current_age is None or str(_current_age).strip() == "":
        input_quality_issues.append("current_age_missing")
    else:
        try:
            if not math.isfinite(float(_current_age)) or float(_current_age) <= 0:
                input_quality_issues.append("current_age_invalid")
        except (TypeError, ValueError):
            input_quality_issues.append("current_age_invalid")
    for field_name in ("planet_house", "house_lords", "d24_house_lords", "d24_house_occupancy"):
        if not isinstance(getattr(payload, field_name, None), dict):
            input_quality_issues.append(f"{field_name}_malformed")
    if _current_age is not None:
        try:
            if float(_current_age) >= AGE_THRESHOLD_YEARS:
                age_routing_note = (
                    f"current_age={_current_age} is >= {AGE_THRESHOLD_YEARS} -- this chart is "
                    "outside this engine's normal under-15 scope. If this call did not go "
                    "through early_age_stream_engine.py's CLI (which stamps forced_override/"
                    "eligibility_status for exactly this case), the caller should treat this "
                    "result as a test/debug run, not a normal recommendation."
                )
        except (TypeError, ValueError):
            pass

    streams = []
    for stream_id in STREAM_META:
        subjects_ranked = score_subjects(stream_id, planet_strengths)
        entry = score_stream(
            payload, stream_id, planet_strengths, subjects_ranked,
            field_derived_evidence=field_derived_evidence,
        )
        # _planet_weights is an internal-only field (see score_subjects) used
        # by _subject_evidence_section's circularity discount -- strip it
        # before this list becomes part of the public report contract.
        entry["subjects"] = [{k: v for k, v in s.items() if not k.startswith("_")} for s in subjects_ranked]
        streams.append(entry)

    streams.sort(key=lambda r: -r.get("normalized_score", 0.0))

    # GAP-FIX (2026-07-24, explicit user decision, "Option 1"): apply the
    # D24/JAIMINI ARBITRATION POLICY (see the large comment block above this
    # function) now that all 3 streams have been independently scored --
    # this is the earliest point at which cross-stream comparison (needed to
    # know whether D1 is actually inconclusive) is possible. Re-sorts
    # `streams` in place if arbitration changes any stream's normalized_score,
    # so every downstream computation below (evidence_completeness,
    # is_close_call, disagreement_ledger, dominant_stream, ...) already sees
    # the post-arbitration ranking.
    d1_arbitration_detail = _apply_d24_arbitration_policy(streams, enabled=d24_arbitration_enabled)
    d1_arbitration_status = d1_arbitration_detail["status"]

    # GAP-FIX (2026-07-24): CLASSICAL PRECEDENCE CHAIN -- see the large
    # comment block above _apply_classical_precedence_chain(). Runs AFTER
    # the (now deprecated, default-off) D24/JAIMINI arbitration policy above
    # so it sees whatever ranking is currently in effect; with
    # d24_arbitration_enabled left at its new default (False) the two never
    # both fire on the same report.
    #
    # GAP-FIX (2026-07-24, CRITICAL bug #1): `streams` is NO LONGER
    # reordered by this call -- it stays in pure normalized_score-descending
    # order (numeric_rank). The classical chain's pick is read explicitly
    # below as `precedence_decision`/`recommended_stream`, kept as separate,
    # named fields instead of being implied by list order. See the
    # docstring on _apply_classical_precedence_chain() for the full
    # rationale (this was CRITICAL bug #1 from the 2026-07-24 external
    # review: recommended_stream could previously display a LOWER
    # normalized_score than a stream ranked below it, and top_score/
    # close-call/low-support logic further down was silently reading the
    # precedence winner's score instead of the actual numeric leader's).
    precedence_chain_detail = _apply_classical_precedence_chain(
        payload, streams, enabled=classical_precedence_chain_enabled,
        as_of_date=as_of_date)
    precedence_chain_resolution_stage = precedence_chain_detail["resolution_stage"]
    evaluation_as_of_date = precedence_chain_detail.get("evaluation_as_of_date")

    # `streams` is guaranteed to be in pure normalized_score-descending
    # order at this point (see GAP-FIX above) -- numeric_rank is just that
    # order's stream_ids, named explicitly so nothing downstream has to
    # infer "top score" from list position.
    numeric_rank = [s["stream_id"] for s in streams]
    # d1_candidate_rank: the D1-only promise ranking the precedence chain
    # itself computed (per stream, before D24/Jaimini/dasha refinement) --
    # exposed explicitly rather than only implicitly driving tied_ids
    # inside _apply_classical_precedence_chain.
    _d1_promise_scores = precedence_chain_detail.get("d1_promise_scores") or {}
    d1_candidate_rank = (
        [sid for sid, _ in sorted(_d1_promise_scores.items(), key=lambda kv: -kv[1])]
        if _d1_promise_scores else list(numeric_rank)
    )
    # precedence_decision: the stream the classical chain actually selected
    # (None if the chain left a genuine tie unresolved, or never ran).
    precedence_decision = precedence_chain_detail.get("winner")
    # recommended_stream: the pick actually shown to the user as "the"
    # recommendation. Equals precedence_decision when the chain resolved a
    # decision; falls back to the numeric leader when the chain is
    # disabled, saw no streams, or genuinely could not resolve a tie. This
    # is NOT guaranteed to be the highest normalized_score -- see
    # numeric_rank for the raw score ordering, and read
    # precedence_chain_resolution_stage/precedence_chain_detail for why.
    recommended_stream = precedence_decision if precedence_decision else (
        numeric_rank[0] if numeric_rank else None
    )

    # Evidence completeness is deliberately separate from score. A high score
    # assembled from a thin payload must not be presented as a confident result.
    strength_coverage = sum(v is not None for v in planet_strengths.values()) / len(_ALL_PLANETS)
    has_houses = bool(getattr(payload, "planet_house", {}) and getattr(payload, "house_lords", {}))
    has_d24 = bool(getattr(payload, "d24_house_lords", {}) and getattr(payload, "d24_house_occupancy", {}))
    role_fields = (
        bool(getattr(payload, "atmakaraka", "")),
        bool(getattr(payload, "amatyakaraka", "")),
        bool(getattr(payload, "h10_lord", "") or (getattr(payload, "house_lords", {}) or {}).get("10")),
    )
    # Partial role data should contribute partial evidence rather than being
    # treated as equivalent to a fully populated AK/AmK/H10 payload.
    role_coverage = sum(role_fields) / len(role_fields)
    has_birth_precision = _calculation_identity(payload)["birth_time_precision"] == "EXACT_RECORDED"
    evidence_completeness = (
        0.50 * strength_coverage
        + 0.20 * float(has_houses)
        + 0.15 * float(has_d24)
        + 0.10 * role_coverage
        + 0.05 * float(has_birth_precision)
    )

    # GAP-FIX (audit, 2026-07-23): this used to only ever compare
    # streams[0] vs streams[1] -- a chart where #2 and #3 are ALSO within
    # the near-tie margin of each other (confirmed live on Ramsunder:
    # Science 40.2, Commerce 37.51 [gap 2.69, correctly flagged], Humanities
    # 36.29 [gap to Commerce only 1.22, ALSO under the 3.0 margin]) was
    # reported as "a genuine two-stream tie", silently understating that the
    # #3 stream is nearly as close as #2 -- misleading for a parent/student
    # deciding between all three. Now walks down the ranking checking every
    # adjacent gap, not just the first one, and the note names every stream
    # that's bunched together rather than assuming exactly two.
    is_close_call = False
    close_call_note = ""
    score_gap = 0.0
    tied_stream_labels: List[str] = []
    if len(streams) >= 2:
        gap = streams[0]["normalized_score"] - streams[1]["normalized_score"]
        score_gap = gap
        if gap <= _NEAR_TIE_MARGIN:
            is_close_call = True
            tied_stream_labels = [streams[0]["label"], streams[1]["label"]]
            for i in range(1, len(streams) - 1):
                next_gap = streams[i]["normalized_score"] - streams[i + 1]["normalized_score"]
                if next_gap <= _NEAR_TIE_MARGIN:
                    tied_stream_labels.append(streams[i + 1]["label"])
                else:
                    break
            tied_scores_text = ", ".join(
                f"{s['label']} ({s['normalized_score']:.1f})" for s in streams[: len(tied_stream_labels)]
            )
            tie_kind = "two-stream tie" if len(tied_stream_labels) == 2 else f"{len(tied_stream_labels)}-way tie"
            close_call_note = (
                f"{tied_scores_text} are all within {_NEAR_TIE_MARGIN:.0f} points of their "
                f"nearest neighbor -- treat this as a genuine {tie_kind}, not a decisive "
                "single recommendation. All of these streams' core-subject lists are worth "
                "reviewing with the student. This threshold is an engineering convenience, "
                "not a statistically validated confidence interval -- see scoring_contract_version."
            )

    # The classical chain is authoritative for decision status. Numeric
    # final scores retain all rubric sections for auditability, but D24 may
    # neither manufacture a close call when D1 is clear nor conceal a real
    # D1 tie. A resolved refinement is a decision; an unresolved chain is
    # explicitly indeterminate.
    _resolved_stages = {"vargottama", "dignity_strength", "jaimini_akamk", "dasha_relevance"}
    if precedence_chain_resolution_stage == "d1_clear":
        d1_values = sorted(
            (precedence_chain_detail.get("d1_promise_scores") or {}).values(),
            reverse=True,
        )
        score_gap = (d1_values[0] - d1_values[1]) if len(d1_values) >= 2 else 0.0
        is_close_call = False
        tied_stream_labels = []
        close_call_note = precedence_chain_detail.get("note", "")
    elif precedence_chain_resolution_stage in _resolved_stages:
        is_close_call = False
        tied_stream_labels = []
        close_call_note = precedence_chain_detail.get("note", "")
    elif precedence_chain_resolution_stage == "still_tied_after_full_chain":
        is_close_call = True
        tied_stream_labels = precedence_chain_detail.get("tied_streams", [])
        close_call_note = precedence_chain_detail.get("note", "")

    # GAP-FIX (audit #66): "disagreement ledger" -- for each rubric section,
    # which stream had the highest raw contribution in that section alone,
    # vs the FINAL (all-sections-combined) winner. A report showing only the
    # final ranked list hides cases where, say, subject_evidence favors
    # Commerce while d24_confirmation favors Science and the final score
    # happens to land on Science anyway (buried under a dozen other numbers)
    # -- this makes that visible in one place instead of requiring someone to
    # manually diff every section across all 3 streams' rubrics.
    disagreement_ledger: Dict[str, Any] = {}
    if streams:
        all_sections = streams[0]["score_rubric"]["sections"]
        # GAP-FIX (audit, this turn): "leader" means "highest positive
        # evidence" for every section EXCEPT contraindications, which is a
        # penalty section (negative display values) -- max() by display
        # there silently means "least penalized," a DIFFERENT concept that
        # was previously mixed into the same section_leading_stream dict
        # with no distinction, making it read as if every entry meant the
        # same thing. Penalty sections are now reported separately.
        positive_section_names = [sec["section"] for sec in all_sections if sec.get("kind") != "penalty"]
        penalty_section_names = [sec["section"] for sec in all_sections if sec.get("kind") == "penalty"]
        section_leaders: Dict[str, str] = {}
        for section_name in positive_section_names:
            # GAP-FIX (audit #17, CONFIRMED bug): this previously ranked
            # streams by each section's UNCAPPED "actual" value, while the
            # final score (rubric["display_total"], per the P0-1 fix this
            # engine already made once before) is built from "display" --
            # the min(actual, cap) value. A section where one stream's raw
            # contribution wildly overshoots its cap (e.g. actual=40 vs
            # cap=18) could be reported as "leading" here even though it
            # contributes no more to the real score than a stream at
            # actual=18.01 -- the ledger's leader could silently disagree
            # with what the section actually counted toward the total.
            # "display" is the same capped/signed value build_score_rubric
            # already uses for display_total, so this ledger and the real
            # final score are now reading the exact same numbers.
            def _section_key(s, _name=section_name):
                return next(
                    (sec["display"] for sec in s["score_rubric"]["sections"] if sec["section"] == _name),
                    float("-inf"),
                )
            best_stream = max(streams, key=_section_key)
            section_leaders[section_name] = best_stream["label"]

        # Penalty sections: "leader" here means "least penalized" (display
        # closest to 0, since penalty values are <= 0), a different
        # question from "which stream has the strongest evidence" -- kept
        # in its own dict so it's never confused with section_leaders above.
        least_penalized: Dict[str, str] = {}
        for section_name in penalty_section_names:
            def _section_key(s, _name=section_name):
                return next(
                    (sec["display"] for sec in s["score_rubric"]["sections"] if sec["section"] == _name),
                    float("-inf"),
                )
            best_stream = max(streams, key=_section_key)
            least_penalized[section_name] = best_stream["label"]

        final_leader = streams[0]["label"]
        disagreeing_sections = sorted(
            name for name, leader in section_leaders.items() if leader != final_leader
        )
        disagreement_ledger = {
            "final_leading_stream": final_leader,
            "section_leading_stream": section_leaders,
            "sections_disagreeing_with_final": disagreeing_sections,
            # GAP-FIX (audit, this turn): separated out from
            # section_leading_stream -- see comment above positive_section_names.
            "section_least_penalized_stream": least_penalized,
            "note": (
                "section_leading_stream: which stream each POSITIVE-evidence rubric "
                "section (planetary_strength, house_support, role_placement, "
                "subject_evidence, d24_confirmation, relational_d1, jaimini_apparatus) "
                "would pick on its own, versus the FINAL stream after all sections are "
                "combined. A section appearing in sections_disagreeing_with_final does "
                "not mean it is wrong -- it means that evidence channel alone points "
                "elsewhere; worth reading before treating the final ranking as unanimous "
                "across every kind of evidence this engine considers. "
                "section_least_penalized_stream (contraindications) is a DIFFERENT "
                "question -- which stream received the smallest penalty, not which has "
                "the strongest positive evidence -- reported separately so the two are "
                "never conflated."
            ),
        }

    # GAP-FIX (2026-07-24, CRITICAL bug #1): top_score MUST be the actual
    # numeric leader's score -- `streams` is kept in pure normalized_score
    # order now (see above), so streams[0] is safe to read here again.
    # Previously (when `streams` could be reordered by the precedence
    # chain) this line silently read the precedence WINNER's score instead
    # of the true top score, corrupting every status check below it
    # (INDETERMINATE_LOW_SUPPORT, close-call, PROVISIONAL/SUPPORTED).
    top_score = streams[0]["normalized_score"] if streams else 0.0
    if strength_coverage < 0.80 or evidence_completeness < 0.60:
        recommendation_status = "INSUFFICIENT_DATA"
        dominant_stream = None
    elif top_score < 30.0:
        recommendation_status = "INDETERMINATE_LOW_SUPPORT"
        dominant_stream = None
    elif is_close_call:
        recommendation_status = "INDETERMINATE_CLOSE_CALL"
        dominant_stream = None
    elif score_gap < 6.0 or not has_birth_precision:
        recommendation_status = "PROVISIONAL"
        # dominant_stream is the user-facing recommendation -- the
        # precedence-informed pick (recommended_stream), NOT necessarily
        # streams[0]/the raw numeric leader. See recommended_stream's
        # doc-comment above and numeric_rank for the raw score ordering.
        dominant_stream = recommended_stream
    else:
        recommendation_status = "SUPPORTED"
        dominant_stream = recommended_stream

    return {
        "engine_version": STREAM_ENGINE_VERSION,
        "calculation_profile": CALCULATION_PROFILE,
        # GAP note: a report scored with the experimental 8th section must be
        # visibly distinguishable from a normal-mode report -- the contract
        # string itself carries a suffix so old/new-mode reports for the same
        # chart are never mistaken for directly comparable.
        "scoring_contract_version": (
            SCORING_CONTRACT_VERSION + "+field-derived-experimental.v1"
            if include_field_derived_evidence else SCORING_CONTRACT_VERSION
        ),
        "engine_build_fingerprint": _ENGINE_BUILD_FINGERPRINT,
        "field_determination_evidence": field_derived_evidence,
        "calculation_identity": _calculation_identity(payload),
        "input_quality": {
            "status": "VALID" if not input_quality_issues else "DEGRADED",
            "issues": input_quality_issues,
            "note": "Degraded inputs are retained for auditability but reduce evidential completeness.",
        },
        "calibration": calibration_state(),
        # GAP-FIX (2026-07-24, CRITICAL bug #1): `streams` is always in pure
        # normalized_score-descending order now -- it is NOT reordered to
        # reflect the precedence chain's pick. Use numeric_rank/
        # recommended_stream (below) instead of streams[0] for anything
        # that needs to distinguish "highest score" from "recommended."
        "streams": streams,
        # numeric_rank: stream_ids ordered purely by normalized_score,
        # descending. This is what "top score"/close-call/low-support
        # status logic reads from -- it never reflects the precedence
        # chain's pick.
        "numeric_rank": numeric_rank,
        # d1_candidate_rank: stream_ids ordered by D1-only promise score
        # (planetary_strength/house_support/role_placement/subject_evidence/
        # relational_d1/contraindications only -- before D24, Jaimini, or
        # dasha refinement). This is the "tree establishes the candidates"
        # ranking the classical precedence chain uses to decide which
        # streams are even eligible to be refined.
        "d1_candidate_rank": d1_candidate_rank,
        # precedence_decision: the stream_id the classical precedence chain
        # actually selected, or None if it left a genuine tie unresolved
        # (or the chain is disabled/had no streams). See
        # precedence_chain_resolution_stage for which stage decided it and
        # precedence_chain_detail for the full evidence trail.
        "precedence_decision": precedence_decision,
        # recommended_stream: the final pick shown to the user as THE
        # recommendation. This is the precedence-informed pick
        # (== precedence_decision when the chain resolved one, else falls
        # back to numeric_rank[0]) -- it is NOT guaranteed to be the raw
        # numeric leader. dominant_stream (below) is set from this field
        # whenever recommendation_status allows a recommendation at all.
        "recommended_stream": recommended_stream,
        # dominant_stream: recommended_stream, gated by recommendation_status
        # (None under INSUFFICIENT_DATA/INDETERMINATE_* -- see status logic
        # above). Kept for backward compatibility with existing callers.
        "dominant_stream": dominant_stream,
        # top_ranked_stream: the highest normalized_score stream, i.e.
        # numeric_rank[0]. Historically documented (see cross_validate.py)
        # as "the plain highest-score stream, always populated" -- now
        # actually guaranteed to mean that again (see CRITICAL bug #1: this
        # used to silently read the precedence winner after `streams` got
        # reordered).
        "top_ranked_stream": numeric_rank[0] if numeric_rank else None,
        "recommendation_status": recommendation_status,
        "evidence_completeness": round(evidence_completeness, 3),
        "planet_strength_coverage": round(strength_coverage, 3),
        "score_gap_top_two": round(score_gap, 2),
        "is_close_call": is_close_call,
        "close_call_note": close_call_note,
        # GAP-FIX (audit, 2026-07-23): all streams bunched within the
        # near-tie margin of their neighbor, in ranked order -- lets a
        # report distinguish a genuine 2-way tie from a 3-way toss-up
        # instead of only ever naming the top 2.
        "tied_streams": tied_stream_labels,
        # GAP-FIX (audit #66): see disagreement_ledger construction above.
        "disagreement_ledger": disagreement_ledger,
        # GAP-FIX (audit #45): non-None only when current_age indicates an
        # adult chart -- see construction above.
        "age_routing_note": age_routing_note,
        # GAP-FIX (2026-07-24, explicit user decision, "Option 1"): see the
        # D24/JAIMINI ARBITRATION POLICY comment block above
        # compute_stream_determination() -- d1_arbitration_status is
        # "clear_d1_signal" (D1 alone decisively favored the winner, D24/
        # Jaimini stayed purely additive/confirmatory, nothing changed),
        # "d24_arbitrated" (D1 was inconclusive among 2-3 streams and D24/
        # Jaimini's boosted vote produced a clear leader among them),
        # "still_tied" (D1 was inconclusive AND D24/Jaimini's boost still
        # left the leading candidates within the engine's own close-call
        # margin -- genuinely a toss-up, not silently resolved), or
        # "disabled" (d24_arbitration_enabled=False was passed -- pure
        # pre-2026-07-24 additive behavior). d1_arbitration_detail carries
        # the full per-stream D1/D24 subtotals and before/after ranking so
        # this is always independently checkable, never a silent policy.
        "d1_arbitration_status": d1_arbitration_status,
        "d1_arbitration_detail": d1_arbitration_detail,
        # GAP-FIX (2026-07-24): CLASSICAL PRECEDENCE CHAIN result -- one of
        # "d1_clear" (no genuine tie -- final score already decisive),
        # "vargottama" | "dignity_strength" | "jaimini_akamk" |
        # "dasha_relevance" (the stage whose real classical evidence
        # resolved a genuine tie), "still_tied_after_full_chain" (all 4
        # stages checked, tie is real, no winner forced), or "disabled"
        # (classical_precedence_chain_enabled=False was passed).
        # precedence_chain_detail carries the full per-stage evidence
        # (vargottama significators, dignity states, AK/AmK hits, active
        # dasha lords) actually used, or an honest note when a stage's
        # inputs were unavailable and it was skipped rather than faked.
        "precedence_chain_resolution_stage": precedence_chain_resolution_stage,
        "precedence_chain_detail": precedence_chain_detail,
        # GAP-FIX (2026-07-24, dasha as_of_date reproducibility): the exact
        # calendar date Stage 4 (dasha-relevance) treated as "today" when
        # resolving the active mahadasha/antardasha window -- also present
        # inside precedence_chain_detail, duplicated here as a top-level
        # field so any report reader can see at a glance what date this
        # report's dasha-stage evaluation used without digging into the
        # nested chain detail.
        "evaluation_as_of_date": evaluation_as_of_date,
        "planet_strengths": {p: (round(float(v), 3) if v is not None else None)
                             for p, v in planet_strengths.items()},
    }
