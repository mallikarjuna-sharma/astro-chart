"""Tier-based field ranking override (2026-08-18).

Replaces the flat 9-method linear-blend's contribution to field RANKING
with a 3-tier classical-authority hierarchy. This does NOT touch how any
individual method score is computed, nor any of the safety/eligibility
gates (hard_lockout, aptitude threshold, contraindication floor, etc.) --
it only decides which of the already-scored, already-eligible candidate
fields outranks which other one, replacing the old
"sort everything by the flat-blend final_score" ranking authority.

WHY: a by-hand audit against two real charts (Ramsunder and Akash
Shanmugham -- see md/ENGINE_TRANSPARENCY_GAP_AUDIT_2026-08-17.md and the
follow-up chat thread) found the same failure signature on both: the
flat-blend's published #1 field had the WEAKEST astrological method
evidence (lowest `weighted_method_score`) among the top candidates, with
`affinity_score` (a non-astrological academic/interest-fit signal, not
part of the 9 astrological methods at all) actually driving the ranking.
Meanwhile a field with genuinely stronger classical-method agreement sat
several ranks lower. Re-weighting the blend wasn't enough to fix this --
the flat linear blend structurally lets a handful of loud-but-lower-
authority signals outvote a chart's actual classical-authority evidence.

TIER DESIGN (agreed 2026-08-18):
  Tier 1 (gatekeeper, primary vote):      Parashara + Dashamsha + Jaimini + K.N. Rao
  Tier 2 (confirmatory, tie-break only):  KP + Sudarshana
  Tier 3 (fine-tune, sanity-check only):  Shashtiamsha + structural_patterns

  Siddhamsha (D24) is deliberately EXCLUDED from this field-RANKING blend.
  It is the classical education/learning varga, not a career-field varga,
  and belongs to the (separate) education-route decision, at its own
  tier-1-equivalent authority there. Folding it into the field-ranking
  blend was part of what let the old flat blend's field-choice and
  education-route signals bleed into each other.

  Tier 1 decides a field's rank outright UNLESS it is a near-tie with
  another field (within NEAR_TIE_BAND, relative to the tier-1 leader of
  that cluster) -- classical technique should not be second-guessed by
  softer/narrower techniques when it isn't actually close. Only when
  Tier 1 leaves a genuine near-tie does Tier 2 get a vote, and only when
  Tier 2 is *also* a near-tie does Tier 3 get a vote. Tier 2/3 methods are
  each individually narrower in classical scope than the Tier 1 quartet
  (KP is a horary/timing technique stretched to a field-breadth question;
  Sudarshana is a synthesis overlay, not new evidence; Shashtiamsha is
  birth-time-sensitive; structural_patterns has no classical grounding at
  all) -- which is why they are confirmatory/tie-break only, never a
  primary vote.

Per-tier weights are RENORMALIZED from this codebase's own existing
`METHOD_WEIGHTS` classical-authority priors (see
Field_Determination/field_methods/__init__.py), restricted to each tier's
methods and rescaled to sum to 1.0 within that tier. This preserves the
relative classical-authority ordering the codebase already encodes (e.g.
within Tier 1, KNRao > Dashamsha == Jaimini > Parashara) rather than
inventing new priors from scratch.

GAP FIX (2026-08-18, "why is law/archaeology coming from nowhere" audit,
round 2 -- GENERALIZED): jyotish/ranking_policy.py runs two versions of the
same uncorroborated-symbolic-leakage guard: a curated-list check
(PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE -- history_archaeology, civil_services,
journalism_media, gender_studies, etc.) and, since a later gap-audit round,
a GENERALIZED check with no list requirement at all -- ANY field ranking
in the true top 5 with no Dashamsha/Siddhamsha career-varga support (both
< 35.0) and no same-cluster corroboration among the astrological top 10
gets the same 45% discount (see `apply_uncorroborated_leakage_guards()`'s
second block in ranking_policy.py). Both guards run in engine.py BEFORE
compute_tiered_ranking() -- but tier1_score (built only from raw Tier-1
method scores) doesn't know either discount happened, so an uncorroborated
field's inflated tier1_score walks straight back to the top of the ranking
this module produces regardless of which guard would have caught it.

First round of this fix only re-applied the CURATED-list version here,
which stopped history_archaeology (on the list) but missed
international_law (an uncorroborated field -- dashamsha 3.52 -- that had
simply never been added to the curated list, since it hadn't leaked on a
prior chart). Per an explicit design decision (2026-08-18): rather than
hand-adding international_law to the curated list, this module now
reimplements the CODEBASE'S OWN ALREADY-EXISTING generalized check
directly (same thresholds, same cluster-support exemption, same 45%
ratio) so coverage doesn't depend on a field having personally been
caught leaking on some earlier chart first. This is a real behavior
change for every chart, not just Ramsunder's -- any chart where an
uncorroborated field would otherwise crack the top 5 on Tier 1 alone is
now affected, matching how the curated version already behaves for its
narrower list. Tier 1 authority does NOT override this protection -- it
isn't a competing ranking opinion, it's a correction for a known
scoring-scale distortion in the same 2 raw methods (KNRao, Parashara)
Tier 1 is built from. See _corroboration_discounted_tier1_scores() below.
"""

