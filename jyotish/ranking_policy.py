"""Deterministic publication policy for coherent career-field rankings.

The astrological engine scores every registry branch independently.  That is
useful for discovery, but a published Top 20 also needs two invariants that an
independent scorer cannot provide by itself:

* a narrow specialization must not outrank its supported broad foundation;
* isolated symbolic matches must not overwhelm a clearly dominant career
  cluster.

This module applies bounded, auditable score adjustments only.  It never
splices a field into a fixed rank and always returns true score order.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


FIELD_ROLES = {
    "civil_services": "career_route",
    "research_academia": "career_context",
    # Gap-audit fix (2026-08): checked every registry entry that reads as
    # route-like rather than subject-like against its actual data
    # (jyotish/india_course_registry_v12.json). Two others were structurally
    # identical to civil_services/research_academia -- their own "field"
    # value names an INSTITUTIONAL DESTINATION reached via several unrelated
    # entry-degree paths, not a taught discipline:
    #   civil_services      -- field: None (bare placeholder, no discipline at all)
    #   research_academia   -- field: "Research & Teaching" (a career mode spanning
    #                           every discipline, entered via PhD/Post_Doc/Faculty)
    #   defence_military     -- field: "Armed Forces", entered via NDA_Grad/
    #                           BTech_AFA/LLB_JAG/BSc_Naval -- four unrelated
    #                           degree routes into one institutional destination,
    #                           the same civil_services pattern.
    # By contrast "entrepreneurship" (field: "Entrepreneurship & Innovation
    # Management", taught at IIT SINE/IIM CIIE/SPJIMR as its own curriculum)
    # and "defence_strategic_studies" (field: "Defence & Strategic Studies",
    # taught as a humanities discipline at BHU/DU/JNU) are genuine academic
    # subjects with their own degree programs -- left as educational_field,
    # not added here.
    "defence_military": "career_route",
}

# Narrow branch -> broad educational foundation.  Only pairs present in the
# same candidate set are compared, so this cannot manufacture a recommendation.
SPECIALIZATION_PARENTS = {
    "space_materials": "materials_science_engineering",
    "space_systems_engineering": "aerospace_engineering",
    "space_sciences_engineering": "aerospace_engineering",
    "chemical_engineering_data_science": "chemical_engineering",
    # Gap-audit fix (2026-08, chat cross-chart review): these narrow labels
    # were repeatedly outranking their own broad classical foundation across
    # unrelated charts (Lakshman, hemant, Sai_Havish, Karthick, mallikarjun)
    # even though the underlying method evidence supports the broad theme,
    # not a distinctively narrower one. Same taxonomy pattern as the entries
    # above -- register them so broad_foundation_first applies.
    "applied_linguistics": "linguistics",
    "econometrics": "economics",
}

HYBRID_PARENTS = {
    "economics_data_science": ("economics", "statistics_data_science", "econometrics"),
    "chemical_engineering_data_science": ("chemical_engineering", "data_science_engineering"),
}
HYBRID_SYNERGY_CAP = 8.0

# Narrow fields need repeated support from their own macro domain. A single
# symbolic planet/keyword match is insufficient for publication near the top.
NARROW_FIELD_CLUSTERS = {
    "veterinary_science": {"Medicine, Health & Life Sciences", "Natural & Physical Sciences"},
    "fisheries_science": {"Agriculture & Environmental Systems", "Natural & Physical Sciences"},
    "philosophy": {"Knowledge, Humanities & Behavioural Sciences"},
}

PHYSICAL_CLUSTERS = {
    "Advanced Engineering & Physical Systems",
    "Natural & Physical Sciences",
}

# Recurrent symbolic leakage when the chart is already anchored by several
# independent physical/materials branches.  These are not globally rejected;
# the discount activates only under the dominant-physical-profile gate.
PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE = {
    "history_archaeology",
    "computational_social_science",
    "healthcare_management",
    "environmental_law",
    "civil_services",
    "fisheries_science",
    "public_health",
    "journalism_media",
    "mass_communication",
    "gender_studies",
    "rural_management",
    "visual_communication",
    "hotel_hospitality_management",
}


# Gap-audit fix (2026-08, chat cross-chart review): PHYSICAL_PROFILE_SYMBOLIC_
# LEAKAGE already existed to discount isolated cross-cluster symbolic matches,
# but its only trigger was `_dominant_physical_profile()` -- so it protected
# charts dominated by engineering clusters and did nothing for the opposite
# case. Across 4 unrelated charts (akash_shanmugham, thirukumaran, vaagesh,
# Vithun) "gender_studies" reached rank #1/#1/#15/#12 purely on generic
# Moon/Jupiter/Mercury affinity while its own dedicated career/education
# vargas (Dashamsha D10, Siddhamsha D24) scored far below the floor that a
# genuinely chart-supported field shows (observed: dashamsha 4.4-5.3,
# siddhamsha 27.7-28.4, vs. 40+ for fields with real career-house backing).
# This is the same "isolated symbolic match, no dedicated-varga corroboration"
# failure mode the existing gate targets -- just not conditioned on a
# dominant-physical profile. Added as an unconditional, narrowly-scoped
# second gate over the same PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE set.
UNCORROBORATED_CAREER_VARGA_FLOOR = 35.0
UNCORROBORATED_LEAKAGE_RANK_GUARD = 5

# Chart-relative floor fix (2026-08-20, Claude session, "field determination
# gaps" follow-up), superseded by the percentile-standing fix directly below
# (kept for history): UNCORROBORATED_CAREER_VARGA_FLOOR above is an ABSOLUTE
# constant on the 0-100 normalized scale, hand-tuned against charts where
# genuinely-supported fields cleared 40+ on Dashamsha/Siddhamsha. Dashamsha's
# own raw-score distribution runs systemically low on some charts, so an
# absolute 35.0 floor over-flags on those charts. A first fix made the floor
# a fraction of that chart's own max score per varga -- but this broke down
# on charts where BOTH vargas are compressed on the SAME chart (confirmed
# live on Ramsunder: Siddhamsha's own chart-wide ceiling was only ~13.6, so
# a 50%-of-max floor computed to ~6.8, and every field's siddhamsha sat in
# an 11-14 range -- everyone cleared that floor trivially, and the guard
# could never fire at all, on any field, regardless of how weak its
# dashamsha was). A magnitude-relative floor still assumes the chart's own
# ceiling is a meaningful reference point; when the whole distribution for a
# varga is nearly flat, magnitude comparison degenerates to "always pass".
#
# Percentile-standing fix (2026-08-20, Claude session): replaced magnitude
# comparison with RANK comparison -- does this field sit in the bottom half
# of THIS chart's own candidate pool on this varga, not "is its raw score
# below some fraction of the chart's ceiling". Percentile standing is scale-
# invariant: it cannot degenerate the way a magnitude-relative floor can,
# because a flat distribution still has a well-defined rank order (a field
# scoring 11.75 among values spanning 10.98-14.73 is unambiguously below the
# median, even though the RAW gap is tiny). See
# _career_varga_percentile_standings() below.
_CAREER_VARGA_PERCENTILE_THRESHOLD = 0.5  # bottom half of the chart's own pool on that varga


def _career_varga_percentile_standings(
    rows: List[Dict[str, Any]],
) -> tuple[Dict[str, float], Dict[str, float]]:
    """Return ({field_id: dashamsha_standing}, {field_id: siddhamsha_standing})
    for THIS chart's candidate pool. Standing is 1.0 for the field ranked
    highest on that varga, 0.0 for the field ranked lowest, linearly spaced
    in between by rank position (ties share the same standing as their tied
    peers get from stable sort order -- close enough for a bottom-half test,
    not used for anything finer-grained than that). Call once per ranking
    pass against the full pool and thread the result through to every
    _lacks_career_varga_corroboration() call in that pass, so all rows in
    the same pass are judged against the same standings.

    Excludes hard_lockout and exploratory_only rows from the reference pool
    (same rationale as the superseded _career_varga_reference_band(): those
    rows are often near-zero on both vargas precisely because they are
    contraindicated or non-competing, and letting them anchor the bottom of
    the distribution would inflate every real candidate's standing for free).
    """
    _eligible = [
        r for r in rows
        if not r.get("hard_lockout", False) and r.get("publication_eligibility") != "exploratory_only"
    ] or rows  # fall back to the unfiltered pool if filtering would leave nothing to measure against

    def _standings(key_norm: str, key_flat: str) -> Dict[str, float]:
        pairs: List[tuple[str, float]] = []
        for r in _eligible:
            norm = r.get("method_scores_normalized_0_100") or r.get("method_normalized_scores") or {}
            v = norm.get(key_norm, r.get(key_flat))
            if v is None:
                continue
            try:
                pairs.append((str(r.get("field_id", "")), float(v)))
            except (TypeError, ValueError):
                continue
        n = len(pairs)
        if n == 0:
            return {}
        if n == 1:
            return {pairs[0][0]: 1.0}
        ordered = sorted(pairs, key=lambda kv: -kv[1])
        return {fid: 1.0 - (i / (n - 1)) for i, (fid, _v) in enumerate(ordered)}

    return _standings("dashamsha", "dashamsha_score"), _standings("siddhamsha", "siddhamsha_score")


def _lacks_career_varga_corroboration(
    row: Dict[str, Any],
    dash_standings: Dict[str, float] | None = None,
    sidd_standings: Dict[str, float] | None = None,
    threshold: float = _CAREER_VARGA_PERCENTILE_THRESHOLD,
) -> bool:
    # Bug fix (2026-08 gap-audit, "fix both" round): this previously read
    # row["method_normalized_scores"], which never exists on a final row --
    # engine.py only ever sets that key on an earlier intermediate dict, then
    # explicitly renames it to "method_scores_normalized_0_100" before the
    # row reaches this module (see engine.py's "LS12 fix" line). The lookup
    # therefore always fell back to {}, so dashamsha/siddhamsha always
    # defaulted to 0.0 -- meaning this function silently returned True for
    # every field in the registry regardless of its real D10/D24 support,
    # since before this fix. Verified empirically on Aiswaryya's own results:
    # row.get("method_normalized_scores") was {} for all 35 fields even
    # though row["dashamsha_score"]/row["siddhamsha_score"] held real,
    # different values per field. Falls back to the legacy key too, in case
    # some upstream caller still populates it directly.
    norm = row.get("method_scores_normalized_0_100") or row.get("method_normalized_scores") or {}
    # gap fix 2026-08-18 (item 6 / Group 6): same failure class this
    # function's own comment above already describes fixing once for the
    # wrong-key-name case -- when NEITHER dashamsha nor siddhamsha data is
    # present anywhere on the row (no norm entry, no *_score key), that is
    # an absence of data, not a chart-confirmed near-zero career-varga
    # reading. Treating "unknown" the same as "confirmed unsupported" made
    # this guard (and its 0.55x discount) fire unconditionally on every
    # curated-list field ranking in the true top 5, even on rows that never
    # carried any method-score data at all (e.g. earlier pipeline stages,
    # partial payloads, or test fixtures exercising unrelated policy paths)
    # -- silently stacking a second ~45% discount on top of this module's
    # other, already-tested discount paths (dominant_physical_profile's own
    # gate, the career_route/context 0.90x boundary discount) whenever those
    # ran on rows lacking this data, an undocumented regression relative to
    # this guard's own "only when neither varga backs them up" contract.
    # Absence of data must not be scored as if it were confirmed weak
    # evidence; only a row that actually carries dashamsha/siddhamsha data
    # AND that data is genuinely below the floor lacks corroboration.
    _dashamsha_present = "dashamsha" in norm or "dashamsha_score" in row
    _siddhamsha_present = "siddhamsha" in norm or "siddhamsha_score" in row
    if not _dashamsha_present and not _siddhamsha_present:
        return False
    fid = str(row.get("field_id", ""))
    dash_standings = dash_standings or {}
    sidd_standings = sidd_standings or {}
    # A field present in the row but missing from the standings dict (e.g.
    # its value didn't parse as a float during _career_varga_percentile_
    # standings()) is treated as worst-standing (0.0) -- same "confirmed
    # unresolvable data counts as weak, absent data does not" split the
    # presence check above already enforces.
    dash_standing = dash_standings.get(fid, 0.0) if _dashamsha_present else 1.0
    sidd_standing = sidd_standings.get(fid, 0.0) if _siddhamsha_present else 1.0
    # Gap-audit fix (2026-08-19, chat session, "restore the absolute floor"
    # round): the percentile-standing fix (2026-08-20 comment above) replaced
    # UNCORROBORATED_CAREER_VARGA_FLOOR's absolute-magnitude test with a pure
    # RANK test specifically to fix the case where a varga's whole
    # distribution is compressed on one chart (the flat-siddhamsha case
    # documented above). But percentile standing has the mirror-image
    # failure: when the WHOLE POOL is weak on a varga (not just the top
    # field), "least weak of many weak fields" reads as a top-percentile
    # pass even though every field's absolute score is still near zero.
    # Confirmed live on Ramsunder's chart: dashamsha's normalized_score never
    # exceeded 9.85/100 across all 35 candidate fields, yet
    # agricultural_food_engineering's 8.42 landed at the 94th percentile of
    # that uniformly-weak pool and cleared this guard entirely, undiscounted,
    # while carrying essentially no real D10 support (Parashara treats
    # Dashamsha as THE authoritative career varga -- a field should not be
    # able to claim corroboration purely by outranking 33 other equally weak
    # fields). Fix: restore the absolute floor as an OR alongside percentile
    # standing, not a replacement for it -- each varga's own emptiness check
    # now fires if EITHER signal says weak, so a chart-wide-compressed
    # distribution can no longer let percentile standing alone wave a
    # genuinely near-zero absolute score through. Both tests are kept
    # (rather than reverting to the absolute-only original) because the
    # absolute floor still has ITS OWN documented degenerate case (the
    # flat-siddhamsha chart where the guard could never fire at all) --
    # each test alone is incomplete; together they cover both directions.
    dash_weak = dash_standing < threshold or (
        _dashamsha_present and float(norm.get("dashamsha", row.get("dashamsha_score", 0.0)) or 0.0) < UNCORROBORATED_CAREER_VARGA_FLOOR
    )
    sidd_weak = sidd_standing < threshold or (
        _siddhamsha_present and float(norm.get("siddhamsha", row.get("siddhamsha_score", 0.0)) or 0.0) < UNCORROBORATED_CAREER_VARGA_FLOOR
    )
    return dash_weak and sidd_weak


def _cluster(row: Dict[str, Any]) -> str:
    return str(row.get("graph_cluster") or row.get("competency_label") or "")


def _family(row: Dict[str, Any]) -> str:
    # Mirrors hierarchical_ranking.py's own family lookup and
    # tiered_ranking.py's identically-named helper (kept in sync
    # deliberately -- see the cluster-support-exemption fix below).
    ontology = row.get("ontology_v12") or {}
    return str(ontology.get("primary_family") or row.get("domain") or "unclassified")



# Gap-audit fix (2026-08-18, Claude session, following the structural-gaps
# remediation plan): apply_uncorroborated_leakage_guards() below only ever
# checks out[:UNCORROBORATED_LEAKAGE_RANK_GUARD] (the true top 5) -- a field
# ranking anywhere from 6 to _LOW_DIFFERENTIATION_RANK_END (20, the window
# _annotate_rank_differentiation() in this same file already treats as real,
# displayed output) currently gets ZERO corroboration checking. Verified
# live on Lakshman's real chart run: every field at ranks 6-20 carried
# corroboration_checked=False before this fix (the key simply didn't exist).
#
# Deliberately does NOT extend the 45%-discount score mutation past rank 5.
# That multiplicative discount was hand-tuned against specific real-chart
# headline-risk failures (Ramsunder, Aiswaryya, akash_shanmugham, etc. --
# see the guards above and in tiered_ranking.py); applying the same
# magnitude further down the list without equivalent real-chart validation
# risks destabilizing already-tuned rank-6-35 behavior for existing charts.
# Instead this is a TRANSPARENCY fix, matching how this file already treats
# differentiation (annotate, don't silently truncate or re-score): every
# field from rank 6 through _LOW_DIFFERENTIATION_RANK_END gets an explicit,
# auditable `corroboration_checked` / `lacks_career_varga_corroboration`
# flag pair, visible to any consumer (report renderer, LLM narrative
# builder, API response) that wants to warn a reader "this rank position is
# not backed by a dedicated career varga" -- something the pipeline could
# not previously say about ranks 6-20 at all, positive or negative.
_WIDE_CORROBORATION_CHECK_RANK_START = UNCORROBORATED_LEAKAGE_RANK_GUARD + 1  # 6
_WIDE_CORROBORATION_CHECK_RANK_END = 20  # matches _LOW_DIFFERENTIATION_RANK_END below


_LEGACY_LEAKAGE_ADJUSTMENT_MARKERS = (
    "uncorroborated_generic_affinity",
    "dominant_physical_profile",
)


def reconcile_legacy_leakage_annotations(out: List[Dict[str, Any]]) -> None:
    """Clear up a stale-audit-trail gap (2026-08-18, Claude session, found
    while validating annotate_wide_corroboration_visibility() live on
    Lakshman's chart): apply_uncorroborated_leakage_guards() /
    reapply_leakage_guards_post_lockout() discount `final_score` BEFORE
    compute_tiered_ranking() runs. compute_tiered_ranking() then recomputes
    `final_score` from scratch (from `tier1_score`, built independently off
    raw method scores -- see its own docstring), discarding that earlier
    discount entirely for any field whose OWN tier1-based corroboration
    check (`tier1_leakage_discounted`) didn't independently also catch it
    (e.g. because tiered_ranking.py's cluster-support exemption fired even
    though the earlier, pre-tiered guard's did not, or vice versa -- the two
    passes check different score bases and can legitimately disagree).

    Confirmed live: computational_social_science carried an explicit
    "discounted 45%" adjustment note from the pre-tiered guard while ranking
    #1 in the actually-shipped, undiscounted tiered output -- a reader of
    `publication_ranking_adjustments` would reasonably but wrongly conclude
    the shipped score already reflects that discount.

    This does not re-decide anything -- it only makes the note honest: for
    any row carrying a legacy leakage-guard adjustment whose
    `tier1_leakage_discounted` is not True (i.e. the discount that note
    describes did not survive into the shipped tiered score), append a
    clarifying note. Must run AFTER compute_tiered_ranking() has set
    `tier1_leakage_discounted` on every row.
    """
    for row in out:
        adjustments = row.get("publication_ranking_adjustments") or []
        if not adjustments:
            continue
        has_legacy_note = any(
            marker in adj for adj in adjustments for marker in _LEGACY_LEAKAGE_ADJUSTMENT_MARKERS
        )
        if not has_legacy_note:
            continue
        if row.get("tier1_leakage_discounted"):
            continue  # tiered ranking's own pass independently confirmed and reapplied it -- note is accurate
        _append_adjustment(
            row,
            "note: the discount described above was applied to the pre-tiered "
            "final_score and was superseded when tiered ranking recomputed "
            "final_score independently -- it did NOT reduce this field's "
            "shipped score or rank. See tier1_leakage_discounted (False here) "
            "for whether tiered ranking's own corroboration check also flagged this field.",
        )


def _annotate_wide_corroboration_visibility(out: List[Dict[str, Any]]) -> None:
    """Flag (never discount) corroboration status for ranks 6-20.

    Trusts each row's existing `rank` field rather than re-sorting by
    final_score (mirrors `_annotate_rank_differentiation`'s own pattern,
    just below) -- this must run at the call site where `rank` already
    reflects the truly-published order (i.e. after compute_tiered_ranking()
    in engine.py, same call site as annotate_rank_differentiation()), not
    from inside the pre-tiered leakage-guard passes, whose own row order at
    that point is not yet the final one. Mutates `out` in place.
    """
    dash_st, sidd_st = _career_varga_percentile_standings(out)
    for row in out:
        row.setdefault("corroboration_checked", False)
        row.setdefault("lacks_career_varga_corroboration", None)
    for row in out:
        rank = int(row.get("rank", 0) or 0)
        if not (_WIDE_CORROBORATION_CHECK_RANK_START <= rank <= _WIDE_CORROBORATION_CHECK_RANK_END):
            continue
        row["corroboration_checked"] = True
        lacks = _lacks_career_varga_corroboration(row, dash_st, sidd_st)
        row["lacks_career_varga_corroboration"] = lacks
        if lacks:
            _append_adjustment(
                row,
                f"diagnostic: rank {rank} has no Dashamsha/Siddhamsha career-varga "
                "support above the corroboration floor -- visible for transparency, "
                "not discounted (see _annotate_wide_corroboration_visibility docstring)",
            )


def annotate_wide_corroboration_visibility(out: List[Dict[str, Any]]) -> None:
    """Public entry point -- call after the FINAL publication rank is known
    (i.e. after compute_tiered_ranking(), same call site as
    annotate_rank_differentiation()), not from inside the pre-tiered
    leakage-guard passes above, since compute_tiered_ranking() re-ranks
    everything those passes saw."""
    _annotate_wide_corroboration_visibility(out)


def apply_uncorroborated_leakage_guards(out: List[Dict[str, Any]]) -> None:
    """Discount fields ranking in the true top 5 purely on generic affinity,
    with no dedicated career-varga (Dashamsha/Siddhamsha) support and no
    same-cluster corroboration among the astrological top 10. Mutates `out`
    in place; caller is responsible for re-sorting/re-ranking afterward.

    Extracted (2026-08 gap-audit, "fix both, then yes" round) so the exact
    same guard logic can run a second time in engine._finalize_published_
    results(), after _enforce_hard_lockout_publication_order() -- see the
    call site there for why a single in-function placement is not enough:
    hard-lockout reordering can promote a field into the true top 5 purely
    by demoting hard_lockout/exploratory rows above it, without touching
    final_score at all, so a guard that only runs inside
    apply_publication_ranking_policy() can still miss it (confirmed on
    Aiswaryya's chart: chemistry reached rank 3 this way and was invisible
    to both guard passes inside this function).
    """
    out.sort(key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))))
    dash_st, sidd_st = _career_varga_percentile_standings(out)

    # Unconditional generic-affinity leakage guard (see comment on
    # _lacks_career_varga_corroboration above). Only fires for fields already
    # on the curated PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE list, only when they
    # are ranking implausibly high (top 5 of the whole registry), and only
    # when neither dedicated career varga backs them up -- so it cannot touch
    # a field that has genuine D10/D24 support, however it scored elsewhere.
    for index, row in enumerate(out[:UNCORROBORATED_LEAKAGE_RANK_GUARD]):
        fid = str(row.get("field_id", ""))
        if fid not in PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE:
            continue
        if "dominant_physical_profile" in " ".join(row.get("publication_ranking_adjustments", [])):
            continue  # already discounted by the profile-specific gate above
        if "uncorroborated_generic_affinity" in " ".join(row.get("publication_ranking_adjustments", [])):
            continue  # already discounted by an earlier pass of this same guard
        if not _lacks_career_varga_corroboration(row, dash_st, sidd_st):
            continue
        old = float(row.get("final_score", 0.0) or 0.0)
        row["final_score"] = round(old * 0.55, 4)
        _append_adjustment(
            row,
            "uncorroborated_generic_affinity: top-5 rank rests on generic "
            "Moon/Jupiter/Mercury affinity with no Dashamsha/Siddhamsha "
            "career-varga support -- discounted 45%",
        )

    # Generalized guard: same signals, without requiring curated-list
    # membership, so coverage doesn't depend on someone having hand-added
    # the field name in advance. Still a bounded, auditable final_score
    # adjustment inside this module's own established authority -- not the
    # blocked defensibility/ranking_effect layer.
    out.sort(key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))))
    astro_head_for_isolation = sorted(
        out, key=lambda r: -float(r.get("astrological_score", r.get("final_score", 0.0)) or 0.0)
    )[:10]
    for index, row in enumerate(out[:UNCORROBORATED_LEAKAGE_RANK_GUARD]):
        fid = str(row.get("field_id", ""))
        if fid in PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE:
            continue  # already handled by the curated-list guard above
        adjustments_so_far = " ".join(row.get("publication_ranking_adjustments", []))
        if "dominant_physical_profile" in adjustments_so_far or "uncorroborated_generic_affinity" in adjustments_so_far:
            continue
        if not _lacks_career_varga_corroboration(row, dash_st, sidd_st):
            continue
        # Gap-audit fix (2026-08-18, Claude session): raw same-cluster field
        # count let near-synonymous registry entries "corroborate" each
        # other (confirmed live: 8 of Lakshman's top-10 astrological fields
        # share one graph_cluster and mostly one competency_ontology family
        # -- see the identical fix and full rationale in
        # tiered_ranking.py::_apply_generalized_corroboration_discount).
        # Now requires DISTINCT families among same-cluster co-members, not
        # just distinct field_ids.
        #
        # Round 2 (2026-08-19, Claude session): distinct family labels
        # alone still weren't enough -- confirmed live on Ramsunder's chart,
        # a whole cluster of both families' members were themselves all
        # uncorroborated (see the matching round-2 fix and full rationale in
        # tiered_ranking.py). A same-cluster, different-family field only
        # counts if it does NOT ALSO lack career-varga corroboration itself.
        row_family = _family(row)
        corroborating_families = {
            _family(r) for r in astro_head_for_isolation
            if r is not row
            and _cluster(row) and _cluster(r) == _cluster(row)
            and _family(r) != row_family
            and not _lacks_career_varga_corroboration(r, dash_st, sidd_st)
        }
        if len(corroborating_families) >= 2:
            continue  # genuinely distinct families, each with real career-varga support of their own
        old = float(row.get("final_score", 0.0) or 0.0)
        row["final_score"] = round(old * 0.55, 4)
        _append_adjustment(
            row,
            "uncorroborated_generic_affinity_general: top-5 rank rests on generic "
            "affinity with no Dashamsha/Siddhamsha career-varga support and no "
            "same-cluster corroboration in the astrological top 10 -- discounted 45%",
        )


def reapply_leakage_guards_post_lockout(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-run the uncorroborated-leakage guards against the rank order that
    actually ships, after engine._enforce_hard_lockout_publication_order()
    has pushed hard_lockout/exploratory rows to the bottom. Re-sorts and
    returns `results`; caller must re-run
    _enforce_hard_lockout_publication_order() afterward to restamp `rank`,
    since a fresh discount here can in principle change relative order
    within the "valid" group. See apply_uncorroborated_leakage_guards()
    docstring for why this second pass is necessary at all.
    """
    apply_uncorroborated_leakage_guards(results)
    results.sort(key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))))
    return results


