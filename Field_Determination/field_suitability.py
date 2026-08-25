"""Professional route-suitability classification for ranked career fields.

This layer does not change astrological aptitude rank. It separates chart
alignment, academic compatibility, education feasibility and career viability
so a PG-dependent or niche field is not mislabeled as astrologically rejected.

Gap-audit fix (2026-08, documentation-only cross-reference): this module is
one of THREE similarly-named "field suitability"-adjacent modules in this
package, each with a distinct, non-overlapping contract and version string.
None previously referenced the others, which was flagged as a discoverability
risk for future maintainers. For the full picture:
  - field_suitability.py (this file, version-less/route-suitability.v3
    internally) -- ASTROLOGICAL-vs-PRACTICAL route recommendation
    (Primary/Conditional/PG-route/Exploratory/Not-recommended), consumed by
    the report layer. THIS is the one that produces the final Recommended-as-
    Primary-style label shown to end users.
  - structural_vocational_fit.py (STRUCTURAL_FIT_VERSION =
    "structural-vocational-fit.r4.shadow.v1") -- an explicitly
    NON-authoritative ("shadow") diagnostic blending D1/D10/KP/Jaimini/
    Sudarshana sub-scores into one "structural fit" number for QA/debugging,
    not shown as a user-facing recommendation.
  - exact_field_defensibility.py (EXACT_FIELD_CONTRACT_VERSION =
    "exact-field-defensibility.r9.v1") -- population-aware sibling/
    uniqueness distinguishability check (is this field defensibly distinct
    from near-identical siblings for THIS chart), also non-authoritative.
None of the three reads or calls the others; they are independent diagnostic
layers that happen to sit next to each other in the same package.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

# GAP FIX (2026-08-18, audit item B): shared "absent data vs. genuinely low
# score" utility, retrofitted into _education_score/_career_score below
# (see common.py's scored_dimension docstring for the full rationale; this
# import is the only change those two functions' plumbing needed -- their
# score FORMULAS are unchanged).
from Field_Determination.field_methods.common import scored_dimension


STATUS_PRIMARY = "Recommended as Primary"
STATUS_CONDITIONAL = "Recommended with Conditions"
STATUS_PG = "Better as a Specialization or PG Route"
STATUS_EXPLORATORY = "Exploratory or Secondary Option"
STATUS_NOT_PRIMARY = "Not Recommended as Primary"
STATUS_REQUIRES_VALIDATION = "Requires Academic Validation"

SUBJECT_REQUIREMENTS = {
    "math_intensity": "mathematics", "physics_intensity": "physics",
    "chemistry_intensity": "chemistry", "biology_intensity": "biology",
    "coding_intensity": "coding", "writing_intensity": "writing",
    "people_interaction": "people_interaction", "fieldwork_intensity": "fieldwork",
}

# Explicit route requirements override noisy registry intensity fields.  A hard
# requirement is an eligibility veto; a core requirement must be validated
# before a primary recommendation; optional competencies never block a route.
HARD_ELIGIBILITY: Dict[str, tuple[str, ...]] = {
    "veterinary_science": ("biology",),
    "fisheries_science": ("biology",),
    "medicine_mbbs": ("biology", "chemistry", "physics"),
    "dentistry_bds": ("biology", "chemistry", "physics"),
    "nursing": ("biology",),
}
CORE_APTITUDE: Dict[str, tuple[str, ...]] = {
    "industrial_engineering": ("mathematics", "physics"),
    "statistics_data_science": ("mathematics",),
    "data_science_engineering": ("mathematics",),
    "economics_data_science": ("mathematics",),
    "econometrics": ("mathematics",),
    "architecture": ("mathematics",),
    "journalism_media": ("writing",),
    "philosophy": ("writing",),
    "gender_studies": ("writing",),
    "operations_research": ("mathematics",),
    "information_systems": ("mathematics",),
    "it_systems_planning": ("mathematics",),
    "software_infrastructure_engineering": ("mathematics",),
    "engineering_management": ("mathematics",),
    "it_business_advisory": (),
    "it_governance": ("writing",),
    "law_llb": ("writing",),
    "environmental_law": ("writing",),
    "educational_technology": ("writing",),
    "intelligence_security": ("writing",),
    "intelligence_security_studies": ("writing",),
    "computational_social_science": ("mathematics",),
    "urban_informatics": ("mathematics",),
    "history_archaeology": ("writing",),
    "international_law": ("writing",),
    "ca_cma_cs_professional": ("mathematics",),
}
OPTIONAL_COMPETENCIES: Dict[str, tuple[str, ...]] = {
    "architecture": ("coding",),
    "economics_data_science": ("coding",),
    "econometrics": ("coding",),
}


def _field_id(row: Mapping[str, Any]) -> str:
    return str(row.get("field_id") or row.get("branch_id") or "")


def _requirements(row: Mapping[str, Any], curriculum: Mapping[str, Any]) -> Dict[str, list[str]]:
    fid = _field_id(row)
    hard = list(HARD_ELIGIBILITY.get(fid, ()))
    explicit_core = CORE_APTITUDE.get(fid)
    if explicit_core is not None:
        core = list(explicit_core)
    else:
        core = []
        subject_text = " ".join(str(x).lower() for x in curriculum.get("core_subjects_ug", []) or [])
        subject_tokens = {
            "mathematics": ("math", "quantitative", "statistics"),
            "physics": ("physics",), "chemistry": ("chemistry",),
            "biology": ("biology", "life science"),
            "coding": ("programming", "coding", "computer"),
            "writing": ("writing", "literature", "communication"),
        }
        for profile_key, tokens in subject_tokens.items():
            if profile_key not in hard and any(token in subject_text for token in tokens):
                core.append(profile_key)
    optional = list(OPTIONAL_COMPETENCIES.get(fid, ()))
    return {"hard_eligibility": hard, "core_aptitude": core, "optional_competency": optional}


def _section(row: Mapping[str, Any], key: str) -> Dict[str, Any]:
    direct = row.get(key)
    if isinstance(direct, dict) and direct:
        return direct
    v12 = row.get("registry_v12") or row.get("registry") or {}
    value = v12.get(key, {}) if isinstance(v12, Mapping) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def _academic_score(requirements: Mapping[str, list[str]], curriculum: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[Optional[float], list[str], list[str], list[str]]:
    weighted, weights, missing, contraindications, hard_failures = 0.0, 0.0, [], [], []
    subjects = requirements.get("hard_eligibility", []) + requirements.get("core_aptitude", [])
    for profile_key in dict.fromkeys(subjects):
        raw = profile.get(profile_key)
        if raw is None:
            kind = "eligibility" if profile_key in requirements.get("hard_eligibility", []) else "aptitude"
            missing.append(f"{profile_key.replace('_', ' ').title()} {kind} evidence not supplied")
            continue
        try:
            ability = float(raw)
            if ability > 1.0: ability /= 100.0
            ability = max(0.0, min(1.0, ability))
        except (TypeError, ValueError):
            missing.append(f"{profile_key.replace('_', ' ').title()} value is invalid")
            continue
        intensity_key = next((k for k, v in SUBJECT_REQUIREMENTS.items() if v == profile_key), "")
        weight = max(0.8, float(curriculum.get(intensity_key, 4) or 4) / 5.0)
        weighted += ability * 100.0 * weight; weights += weight
        if ability < 0.40:
            message = f"Low validated {profile_key.replace('_', ' ')} fit for a required curriculum"
            contraindications.append(message)
            if profile_key in requirements.get("hard_eligibility", []):
                hard_failures.append(message)
    return (round(weighted / weights, 2) if weights else None, missing, contraindications, hard_failures)


def _education_score(edu: Mapping[str, Any]) -> tuple[float, list[str], list[str], list[str]]:
    """Gap-audit fix (2026-08): added a `missing` return list (4th element,
    matching _academic_score's existing contract) so an entirely-absent
    `education_realism` section is distinguishable from one that was present
    and genuinely scored weak. Previously this function's `edu.get(key, 0.0)`
    calls silently treated "no education_realism data supplied at all" the
    same as "data supplied, availability/direct-job scores are actually
    0.0" -- both produced identical output with no signal that the input was
    absent. The SCORE FORMULA below is unchanged; this only adds visibility.
    """
    missing: list[str] = []
    # GAP FIX (2026-08-18, audit item B): retrofit of the "whole section
    # missing" note onto the shared scored_dimension() helper. Behavior is
    # byte-for-byte identical to before -- `_edu_missing` is the exact same
    # boolean `not edu` already computed below, and scored_dimension()'s
    # MISSING branch here only ever affects the `missing` list, never the
    # score formula (availability/ug/direct default to 0.0 either way,
    # matching edu.get(key, 0.0) below regardless of section presence).
    _edu_missing = not edu
    _, _edu_status = scored_dimension(edu, _edu_missing, missing_placeholder={})
    if _edu_status == "MISSING":
        missing.append("Education realism data not supplied")
    availability = float(edu.get("overall_availability_score", 0.0) or 0.0)
    ug = float(edu.get("ug_availability_score", 0.0) or 0.0)
    direct = float(edu.get("direct_job_after_ug_score", 0.0) or 0.0)
    score = 100.0 * (0.40 * availability + 0.25 * ug + 0.35 * direct)
    conditions, contra = [], []
    if edu.get("pg_required_for_good_outcome"):
        conditions.append("Plan a broad undergraduate foundation followed by PG specialization")
    if edu.get("professional_license_required"):
        conditions.append("Professional entrance/licensing requirements must be completed")
    if str(edu.get("credential_barrier", "")).lower() == "high":
        conditions.append("High credential or entrance barrier")
    if availability < 0.35:
        contra.append("Limited dependable education availability")
    if direct < 0.35:
        contra.append("Weak direct-employment pathway after undergraduate study")
    return round(max(0.0, min(100.0, score)), 2), conditions, contra, missing


def _career_score(market: Mapping[str, Any], risk: Mapping[str, Any], risk_appetite: str) -> tuple[float, list[str], list[str], list[str]]:
    """Gap-audit fix (2026-08): added a `missing` return list (4th element,
    matching _academic_score's existing contract) -- same rationale as
    _education_score above. `market`/`risk` being entirely absent previously
    fell back to this function's own "medium"/"Medium" defaults silently, so
    a field with genuinely no market/risk data looked identical to a field
    with real data assessed as medium. The SCORE FORMULA below is
    unchanged; this only adds visibility.
    """
    missing: list[str] = []
    # GAP FIX (2026-08-18, audit item B): same retrofit as _education_score
    # above -- purely a plumbing change through scored_dimension(), the
    # market/risk missing-checks and the score formula below are unchanged.
    _, _market_status = scored_dimension(market, not market, missing_placeholder={})
    if _market_status == "MISSING":
        missing.append("Market data not supplied")
    _, _risk_status = scored_dimension(risk, not risk, missing_placeholder={})
    if _risk_status == "MISSING":
        missing.append("Risk data not supplied")
    depth = {"deep": 90, "medium": 68, "niche": 42}.get(str(market.get("market_depth", "medium")).lower(), 60)
    fresh = {"high": 90, "medium": 68, "low-medium": 48, "low": 30}.get(str(market.get("freshers_market", "medium")).lower(), 60)
    demand = {"high": 90, "stable": 68, "medium": 60, "low": 35}.get(str(market.get("india_2035_demand", "stable")).lower(), 60)
    score = 0.40 * depth + 0.30 * fresh + 0.30 * demand
    conditions, contra = [], []
    risk_level = str(risk.get("risk_level", "Medium"))
    if risk_level in {"Medium-High", "High"}:
        conditions.append("Use internships, portfolio evidence and a broad backup route to manage market risk")
        if str(risk_appetite).upper() == "LOW":
            score -= 12
            contra.append("Career risk exceeds the supplied low risk appetite")
    if depth == 42:
        conditions.append("Niche market: retain an adjacent broad qualification")
    return round(max(0.0, min(100.0, score)), 2), conditions, contra, missing


def assess_field_suitability(
    row: Mapping[str, Any], *, top_score: float,
    academic_profile: Mapping[str, Any] | None = None,
    risk_appetite: str = "MODERATE",
) -> Dict[str, Any]:
    academic_profile = academic_profile or {}
    raw = float(row.get("final_score", 0.0) or 0.0)
    astro = round(max(0.0, min(100.0, 100.0 * raw / top_score)), 2) if top_score > 0 else 0.0
    curriculum, edu, market, risk = (_section(row, x) for x in ("curriculum", "education_realism", "market", "risk"))
    requirements = _requirements(row, curriculum)
    academic, missing, academic_contra, hard_failures = _academic_score(requirements, curriculum, academic_profile)
    education, education_conditions, education_contra, education_missing = _education_score(edu)
    career, career_conditions, career_contra, career_missing = _career_score(market, risk, risk_appetite)

    astrological_contra = []
    if row.get("is_afflicted") and astro < 45:
        astrological_contra.append("Structural astrological QA gate is adverse")
    if float(row.get("net_contraindication_index", 0.0) or 0.0) >= 0.60 and astro < 50:
        astrological_contra.append("Multiple astrological methods show material contraindications")

    academic_unknown = bool(missing)
    academic_not_applicable = not requirements["hard_eligibility"] and not requirements["core_aptitude"]
    if academic_unknown or academic_not_applicable:
        # Do not silently convert absent evidence into average aptitude.  The
        # point estimate uses only known dimensions and the interval shows the
        # full unresolved academic range (0..100 at 25% model weight).
        known_weight = 0.40 + 0.20 + 0.15
        known_total = 0.40 * astro + 0.20 * education + 0.15 * career
        overall = round(known_total / known_weight, 2)
        lower_overall = overall if academic_not_applicable else round(known_total, 2)
        upper_overall = overall if academic_not_applicable else round(known_total + 25.0, 2)
    else:
        overall = round(0.40 * astro + 0.25 * float(academic or 0.0) + 0.20 * education + 0.15 * career, 2)
        lower_overall = upper_overall = overall
    dimensions_adverse = sum(bool(x) for x in (astrological_contra, academic_contra, education_contra, career_contra))
    conditions = list(dict.fromkeys(education_conditions + career_conditions))
    contraindications = list(dict.fromkeys(astrological_contra + academic_contra + education_contra + career_contra))

    if hard_failures:
        status = STATUS_NOT_PRIMARY
    elif overall >= 80 and not conditions and dimensions_adverse == 0:
        status = STATUS_PRIMARY
    elif overall >= 65:
        status = STATUS_CONDITIONAL if conditions or missing else STATUS_PRIMARY
    elif overall >= 50:
        status = STATUS_PG if edu.get("pg_required_for_good_outcome") else STATUS_CONDITIONAL
    elif overall >= 35 or dimensions_adverse < 2:
        status = STATUS_EXPLORATORY
    else:
        status = STATUS_NOT_PRIMARY

    # A rejection requires independent adverse evidence in at least two
    # dimensions. Low rank alone can only make a field exploratory.
    if status == STATUS_NOT_PRIMARY and dimensions_adverse < 2 and not hard_failures:
        status = STATUS_EXPLORATORY

    def band(value: float) -> str:
        if value >= 80: return STATUS_PRIMARY
        if value >= 65: return STATUS_CONDITIONAL
        if value >= 50: return STATUS_PG if edu.get("pg_required_for_good_outcome") else STATUS_CONDITIONAL
        if value >= 35: return STATUS_EXPLORATORY
        return STATUS_NOT_PRIMARY if dimensions_adverse >= 2 else STATUS_EXPLORATORY

    status_range = list(dict.fromkeys((band(lower_overall), band(upper_overall))))
    if academic_unknown:
        status = STATUS_REQUIRES_VALIDATION
    if row.get("publication_eligibility") == "exploratory_only" and status != STATUS_NOT_PRIMARY:
        status = STATUS_EXPLORATORY

    return {
        "recommendation_status": status,
        "astrological_alignment": astro,
        "academic_fit": academic,
        "academic_evidence_status": "not_applicable" if academic_not_applicable else ("unknown" if academic_unknown else "supplied"),
        "education_feasibility": education,
        "career_viability": career,
        "overall_suitability": overall,
        "overall_suitability_interval": [lower_overall, upper_overall],
        "status_range": status_range,
        "decision_resolved": not academic_unknown and not hard_failures and row.get("publication_eligibility") != "exploratory_only",
        "requirement_contract": requirements,
        "hard_eligibility_failures": hard_failures,
        "conditions": conditions,
        "contraindications": contraindications,
        "missing_validations": missing,
        # Gap-audit fix (2026-08, additive/diagnostic-only): _education_score
        # and _career_score previously silently treated an entirely-absent
        # education_realism/market/risk section as if it had been supplied
        # and scored 0/neutral, unlike _academic_score's existing explicit
        # `missing_validations` contract above. These two lists surface that
        # same signal for education/career -- empty when data was present
        # (even if the resulting score is genuinely low), non-empty when the
        # underlying registry section was absent entirely. Deliberately NOT
        # wired into `recommendation_status`/`overall_suitability` above (that
        # would be a scoring/policy change, not a documentation fix) -- purely
        # additive transparency for report/debug consumers.
        "education_missing_data": education_missing,
        "career_missing_data": career_missing,
        "policy": "route-suitability.v3; explicit hard/core/optional requirements; hard failure is a single veto; unknown academics are null and unresolved",
        # gap fix 2026-08-18 (item 3): astrological_alignment above is
        # RELATIVE to this chart's own top final_score (100 x raw/top_score),
        # so the chart's own #1 field always scores 100 regardless of
        # whether the chart is strongly differentiated or nearly flat across
        # many fields. jyotish/ranking_policy.py's
        # annotate_rank_differentiation() already computes score_ceiling_tie
        # (this row sits within a near-tie band of the top score) and
        # low_rank_differentiation (the ranked list is generally flat) on
        # each row, and confirmed (by call-order inspection: engine.py calls
        # annotate_rank_differentiation() on `results` at the end of
        # run_engine(), before career_field_report_v2.py calls
        # annotate_field_suitability() on that same already-annotated
        # `results` list) to already be present on `row` by the time this
        # function runs. This is purely additive -- does not change `astro`,
        # `overall`, or `status` -- so a downstream report can add an honest
        # caveat next to a flat chart's #1 field instead of presenting it
        # with the same unqualified confidence as a strongly convergent
        # chart's #1 field.
        "differentiation_caveat": bool(
            row.get("score_ceiling_tie") or row.get("low_rank_differentiation")
        ),
    }


def annotate_field_suitability(
    rows: Iterable[Dict[str, Any]], *, academic_profile: Mapping[str, Any] | None = None,
    risk_appetite: str = "MODERATE",
) -> list[Dict[str, Any]]:
    rows = list(rows)
    top = max((float(r.get("final_score", 0.0) or 0.0) for r in rows), default=0.0)
    for row in rows:
        row["recommendation_assessment"] = assess_field_suitability(
            row, top_score=top, academic_profile=academic_profile, risk_appetite=risk_appetite,
        )
    # Policy change (2026-08-18, explicit direction from Dr. Sooriyan: "even
    # if [academic evidence] is unknown give the top astrological fields
    # alone... this application is for astrological evaluation"):
    #
    # Previously `resolved` required decision_resolved (which is False
    # whenever academic_unknown is True), so any field with real subject
    # requirements but no supplied academic_profile data -- e.g.
    # mechanical_engineering/chemical_engineering needing math/physics
    # aptitude nobody had entered for a given student -- was EXCLUDED from
    # headline candidacy entirely, regardless of astrological rank. Confirmed
    # live (Akash Shanmugham, 2026-08-18): commerce_accounting (raw
    # astrological rank #15) became "Best UG Route" while
    # mechanical_engineering/chemical_engineering (raw ranks #1/#2, tied top
    # final_score) sat excluded purely for missing data. Per explicit product
    # direction, this app's primary authority is the astrological
    # determination -- academic/practical data is a secondary, ADVISORY layer
    # (conditions/contraindications/caveats), not a gate that can silently
    # veto an astrologically-strong field's candidacy just because a subject
    # aptitude questionnaire hasn't been filled in yet.
    #
    # Only genuine, evidence-independent rejections still exclude a field:
    # STATUS_NOT_PRIMARY (real hard_eligibility_failures -- e.g. a student
    # with *confirmed low* biology aptitude for medicine, or material
    # astrological contraindications -- not merely "unknown") and
    # exploratory_only publication eligibility. academic_unknown no longer
    # excludes candidacy; it still fully drives recommendation_status/
    # conditions/contraindications/missing_validations for that field, so the
    # report can (and does, via best_ug_route_pending_stronger_candidates
    # below and the field's own `conditions` list) honestly flag "this pick's
    # academic fit isn't independently verified yet" without blocking it from
    # being the headline pick when the chart supports it most strongly.
    resolved = [
        r for r in rows
        if (r.get("recommendation_assessment") or {}).get("recommendation_status") != STATUS_NOT_PRIMARY
        and r.get("field_role", "educational_field") in {"educational_field", "specialization"}
    ]

    # Sort key: RAW ASTROLOGICAL SCORE (final_score) is now primary, per the
    # policy above -- deliberately NOT overall_suitability, which blends in
    # academic/education/career dimensions using a reduced-weight formula for
    # not_applicable/unknown fields that can itself inflate a data-light
    # field's apparent suitability (this was the ORIGINAL 2026-08-17
    # "Technology Consulting" bug's actual mechanism -- sorting by that
    # blended number as primary would risk reintroducing it in a new form).
    # Sorting by final_score sidesteps that inflation entirely: it's the same
    # astrological ranking already shown everywhere else in this report
    # (Top 20 table, `rank` field), so "top astrological fields" here means
    # exactly what it says. Evidence completeness (`_evidence_tier`) is kept
    # only as a LOW-PRIORITY tiebreaker for near-identical final_scores (e.g.
    # mechanical_engineering/chemical_engineering tied at 40.68 above), not a
    # gate or a primary key -- astrology decides the winner; evidence quality
    # only decides ties astrology itself left unresolved.
    def _evidence_tier(r: Dict[str, Any]) -> int:
        status = (r.get("recommendation_assessment") or {}).get("academic_evidence_status", "")
        return {"supplied": 0, "not_applicable": 1}.get(status, 2)

    resolved.sort(key=lambda r: (
        -float(r.get("final_score", 0.0) or 0.0),
        _evidence_tier(r),
        str(_field_id(r)),
    ))
    validated_rank = {_field_id(r): i for i, r in enumerate(resolved, 1)}
    for i, row in enumerate(rows, 1):
        row["astrological_potential_rank"] = i
        row["validated_recommendation_rank"] = validated_rank.get(_field_id(row))

    # Gap fix (2026-08-18, "still not fixed" follow-up to the Technology
    # Consulting fix above): that fix corrected the ORDER among already-
    # decision_resolved fields, but left a related failure mode untouched --
    # a field can only enter `resolved`/`validated` at all if decision_resolved
    # is True, and decision_resolved is False whenever academic_unknown is True
    # (real subject requirements exist for that field, e.g. math/physics for
    # engineering, but the student's academic_profile simply hasn't supplied
    # that evidence yet). A field with NO real requirements (like Commerce)
    # never has this problem -- academic_unknown can never be True for it --
    # so it clears decision_resolved "for free" and can win the headline slot
    # even when it ranks far below fields that are merely PENDING evidence,
    # not rejected. Confirmed live: mechanical_engineering/chemical_engineering
    # (raw ranks #1/#2, tied top final_score) excluded from `resolved` purely
    # on academic_unknown, while commerce_accounting (raw rank #15, ~21%
    # lower final_score) became best_ug_route with no caveat that stronger
    # candidates exist pending data -- the same "wins by having nothing to be
    # uncertain about" shape the 2026-08-17 fix already named, just via a
    # different gate (decision_resolved) instead of the evidence-tier sort.
    #
    # This does NOT change validated_recommendation_rank, `resolved`, or any
    # selection mechanics above -- deliberately, to avoid touching the
    # already-fixed Technology Consulting logic. It only adds a factual,
    # always-computable comparison: which academic_unknown (not hard-failed,
    # not exploratory-only) fields outrank the top validated pick on raw
    # final_score. Attached to every row (not just the winner) so any
    # downstream consumer -- not only the current UG-primary field -- can see
    # what's pending, and to the report layer so it can surface an honest
    # "pending stronger candidates" note instead of presenting a lower-ranked
    # validated pick with unqualified confidence.
    top_validated_score = float((resolved[0].get("final_score", 0.0) or 0.0)) if resolved else 0.0
    pending_stronger = sorted(
        (
            {
                "field_id": _field_id(r),
                "field_label": str(r.get("field_label") or r.get("label") or _field_id(r)),
                "astrological_potential_rank": r.get("astrological_potential_rank"),
                "final_score": float(r.get("final_score", 0.0) or 0.0),
            }
            for r in rows
            if (r.get("recommendation_assessment") or {}).get("academic_evidence_status") == "unknown"
            and not (r.get("recommendation_assessment") or {}).get("hard_eligibility_failures")
            and r.get("publication_eligibility") != "exploratory_only"
            and float(r.get("final_score", 0.0) or 0.0) > top_validated_score
        ),
        key=lambda x: -x["final_score"],
    )
    for row in rows:
        row["validated_pick_pending_stronger_candidates"] = pending_stronger
    return rows