from __future__ import annotations

import os as _os
from typing import Any, Dict, List, Tuple

# Print-output optimization (2026-08-20): gate the per-tie-group debug print
# (`[D60 TIE-BREAK]`) behind the same opt-in verbosity flag engine.py uses,
# so a normal run only prints the final summary report. Set
# JYOTISH_VERBOSE_FIELD_LOG=1 to restore it.
_VERBOSE_FIELD_LOG = _os.environ.get("JYOTISH_VERBOSE_FIELD_LOG", "0") == "1"

from .ranking_policy import (
    _career_varga_percentile_standings,
    _lacks_career_varga_corroboration,
    UNCORROBORATED_CAREER_VARGA_FLOOR,
)

# Same ratio ranking_policy.py's own guards already use for this pattern
# (apply_uncorroborated_leakage_guards(): `final_score * 0.55`) -- kept
# identical rather than inventing a new number, so an uncorroborated field
# is discounted the same amount regardless of which stage catches it.
_LEAKAGE_DISCOUNT = 0.55

# Gap-audit fix (2026-08-19, chat session, "Tier-1 gating, not Tier-1
# averaging" round): Tier 1 folds dashamsha into ONE averaged vote alongside
# Parashara/Jaimini/KNRao (TIER1_WEIGHTS below), so a big Tier-1 margin can
# be entirely carried by the three D1 house/karaka-lordship methods while
# dashamsha -- the one chart Parashara names as the specific authority on
# profession (BPHS dedicates a full chapter to it) -- sits near zero and
# never gets a chance to object, because "no near-tie within NEAR_TIE_BAND"
# lets Tier 1 decide outright regardless of what's actually driving that
# margin. Confirmed live on Ramsunder's chart: agricultural_food_engineering
# won Tier 1 outright (29.7779, no near-tie) while its own dashamsha
# normalized_score was 8.42/100 -- an averaged vote let three generic
# methods outvote the one field-authoritative technique entirely.
#
# Fix: dashamsha gets a veto over the "decided outright" shortcut, not just
# a quarter-vote inside it. If the Tier-1 leader of a would-be singleton
# near-tie group has a raw dashamsha score below this absolute bar, Tier 1
# is not allowed to decide outright no matter how large its margin over the
# next candidate is -- that field is folded into contention with the next
# tier-1 group so Tier 2/3 (which do NOT depend on dashamsha at all) get an
# actual vote on whether it still deserves the position. This does not
# touch tier1_score/tier1_groups formation itself, nor the generalized
# corroboration-discount pass below (which is a separate, score-mutating
# guard) -- it only changes whether an already-computed Tier-1 leader is
# allowed to skip tie-breaking. Reuses ranking_policy.py's own
# UNCORROBORATED_CAREER_VARGA_FLOOR rather than inventing a second number,
# so both guards agree on what "career-varga silent" means.
_TIER1_OUTRIGHT_DASHAMSHA_FLOOR = UNCORROBORATED_CAREER_VARGA_FLOOR


def _dashamsha_norm_score(row: Dict[str, Any]) -> float:
    norm = row.get("method_scores_normalized_0_100") or row.get("method_normalized_scores") or {}
    return float(norm.get("dashamsha", row.get("dashamsha_score", 0.0)) or 0.0)