def _dominant_physical_profile(rows: List[Dict[str, Any]]) -> bool:
    """Require breadth, score share and rank strength--not one lucky field."""
    head = rows[:10]
    physical = [r for r in head if _cluster(r) in PHYSICAL_CLUSTERS]
    if len(physical) < 3:
        return False
    total = sum(max(0.0, float(r.get("final_score", 0.0) or 0.0)) for r in head)
    physical_total = sum(max(0.0, float(r.get("final_score", 0.0) or 0.0)) for r in physical)
    return bool(total and physical_total / total >= 0.32 and any(r in physical for r in head[:3]))


def _append_adjustment(row: Dict[str, Any], note: str) -> None:
    row.setdefault("publication_ranking_adjustments", []).append(note)


_SHADOW_TOP_N = 20


def _shadow_position(row: Dict[str, Any]) -> int | None:
    margin = row.get("meaningful_margin") or {}
    pos = margin.get("shadow_position")
    try:
        return int(pos) if pos is not None else None
    except (TypeError, ValueError):
        return None


def _shadow_supports_top20(row: Dict[str, Any]) -> bool:
    """True when the engine's own independent shadow/meaningful-margin audit
    (attach_meaningful_margin_tiers, run earlier in apply_release_4_7 --
    before this function -- so it's already attached by the time this runs)
    places this field within the top-N band on its own, method-robustness
    evidence rather than the blended publication score.

    2026-07-19 audit gap fix: civil_services/research_academia were both
    blanket-discounted 0.90x and clamped below the Top 20 purely because of
    their field_role, with no check on whether the underlying chart evidence
    actually supported that demotion. Cross-checking a real chart found the
    two fields diverge sharply: civil_services' shadow_position was 4 (the
    independent audit thinks it's one of the strongest fields in the whole
    run) while research_academia's was 26 (the independent audit agrees it
    belongs outside the top 20). Blanket-discounting both identically was
    wrong for civil_services specifically. This exemption lets a field_role
    discount be skipped when the field's own shadow ranking already argues
    for a high placement, while still applying the discount by default when
    shadow evidence is missing, inconclusive, or itself agrees with the
    demotion (i.e. no exemption unless the evidence explicitly earns it).
    """
    pos = _shadow_position(row)
    return pos is not None and pos <= _SHADOW_TOP_N