# Mirrors ranking_policy.py's UNCORROBORATED_LEAKAGE_RANK_GUARD (only the
# true top-N of the whole candidate set is checked -- a field ranked #20
# on Tier 1 doesn't need this protection, it's not about to be published
# as a headline pick regardless) and its same-cluster exemption threshold.
_CORROBORATION_CHECK_RANK_GUARD = 5
_CLUSTER_SUPPORT_EXEMPTION = 2


def _cluster(row: Dict[str, Any]) -> str:
    # Mirrors ranking_policy.py's own _cluster() helper exactly.
    return str(row.get("graph_cluster") or row.get("competency_label") or "")


def _family(row: Dict[str, Any]) -> str:
    # Mirrors hierarchical_ranking.py's own family lookup (ontology_v12's
    # primary_family, falling back to domain) so this reads the SAME family
    # label another module in this codebase already treats as authoritative,
    # rather than inventing a second, competing notion of "family".
    ontology = row.get("ontology_v12") or {}
    return str(ontology.get("primary_family") or row.get("domain") or "unclassified")

TIER1_METHODS: Tuple[str, ...] = ("parashara", "dashamsha", "jaimini", "knrao")
TIER2_METHODS: Tuple[str, ...] = ("kp", "sudarshana")
TIER3_METHODS: Tuple[str, ...] = ("shashtiamsha", "structural_patterns")

# Mirrors Field_Determination/field_methods/__init__.py's METHOD_WEIGHTS.
# Duplicated (not imported) deliberately: this module must stay usable/
# testable in isolation without pulling in the full field_methods package,
# and these priors are the codebase's own settled values, not new tuning.
_RAW_METHOD_WEIGHTS: Dict[str, float] = {
    "knrao": 0.1678,
    "kp": 0.0629,
    "jaimini": 0.1538,
    "parashara": 0.1049,
    "dashamsha": 0.1538,
    "sudarshana": 0.0559,
    "siddhamsha": 0.1748,
    "shashtiamsha": 0.046,
    "structural_patterns": 0.08,
}


def _renormalized(methods: Tuple[str, ...]) -> Dict[str, float]:
    total = sum(_RAW_METHOD_WEIGHTS[m] for m in methods) or 1.0
    return {m: _RAW_METHOD_WEIGHTS[m] / total for m in methods}


TIER1_WEIGHTS: Dict[str, float] = _renormalized(TIER1_METHODS)
TIER2_WEIGHTS: Dict[str, float] = _renormalized(TIER2_METHODS)
TIER3_WEIGHTS: Dict[str, float] = _renormalized(TIER3_METHODS)

# Relative gap (as a fraction of a cluster leader's tier score) within
# which two fields are treated as a near-tie requiring the next tier to
# adjudicate, rather than accepting the higher tier's ranking outright.
# Calibrated from the Ramsunder hand-audit (2026-08-17/18): Metallurgical
# vs Materials Science Engineering differed by ~0.2% on Tier 1 -- a
# genuine near-tie that needed Tier 2/3 to resolve -- while the Tier-1
# leader vs the #3 candidate differed by >30% (decided outright, no tie-
# break needed). 3% is a deliberately conservative band: wide enough to
# catch genuine near-ties like the Ramsunder case, narrow enough not to
# trigger on every adjacent pair in a 20-field ranking.
NEAR_TIE_BAND: float = 0.03


def _tier_score(normalized: Dict[str, float], weights: Dict[str, float]) -> float:
    total_w = sum(weights.values()) or 1.0
    return round(
        sum(float(normalized.get(m, 0.0) or 0.0) * w for m, w in weights.items()) / total_w,
        4,
    )


# §11 remediation (2026-08-19): filter 4 ("D60/BAV tie-break within ~1
# point") -- the tie-break mechanism previously cascaded through the WHOLE
# ranked list via this function with no rank-position gate, so a near-tie
# between, say, rank #47 and #48 got the exact same Tier 2/3 adjudication
# machinery as a near-tie for rank #1. The spec scopes this tie-break to
# near-TOP candidates specifically (where the distinction actually matters
# for what gets recommended/published), not every adjacent pair anywhere in
# a 100+ field ranked list. `rank_limit` restricts grouping to rows whose
# cumulative position is within this window; once exceeded, every
# subsequent row is forced into its own singleton group (keeps its raw
# tier1-only order, never enters Tier 2/3 tie-break).
_NEAR_TOP_TIE_BREAK_RANK_LIMIT = 15


def _group_near_ties(
    rows: List[Dict[str, Any]], score_key: str, band: float,
    rank_limit: int | None = None,
) -> List[List[Dict[str, Any]]]:
    """Group consecutive rows (already sorted desc by score_key) into
    near-tie clusters. A row joins the current cluster if it is within
    `band` (relative to that cluster's own leader) of the cluster leader,
    AND (when `rank_limit` is set) its position among `rows` is still
    within that near-top window -- see _NEAR_TOP_TIE_BREAK_RANK_LIMIT.
    """
    groups: List[List[Dict[str, Any]]] = []
    for _pos, row in enumerate(rows, 1):
        score = row[score_key]
        _within_rank_window = rank_limit is None or _pos <= rank_limit
        if groups and _within_rank_window:
            leader_score = groups[-1][0][score_key]
            if leader_score > 0 and (leader_score - score) / leader_score <= band:
                groups[-1].append(row)
                continue
        groups.append([row])
    return groups


def _apply_generalized_corroboration_discount(rows: List[Dict[str, Any]]) -> None:
    """Generalized version of ranking_policy.py's uncorroborated-symbolic-
    leakage guard, reimplemented against `tier1_score` instead of the
    legacy flat-blend `final_score` -- see this module's docstring for why
    a fresh pass is needed here rather than trusting the guard that already
    ran upstream in engine.py. Mutates `tier1_score`/`tier1_leakage_
    discounted` in place on `rows`; caller re-sorts afterward.

    No curated-list requirement (unlike ranking_policy.py's FIRST guard,
    PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE) -- ANY field that would otherwise
    crack the true top N on Tier 1 alone, with no Dashamsha/Siddhamsha
    career-varga support and no same-cluster corroboration among the
    astrological top 10, gets the same 45% discount. Same thresholds as
    ranking_policy.py's own generalized guard (its second block, added
    after the curated one) -- reused, not reinvented.

    Gap-audit fix (2026-08-18, Claude session): the cluster-support
    exemption originally counted raw FIELD instances sharing a row's
    graph_cluster, with no requirement that they be independent evidence.
    Confirmed live on Lakshman's chart: computational_social_science ranked
    #1 with dashamsha=9.01, siddhamsha=0.0 (both catastrophically below
    UNCORROBORATED_CAREER_VARGA_FLOOR) -- exactly this guard's target
    pattern -- yet was exempted because 8 of the top-10 astrological fields
    share its graph_cluster ("Computation, Data & Digital Intelligence").
    Those 8 are mostly near-synonymous registry entries for the same broad
    theme (computational_finance, operations_research, urban_informatics,
    economics_data_science, fintech, econometrics, statistics_data_science),
    almost certainly riding one shared generic-affinity signal rather than
    independent techniques agreeing -- i.e. the exact "isolated symbolic
    leakage, just relabeled many times" failure this guard exists to catch,
    inverted into a false exemption by field-registry granularity.
    Now requires the same-cluster co-members to also span at least
    _CLUSTER_SUPPORT_EXEMPTION DISTINCT competency_ontology families (see
    _family() -- reuses hierarchical_ranking.py's own ontology_v12.
    primary_family lookup, not a new taxonomy), not just distinct field_ids.
    A cluster full of one family's near-duplicates no longer counts as
    corroboration; genuinely different families sharing a broad cluster
    still do.

    Gap-audit fix, round 2 (2026-08-19, Claude session): the family-
    distinctness fix above was necessary but not sufficient. Confirmed live
    on a second real chart (Ramsunder): agricultural_food_engineering
    ranked #1 with dashamsha=7.17, siddhamsha=11.86 (again far below the
    floor), exempted because its cluster ("Advanced Engineering & Physical
    Systems") spans two distinct families (materials_extractive,
    mechanical_manufacturing) -- but EVERY field in both of those families
    among the astrological top 10 was ALSO near-zero on both career vargas
    (dashamsha 2.96-4.8, siddhamsha 10.98-12.17 across the board). Distinct
    family labels are not evidence if every labelled field is equally
    uncorroborated -- an entire cluster can share one weak generic-affinity
    signal while still satisfying a family-diversity count. A same-cluster,
    different-family field now only counts toward corroboration if it does
    NOT ALSO lack career-varga corroboration itself (i.e. it must clear
    UNCORROBORATED_CAREER_VARGA_FLOOR on dashamsha or siddhamsha) -- genuine
    corroboration requires the corroborating evidence to itself be real.

    Gap fix (2026-08-20, Claude session, convergence round): the checked
    window used to be a SINGLE fixed slice -- ranked[:_CORROBORATION_CHECK_
    RANK_GUARD], computed once before any discount was applied. Discounting
    a field in that original top 5 lowers its tier1_score, which can
    promote a field originally ranked #6 into the true top 5 -- but that
    promoted field was never re-checked, since the window was never
    recomputed. Fixed by re-sorting and re-slicing the top-N window after
    every discount, looping until a full pass makes no new discounts (a
    fixed point), so a field newly promoted into the checked window by an
    earlier pass's discount gets the same scrutiny an originally-top-5
    field did. astro_head (the same-cluster corroboration source pool) is
    intentionally NOT recomputed per pass -- it stays the fixed top-10-by-
    astrological_score population throughout, since it represents "what
    does this chart's independent astrological evidence look like", not
    the ranking-in-progress this loop is still resolving.

    Gap fix (2026-08-20, Claude session, percentile-standing floor): the
    test each field's dashamsha/siddhamsha is judged against is no longer a
    magnitude comparison at all (neither the bare UNCORROBORATED_CAREER_
    VARGA_FLOOR constant nor its chart-relative-fraction successor) -- see
    ranking_policy._career_varga_percentile_standings()'s docstring for why
    a magnitude-based floor (absolute OR relative) can degenerate to
    "always pass" when a varga's whole distribution is compressed on a
    given chart. Replaced with a rank/percentile test: does this field sit
    in the bottom half of THIS chart's own candidate pool on that varga.
    Computed once per call, before the convergence loop, from the full
    undiscounted pool.
    """
    dash_st, sidd_st = _career_varga_percentile_standings(rows)
    astro_head = sorted(
        rows, key=lambda r: -float(r.get("astrological_score", r.get("final_score", 0.0)) or 0.0)
    )[:10]

    # Hard upper bound on passes: at most one new field can be discounted
    # per pass among the checked window, so this can never loop more than
    # len(rows) times -- guards against any unforeseen oscillation rather
    # than trusting convergence blindly.
    _MAX_PASSES = len(rows) + 1
    for _ in range(_MAX_PASSES):
        ranked = sorted(rows, key=lambda r: (-r["tier1_score"], str(r.get("field_id", ""))))
        window = ranked[:_CORROBORATION_CHECK_RANK_GUARD]
        discounted_this_pass = False
        for row in window:
            if row.get("tier1_leakage_discounted"):
                continue  # already discounted in an earlier pass of this loop
            if not _lacks_career_varga_corroboration(row, dash_st, sidd_st):
                continue
            row_cluster = _cluster(row)
            row_family = _family(row)
            corroborating_families = {
                _family(r) for r in astro_head
                if r is not row
                and row_cluster and _cluster(r) == row_cluster
                and _family(r) != row_family
                and not _lacks_career_varga_corroboration(r, dash_st, sidd_st)
            }
            if len(corroborating_families) >= _CLUSTER_SUPPORT_EXEMPTION:
                continue  # genuinely distinct families, each with real career-varga support of their own
            row["tier1_score"] = round(row["tier1_score"] * _LEAKAGE_DISCOUNT, 4)
            row["tier1_leakage_discounted"] = True
            discounted_this_pass = True
        if not discounted_this_pass:
            break  # fixed point reached -- no field in the current true-top-N window needs discounting