def apply_publication_ranking_policy(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return annotated rows in honest descending publication-score order."""
    out = [dict(r) for r in rows]
    out.sort(key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))))

    for row in out:
        fid = str(row.get("field_id", ""))
        row["field_role"] = FIELD_ROLES.get(fid, "educational_field")
        row["astrological_score"] = float(row.get("final_score", 0.0) or 0.0)
        # 2026-08-18 gap fix: publication_ranking_adjustments/score_ceiling_tie
        # were only ever set via row.setdefault(...)/conditional assignment
        # further down this pipeline, so a row that never triggers any
        # adjustment or ceiling-tie condition never gets these keys at all --
        # a genuine per-row shape drift (confirmed on business_management:
        # every OTHER row got both keys, this one got neither, since it never
        # hit any of the conditional branches below). Every row must share the
        # same key set per html_payload_contract.RESULTS_ROW_KEYS, so seed
        # both keys here with their natural "nothing happened" defaults before
        # any conditional logic runs; later code still safely
        # .setdefault(...).append(...)/overwrites these in place.
        row.setdefault("publication_ranking_adjustments", [])
        row.setdefault("score_ceiling_tie", False)

    if _dominant_physical_profile(out):
        for row in out:
            fid = str(row.get("field_id", ""))
            old = float(row.get("final_score", 0.0) or 0.0)
            if fid in PHYSICAL_PROFILE_SYMBOLIC_LEAKAGE:
                factor = 0.48 if fid in {
                    "journalism_media", "mass_communication", "public_health",
                    "fisheries_science", "healthcare_management",
                } else 0.68
                row["final_score"] = round(old * factor, 4)
                _append_adjustment(
                    row,
                    "dominant_physical_profile: isolated cross-cluster symbolic match "
                    f"discounted {1.0-factor:.0%}",
                )

        # Re-evaluate the boundary after leakage is removed.  Otherwise a
        # strong physical field temporarily displaced by symbolic noise can
        # receive a preservation boost and leapfrog its natural peers.
        provisional = sorted(
            out,
            key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))),
        )
        for index, row in enumerate(provisional):
            old = float(row.get("final_score", 0.0) or 0.0)
            if index >= 10 and _cluster(row) in PHYSICAL_CLUSTERS and old >= 30:
                row["final_score"] = round(old * 1.05, 4)
                _append_adjustment(
                    row,
                    "dominant_physical_profile: supported lower-ranked physical/technical branch +5%",
                )

    by_id = {str(r.get("field_id", "")): r for r in out}
    for child_id, parent_id in SPECIALIZATION_PARENTS.items():
        child, parent = by_id.get(child_id), by_id.get(parent_id)
        if not child:
            continue
        child["field_role"] = "specialization"
        child["foundation_field_id"] = parent_id
        if not parent:
            _append_adjustment(
                child,
                f"taxonomy: specialization mapped to broad foundation {parent_id}",
            )
            continue
        child_score = float(child.get("final_score", 0.0) or 0.0)
        parent_score = float(parent.get("final_score", 0.0) or 0.0)
        if child_score >= parent_score and parent_score > 0:
            child["final_score"] = round(parent_score * 0.97, 4)
            _append_adjustment(
                child,
                f"broad_foundation_first: capped below {parent_id}; retain as specialization",
            )

    # Cross-domain plausibility veto: narrow fields need at least two supporting
    # fields from their own cluster in the astrological top ten.
    astro_head = sorted(out, key=lambda r: -float(r.get("astrological_score", r.get("final_score", 0.0)) or 0.0))[:10]
    for fid, allowed_clusters in NARROW_FIELD_CLUSTERS.items():
        row = by_id.get(fid)
        if not row:
            continue
        support = sum(1 for r in astro_head if r is not row and _cluster(r) in allowed_clusters)
        row["narrow_field_domain_support"] = support
        if support < 2:
            old = float(row.get("final_score", 0.0) or 0.0)
            row["final_score"] = round(old * 0.55, 4)
            row["publication_eligibility"] = "exploratory_only"
            _append_adjustment(row, "narrow_field_gate: fewer than two independent same-domain fields in astrological top 10")

    # Career routes and work contexts remain visible but cannot masquerade as
    # undergraduate fields.  A small bounded discount resolves close calls;
    # the role annotation is the primary semantic fix. Skip the discount when
    # the field's own shadow/meaningful-margin audit independently supports a
    # top-20 placement -- see _shadow_supports_top20 for why.
    for row in out:
        role = row.get("field_role")
        if role not in {"career_route", "career_context"}:
            continue
        if _shadow_supports_top20(row):
            _append_adjustment(
                row,
                f"field_role={role}: publication discount waived -- shadow audit "
                f"position {_shadow_position(row)} independently supports top-{_SHADOW_TOP_N} placement",
            )
            continue
        old = float(row.get("final_score", 0.0) or 0.0)
        row["final_score"] = round(old * 0.90, 4)
        _append_adjustment(row, f"field_role={role}: separated from degree-field ranking")

    # If the registry supplies at least twenty actual fields/specializations,
    # keep career routes and work contexts in the full result set but below
    # the published Top 20 boundary.  This fixes taxonomy without deletion.
    educational_scores = sorted(
        (
            float(r.get("final_score", 0.0) or 0.0)
            for r in out
            if r.get("field_role") in {"educational_field", "specialization"}
        ),
        reverse=True,
    )
    if len(educational_scores) >= 20:
        boundary = educational_scores[19]
        for row in out:
            if row.get("field_role") not in {"career_route", "career_context"}:
                continue
            if _shadow_supports_top20(row):
                continue
            score = float(row.get("final_score", 0.0) or 0.0)
            if score >= boundary:
                row["final_score"] = round(boundary * 0.97, 4)
                _append_adjustment(
                    row,
                    "field_type_boundary: retained outside degree-field Top 20",
                )

    # Enforce exploratory-only narrow fields at the publication boundary as
    # well as by score discount. This guarantees they cannot remain in Top 20
    # merely because the score distribution has a low normalized tail.
    publishable_scores = sorted(
        (float(r.get("final_score", 0.0) or 0.0) for r in out
         if r.get("field_role") in {"educational_field", "specialization"}
         and r.get("publication_eligibility") != "exploratory_only"),
        reverse=True,
    )
    if len(publishable_scores) >= 20:
        boundary = publishable_scores[19]
        for row in out:
            if row.get("publication_eligibility") != "exploratory_only":
                continue
            if float(row.get("final_score", 0.0) or 0.0) >= boundary:
                row["final_score"] = round(boundary * 0.95, 4)
                _append_adjustment(row, "narrow_field_boundary: retained outside published Top 20")

    # Parent-child coherence for interdisciplinary hybrids. Missing parents do
    # not manufacture evidence; present parents constrain the hybrid to the
    # strongest constituent plus a small, explicit synergy allowance.
    #
    # Gap-audit fix (2026-08): this block used to run BEFORE the narrow-field
    # gate, the career-route discount, and both publication-boundary blocks
    # above -- so a hybrid's ceiling/imbalance check was computed against its
    # parents' final_score at that early point, not their true post-adjustment
    # score. With today's curated HYBRID_PARENTS entries none of the parents
    # (economics/statistics_data_science/econometrics,
    # chemical_engineering/data_science_engineering) happen to be touched by
    # those later stages, so this was not yet live-wrong -- but it was
    # structurally fragile: the moment a hybrid's parent is ever also subject
    # to a later discount, the hybrid would be coherence-checked against a
    # stale, too-high parent score and could remain implausibly ranked above
    # its now-lower parent. Moved to run last, after every other score
    # adjustment, so the hybrid is always constrained by its parents' true
    # final publication score.
    for hybrid_id, parent_ids in HYBRID_PARENTS.items():
        hybrid = by_id.get(hybrid_id)
        parents = [by_id[p] for p in parent_ids if p in by_id]
        if not hybrid or not parents:
            continue
        scores = [float(p.get("final_score", 0.0) or 0.0) for p in parents]
        ceiling = max(scores) + HYBRID_SYNERGY_CAP
        old = float(hybrid.get("final_score", 0.0) or 0.0)
        if old > ceiling:
            hybrid["final_score"] = round(ceiling, 4)
            _append_adjustment(hybrid, f"hybrid_coherence: capped at strongest parent +{HYBRID_SYNERGY_CAP:g}")
        if len(scores) >= 2 and min(scores) < 0.50 * max(scores):
            hybrid["final_score"] = round(min(float(hybrid.get("final_score", 0.0)), max(scores) * 0.92), 4)
            _append_adjustment(hybrid, "hybrid_coherence: mandatory parent support is imbalanced")

    # Ordering fix (2026-08 gap-audit, "fix both" round): the leakage guards
    # (now in apply_uncorroborated_leakage_guards(), see its docstring) used
    # to run immediately after the dominant_physical_profile block, before
    # specialization capping, narrow_field_gate, and hybrid_coherence (just
    # above) had a chance to move fields in or out of the top-5 window. This
    # is the last point inside this function where they can run and still
    # see every final_score-shifting step this function itself performs --
    # but engine._finalize_published_results() runs a second pass afterward
    # too, since _enforce_hard_lockout_publication_order() can promote a
    # field into the true top 5 without this function ever seeing it.
    apply_uncorroborated_leakage_guards(out)

    out.sort(key=lambda r: (-float(r.get("final_score", 0.0) or 0.0), str(r.get("field_id", ""))))
    for rank, row in enumerate(out, 1):
        row["rank"] = rank
        row["publication_score"] = float(row.get("final_score", 0.0) or 0.0)

    # NOTE: rank-differentiation annotation deliberately NOT run here. This
    # function's `rank` gets restamped again by
    # engine._enforce_hard_lockout_publication_order() (which runs after this
    # function returns and pushes hard_lockout/exploratory rows to the
    # bottom, shifting valid rows up). Annotating against the pre-restamp
    # rank window would mislabel whichever rows later shift into ranks 6-20.
    # Call annotate_rank_differentiation(out) again from
    # engine._finalize_published_results(), after the hard-lockout restamp,
    # so ranks 6-20 mean what they mean in the actually-published order.
    return out


def annotate_rank_differentiation(out: List[Dict[str, Any]]) -> None:
    """Public entry point -- call after the final publication rank restamp."""
    _annotate_rank_differentiation(out)


# Gap-audit fix (2026-08, chat cross-chart review): two distinct low-signal
# patterns were observed with no diagnostic surfaced to the consumer --
# (1) ramsunder: computational_finance and econometrics both landed at the
# 100.00 ceiling, so their #1-vs-#2 ordering carries no real information; and
# (2) siddarth: ranks 6-20 were bunched inside a ~0.2-point band with unusually
# low structural-fit values, i.e. noise rather than a meaningful ordering.
# Neither is a bug in the score itself -- both are legitimate outputs of a
# chart with thin/low-differentiation evidence past the head of the list --
# but a report reader has no way to tell "meaningfully ranked" from "noise"
# without this. Both are now flagged inline on the affected rows.

# Scale fix (2026-08-18, tiered-ranking rollout): these two constants used
# to be absolute point gaps, calibrated against the old flat 9-method
# blend's ~45-100 final_score range (0.5 pts ~= 0.5% of a ~100-point
# ceiling; 3.0 pts ~= ~3% of that same ceiling on the ramsunder/siddarth
# examples above). jyotish/tiered_ranking.py can now produce a much
# lower/tighter absolute range (e.g. ~13-27 on a real chart, a ~14-point
# total spread) -- a fixed 3.0-point band there is over 20% of the WHOLE
# range instead of a narrow slice, so low_rank_differentiation would fire
# on nearly every chart's ranks 6-20 regardless of how well-differentiated
# they actually are, turning a real diagnostic into permanent noise.
# Expressed as ratios of top_score below instead, preserving the original
# 0.5%/3% ratios these constants implied -- correct regardless of which
# ranking authority (flat blend or tiered) produced final_score.
_SCORE_CEILING_TIE_RATIO = 0.005    # was: _SCORE_CEILING_TIE_EPSILON = 0.5 (~0.5% of a ~100-pt ceiling)
_LOW_DIFFERENTIATION_SPREAD_RATIO = 0.03  # was: _LOW_DIFFERENTIATION_SPREAD = 3.0 (~3% of a ~100-pt ceiling)
_LOW_DIFFERENTIATION_RANK_START = 6
_LOW_DIFFERENTIATION_RANK_END = 20


def _annotate_rank_differentiation(out: List[Dict[str, Any]]) -> None:
    if not out:
        return
    top_score = float(out[0].get("final_score", 0.0) or 0.0)
    score_ceiling_tie_epsilon = top_score * _SCORE_CEILING_TIE_RATIO
    low_differentiation_spread = top_score * _LOW_DIFFERENTIATION_SPREAD_RATIO
    for row in out:
        # 2026-08-18 gap fix: seed the same defaults here too, belt-and-
        # suspenders against apply_publication_ranking_policy()'s equivalent
        # seeding (see that function) -- compute_tiered_ranking() runs
        # between the two and is not guaranteed to preserve every key on
        # every row dict it produces, so this final annotation pass must not
        # assume the earlier seeding survived intact for every row.
        row.setdefault("score_ceiling_tie", False)
        row.setdefault("publication_ranking_adjustments", [])
        score = float(row.get("final_score", 0.0) or 0.0)
        if top_score - score <= score_ceiling_tie_epsilon and score > 0:
            row["score_ceiling_tie"] = True
            _append_adjustment(
                row,
                "diagnostic: within the score-ceiling tie band of the top result -- "
                "treat this rank position as not meaningfully differentiated",
            )

    window = [
        r for r in out
        if _LOW_DIFFERENTIATION_RANK_START <= int(r.get("rank", 0)) <= _LOW_DIFFERENTIATION_RANK_END
    ]
    if len(window) < 2:
        return
    scores = [float(r.get("final_score", 0.0) or 0.0) for r in window]
    spread = max(scores) - min(scores)
    if spread <= low_differentiation_spread:
        for row in window:
            row["low_rank_differentiation"] = True
            _append_adjustment(
                row,
                f"diagnostic: ranks {_LOW_DIFFERENTIATION_RANK_START}-{_LOW_DIFFERENTIATION_RANK_END} "
                f"span only {spread:.2f} points -- treat this band as low-confidence ordering, "
                "not a reliable ranking",
            )