def compute_tiered_ranking(
    results: List[Dict[str, Any]],
    birth_time_precision: str = "exact",
    bav_tiebreak_scores: Dict[str, float] | None = None,
) -> List[Dict[str, Any]]:
    """Re-rank `results` using the 3-tier classical-authority model instead
    of the flat 9-method blend's contribution to ranking.

    Expects each row to already carry `method_normalized_scores` (0-100
    per-method, from Field_Determination/field_methods), `final_score`,
    `hard_lockout`, and `publication_eligibility` -- i.e. this must run
    AFTER the existing per-field scoring chain and safety gates, as the
    final ranking-authority step, not in place of them.

    Returns a NEW list, in final rank order (index 0 == rank 1), so
    callers should replace their working `results` reference with the
    return value directly rather than relying on `row["rank"]` alone.

    Adds/overwrites on every row:
      tier1_score, tier2_score, tier3_score   -- 0-100 tier sub-scores
      tier_decision_trace                     -- list[str], human-readable, which tier decided this field's position
      final_score_legacy_blend                -- the old flat-blend final_score, kept for audit/comparison
      final_score, rank, engine_rank, publication_score -- overwritten with the tiered result

    `bav_tiebreak_scores`: §11 remediation (2026-08-19) -- filter 4 also
    requires Bhinnashtakavarga (BAV) alongside D60 in the near-top tie-break,
    which was entirely absent before. OPTIONAL {field_id: 0-100 score} map,
    computed once per native by the caller (see jyotish.ashtakavarga.
    compute_bav_points -- typically each field's core significator planet's
    BAV bindus in H10, normalized to 0-100) and passed in here. When
    provided, blended lightly into tier3_score (15% weight) so it nudges
    near-top ties without becoming a new primary scoring channel. When
    omitted (default), tier3_score is unchanged from before -- fully
    backward compatible.

    `birth_time_precision`: §6 remediation (2026-08). Shashtiamsha (D60) is
    the finest-grained divisional chart in use (each sign sliced into 60
    parts of 0.5 degrees) -- its longitude-dependent sign placement is only
    meaningful when the birth time (and therefore the ascendant/planetary
    degrees) is known precisely. With an "approximate" or "unknown" birth
    time, D60 placements are effectively noise and should not be allowed to
    swing even a tie-break. When precision is not "exact", Tier 3 falls back
    to structural_patterns alone (renormalized to weight 1.0) instead of the
    default shashtiamsha+structural_patterns blend -- mirroring the existing
    precedent in Field_Determination/field_methods/__init__.py's KP weight
    gating on this same field. Defaults to "exact" for backward
    compatibility with existing callers/tests that don't pass it.
    """
    if not results:
        return results

    _precision_norm = str(birth_time_precision or "exact").lower()
    if _precision_norm == "exact":
        _tier3_weights = TIER3_WEIGHTS
    else:
        _tier3_weights = _renormalized(("structural_patterns",))

    for row in results:
        # BUG FIX (2026-08-18, first live run): engine.py's "LS12 fix"
        # (search that string in engine.py) renames `method_normalized_scores`
        # to `method_scores_normalized_0_100` well before a row reaches
        # `results` here -- `method_normalized_scores` is empty/missing on
        # every published row by this point. ranking_policy.py hit this
        # exact issue earlier and was patched with the same dual-key
        # fallback below; without it every tier score silently computes
        # against {} and collapses to 0.0 for every field (confirmed live:
        # first deployed version of this file did exactly that).
        norm = row.get("method_scores_normalized_0_100") or row.get("method_normalized_scores") or {}
        row["tier1_score"] = _tier_score(norm, TIER1_WEIGHTS)
        row["tier1_leakage_discounted"] = False
        row["tier2_score"] = _tier_score(norm, TIER2_WEIGHTS)
        row["tier3_score"] = _tier_score(norm, _tier3_weights)
        # §11 remediation: blend in the optional BAV tie-break score (see
        # bav_tiebreak_scores docstring above) at a small, fixed 15% weight
        # -- large enough to actually move a near-top tie, capped low
        # enough that Shashtiamsha/structural_patterns (the tier's existing
        # methods) still dominate tier3_score.
        _bav_score = (bav_tiebreak_scores or {}).get(str(row.get("field_id", "")))
        if _bav_score is not None and _precision_norm == "exact":
            row["bav_tiebreak_score"] = round(float(_bav_score), 2)
            row["tier3_score"] = round(row["tier3_score"] * 0.85 + float(_bav_score) * 0.15, 4)
        row["final_score_legacy_blend"] = row.get("final_score")

    # Generalized uncorroborated-symbolic-leakage discount (2026-08-18,
    # round 2) -- must run against the FULL population (all eligible
    # candidates, not per-row in isolation) since "top 5" and "same-cluster
    # corroboration in the astrological top 10" are both population-level
    # facts. Applied before the near-tie grouping below so a discounted
    # field's demotion can actually change which fields end up near-tied
    # with each other, not just cosmetically lower a number.
    _eligible_for_corroboration_check = [
        r for r in results
        if not r.get("hard_lockout", False) and r.get("publication_eligibility") != "exploratory_only"
    ]
    _apply_generalized_corroboration_discount(_eligible_for_corroboration_check)

    # Respect existing safety/eligibility partitioning: hard_lockout and
    # exploratory_only rows never compete for rank position on astrological
    # merit -- this module changes WHICH eligible fields outrank which
    # other eligible fields, not whether a locked-out field can bypass its
    # lockout. Mirrors _enforce_hard_lockout_publication_order()'s own
    # partition in jyotish/engine.py.
    exploratory_only = [r for r in results if r.get("publication_eligibility") == "exploratory_only"]
    locked = [
        r for r in results
        if r.get("hard_lockout", False) and r.get("publication_eligibility") != "exploratory_only"
    ]
    valid = [
        r for r in results
        if not r.get("hard_lockout", False) and r.get("publication_eligibility") != "exploratory_only"
    ]

    valid.sort(key=lambda r: r["tier1_score"], reverse=True)
    tier1_groups = _group_near_ties(valid, "tier1_score", NEAR_TIE_BAND,
                                     rank_limit=_NEAR_TOP_TIE_BREAK_RANK_LIMIT)

    # Gap-audit fix (2026-08-19, chat session, "Tier-1 gating" -- see the
    # _TIER1_OUTRIGHT_DASHAMSHA_FLOOR note above for the full rationale): a
    # singleton Tier-1 group (i.e. a field about to be "decided outright,
    # no near-tie") is not allowed to skip Tier 2/3 if its own dashamsha
    # score is below the absolute career-varga floor -- regardless of how
    # large its Tier-1 margin is, since that margin is necessarily carried
    # entirely by the three non-career-specific methods when dashamsha
    # itself is this weak. Such a group is merged with the NEXT tier-1
    # group so Tier 2 (KP+Sudarshana) actually gets to compare it against
    # its nearest real competition, rather than defaulting to keep-first-
    # place-because-nobody-else-was-consulted. Only merges one step (not a
    # cascading merge across the whole list) -- deliberately conservative,
    # matching NEAR_TIE_BAND's own "narrow enough not to trigger on every
    # adjacent pair" design intent; a field this weak on dashamsha still
    # only needs to prove itself against its immediate next-best rival, not
    # the entire candidate pool.
    _gated_groups: List[List[Dict[str, Any]]] = []
    _i = 0
    while _i < len(tier1_groups):
        _group = tier1_groups[_i]
        if (
            len(_group) == 1
            and _dashamsha_norm_score(_group[0]) < _TIER1_OUTRIGHT_DASHAMSHA_FLOOR
            and _i + 1 < len(tier1_groups)
        ):
            _group[0]["tier1_dashamsha_gate_forced_tiebreak"] = True
            _gated_groups.append(_group + tier1_groups[_i + 1])
            _i += 2
        else:
            _gated_groups.append(_group)
            _i += 1
    tier1_groups = _gated_groups

    ordered: List[Dict[str, Any]] = []
    for group in tier1_groups:
        if len(group) == 1:
            group[0]["tier_decision_trace"] = [
                f"Tier 1 (Parashara+Dashamsha+Jaimini+KNRao)={group[0]['tier1_score']}: "
                f"no near-tie within {NEAR_TIE_BAND:.0%} of the next candidate -- decided outright by Tier 1."
            ]
            ordered.extend(group)
            continue

        group.sort(key=lambda r: r["tier2_score"], reverse=True)
        tier2_subgroups = _group_near_ties(group, "tier2_score", NEAR_TIE_BAND)
        for sub in tier2_subgroups:
            if len(sub) == 1:
                sub[0]["tier_decision_trace"] = [
                    f"Tier 1 near-tie among {len(group)} fields (all within {NEAR_TIE_BAND:.0%}) -- "
                    f"resolved by Tier 2 (KP+Sudarshana)={sub[0]['tier2_score']}."
                ]
                continue
            sub.sort(key=lambda r: r["tier3_score"], reverse=True)
            _sub_field_ids = [str(r.get("field_id", "")) for r in sub]
            _sub_tier3 = [round(r["tier3_score"], 2) for r in sub]
            if _VERBOSE_FIELD_LOG:
                print(
                    f"[D60 TIE-BREAK] {len(sub)} fields tied through Tier 1 and Tier 2 "
                    f"({_sub_field_ids}) -- Shashtiamsha (D60)+structural_patterns tier3_score "
                    f"{_sub_tier3} used to break the tie. Winner: {_sub_field_ids[0] if _sub_field_ids else 'n/a'}."
                )
            for r in sub:
                r["tier_decision_trace"] = [
                    f"Tier 1 near-tie among {len(group)} fields, then Tier 2 near-tie among {len(sub)} fields -- "
                    f"resolved by Tier 3 (Shashtiamsha+structural_patterns)={r['tier3_score']}."
                ]
        # tier2_subgroups, flattened, is this tier-1 group's fully resolved order.
        ordered.extend(r for sub in tier2_subgroups for r in sub)

    # gap fix 2026-08-18 (item 3 / Group 2): `locked`/`exploratory_only` were
    # appended in whatever order the original `results` list happened to
    # carry them in -- never sorted by their own tier1_score -- so within
    # either bucket, final_score (set below) could easily come out
    # non-monotonic (e.g. a hard-locked field with a higher tier1_score
    # sitting after one with a lower tier1_score). Sort each bucket
    # descending by tier1_score before appending, mirroring how `valid` is
    # already sorted, so every bucket is internally score-ordered.
    locked.sort(key=lambda r: (-r["tier1_score"], str(r.get("field_id", ""))))
    exploratory_only.sort(key=lambda r: (-r["tier1_score"], str(r.get("field_id", ""))))
    ordered.extend(locked)
    ordered.extend(exploratory_only)

    # gap fix 2026-08-18 (item 3 / Group 2): within a near-tie cluster,
    # Tier 2/Tier 3 can legitimately reorder members whose tier1_score
    # values are close but NOT identical (that's the whole point of
    # NEAR_TIE_BAND). Displaying each row's raw tier1_score as final_score
    # afterward (as the comment below always intended) can then make a
    # LATER-ranked row show a HIGHER final_score than the row immediately
    # ahead of it -- e.g. two fields ~22.7/22.9 apart get reordered by
    # Tier 2 testimony, so the row now ranked first still displays 22.69
    # while the row now ranked second displays 23.09, violating every
    # caller's "results are in strict final_score order" contract
    # (test_ramsunder_results_are_strictly_score_ordered). Tier evidence is
    # still the sole ranking AUTHORITY (row order below is untouched); this
    # only clamps the DISPLAYED score, per bucket, to be non-increasing so
    # the number shown never contradicts the position it's shown in -- the
    # full, un-clamped tier1_score remains available via tier_decision_trace
    # and the per-tier tier1_score/tier2_score/tier3_score fields for anyone
    # who needs the raw near-tie evidence.
    def _clamp_monotonic(bucket: List[Dict[str, Any]]) -> None:
        prev_score = None
        for row in bucket:
            score = round(row["tier1_score"], 2)
            if prev_score is not None and score > prev_score:
                score = prev_score
            row["final_score"] = score
            prev_score = score

    _clamp_monotonic(ordered[: sum(len(g) for g in tier1_groups)])
    _clamp_monotonic(locked)
    _clamp_monotonic(exploratory_only)

    for idx, row in enumerate(ordered, 1):
        if row.get("tier1_leakage_discounted"):
            row["tier_decision_trace"] = [
                "Tier 1 discounted 45%: this field ranked in the true top 5 with no "
                "Dashamsha/Siddhamsha career-varga corroboration and no same-cluster "
                "support in the astrological top 10 -- its raw KNRao/Parashara score "
                "reflects generic significator matches, not real career-house support."
            ] + (row.get("tier_decision_trace") or [])
        if row.get("tier1_dashamsha_gate_forced_tiebreak"):
            row["tier_decision_trace"] = [
                f"Tier 1 dashamsha gate: this field's Tier-1 margin was not allowed to "
                f"decide outright because its own dashamsha score was below the "
                f"{_TIER1_OUTRIGHT_DASHAMSHA_FLOOR:.0f} career-varga floor -- forced into "
                f"tie-break against its nearest Tier-1 competitor instead."
            ] + (row.get("tier_decision_trace") or [])
        row["rank"] = idx
        row["engine_rank"] = idx
        if "llm_rank" in row:
            row["llm_rank"] = idx
        row["publication_score"] = row["final_score"]

    return ordered
