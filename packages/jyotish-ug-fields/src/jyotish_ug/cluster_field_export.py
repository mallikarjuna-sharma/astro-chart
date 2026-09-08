"""Field_Determination/cluster_field_export.py — Top-20-by-cluster + full
per-field registry/LLM-narrative export, for the CLI's Reference JSON output
(the 2nd of the 3 simplified debug JSON files -- see route_map.py for the
1st/Summary one).

Two-part shape, per the user's 2026-09 request:

  {
    "schema_version": "v12.0_enriched_registry",
    "legend": { ...boilerplate that was previously repeated verbatim on
                 EVERY field entry (route-type labels/explanations, the
                 modern-extensions caution) -- written ONCE here instead;
                 see _LEGEND below... },
    "clusters": [
      {"rank": 1, "cluster": "Engineering, Space & Physical Systems",
       "strength_pct": 100.0,
       "fields": [{"field_id": "...", "label": "...", "rank_in_top20": 1,
                    "final_score": 100.0}, ...]},
      ...
    ],
    "fields": {
      "<field_id>": { ...OPTIMIZED per-field record -- see
                       _optimize_field_entry() below for exactly what was
                       dropped/merged and why -- plus "llm_narrative":
                       <str or null, see _field_llm_narrative()>... },
      ...
    }
  }

"clusters" reuses the SAME grouping/ranking/strength-percentage logic the
HTML "Field scores by cluster" panel is built from
(jyotish/report_utils.py::top20_as_four_cluster_groups /
cluster_strength_weighted -- already used elsewhere in this checkout, e.g.
education_engine.py's own console cluster markdown), re-deriving the same
`strength_pct` formula career_field_report_v2.py's `_macro_cluster_ranking`
uses (100 * cluster's capped/floored/decayed vote total / the strongest
scored cluster's own total; the display-only 4th "Additional Top-20
Branches" bucket always shows 0%, matching the HTML panel's own "0%
strength").

Each field_id appears only ONCE under "fields" (course registry entries can
be large; a field that happened to be a member of more than one grouping
pass is not duplicated) -- "clusters" is what carries the per-cluster
membership/ranking, "fields" is the flat lookup table.

GAP-FIX (2026-09, "optimize the JSON, no repetitions, max info in fewer
fields" request): the raw v12 registry record this module used to emit
verbatim per field carried a LOT of duplication -- both WITHIN one field's
own record and, separately, boilerplate text repeated IDENTICALLY across
EVERY field in the export. _optimize_field_entry() below removes it;
see that function's own comments for the specific redundancies found and
what each was folded into. Nothing informative was dropped -- only text
that was either a second copy of a value already present elsewhere on the
same record, or a static template string that carried zero field-specific
information.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from Field_Determination.jyotish.report_utils import (
    top20_as_four_cluster_groups,
    cluster_strength_weighted,
    field_display_name,
)
from Field_Determination.jyotish.engine_io import _load_course_registry
from Field_Determination.route_map import _row_field_id


# Static, field-independent boilerplate that used to be repeated verbatim
# inside EVERY field's "routes"/"modern_extensions" block (confirmed by
# diffing several real field entries -- the route-type labels and "why"
# explanations, and the modern-extensions caution sentence, never varied by
# field). Written ONCE at the top of the export instead of N times.
_LEGEND: Dict[str, Any] = {
    "route_types": {
        "ambitious": "High-end specialized route: the field's own most advanced UG/PG/PhD track.",
        "safe": "Parent-safe practical route — keeps options broad while preserving alignment with this field.",
        "backup": "Backup / adjacent route — useful if entrance rank, interest, or market conditions make the direct route less practical.",
    },
    "modern_extensions_caution": (
        "Modern extensions are not guaranteed UG outcomes; they usually require electives, "
        "projects, internships or PG/upskilling."
    ),
}


# Per-field LLM narrative text, if any actually landed on this row. The
# current LLM pipeline (jyotish/llm.py::call_llm_for_fields) can now write a
# genuine per-field narrative (see its "field_narratives" schema addition)
# under "astrological_reason" (astrologer audience) or
# "parent_friendly_explanation" (parent audience) -- checked first since
# they're the more specific signal when present. Only falls back to the
# chart-level one-page summary (payload.llm_astrological_summary) when the
# LLM step didn't run at all for this field (no consent, no --llm, no API
# key) -- see education_engine.py's own note on this fallback.
_PER_FIELD_NARRATIVE_KEYS = (
    "astrological_reason", "llm_astrological_reason", "parent_friendly_explanation",
)


def _field_llm_narrative(row: Dict[str, Any], payload: Any = None) -> Optional[str]:
    for key in _PER_FIELD_NARRATIVE_KEYS:
        val = row.get(key)
        if val:
            return str(val)
    if payload is not None:
        chart_level = getattr(payload, "llm_astrological_summary", None)
        if chart_level:
            return chart_level
    return None


def _optimize_field_entry(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Return a de-duplicated, information-dense view of one v12 registry
    record. Redundancies removed (each confirmed by diffing real records,
    not assumed):

    - "classic_core" is a byte-for-byte copy of the top-level field/track/
      specialization/description/niche keys -- dropped; the top-level keys
      stay as the single source of truth.
    - "career_signature" (a flat list) is exactly the union of
      career_outcomes.core + career_outcomes.aspirational, just without the
      bucketing -- dropped in favor of the more informative bucketed
      career_outcomes.
    - "admission_exams" (human-cased) and "admission_exams_canonical"
      (upper-cased) are the same list twice, and routes.ambitious_route.
      entrance_exams was a THIRD copy of the canonical list again -- kept
      once as "admission_exams" (canonical/upper-cased, since that's the
      form used for matching elsewhere in this codebase), dropped from
      routes entirely.
    - "available_at" (raw) is a strict subset of "available_at_normalized"
      (same campus lists, minus the score/confidence/notes normalization) --
      dropped the raw copy. available_at_normalized itself is then trimmed:
      institutions with available=false (the majority, on most fields --
      score 0.0, confidence "none", empty campuses/notes) carry zero
      information and are dropped outright rather than emitted as an empty
      shell; kept institutions drop the now-constant "available": true flag,
      the "raw_v11_value" field (identical to "campuses" when campuses is a
      list; when the source was a bare boolean, availability_score already
      encodes that), and "notes" when blank.
    - "tier_map"'s UG/PG/PhD "spec" strings duplicate routes.ambitious_route
      (ug/pg/phd_or_research) and the top-level label/specialization --
      dropped, keeping only each level's "niche" (which does carry
      level-specific information not present elsewhere) under a renamed
      "tiers" key.
    - "routes.*.label" and "routes.*.why" were IDENTICAL boilerplate across
      every field in the whole export (not just within one record) -- moved
      once to the module-level _LEGEND["route_types"] instead of repeating
      per field; each route here keeps only its actual field-specific
      value(s).
    - "risk.risk_level" / "risk.parent_safe_route" duplicate the same two
      keys already on "education_realism" -- dropped; risk's only unique
      content (avoid_primary_when) is folded into education_realism.
    - "market.credential_barrier" duplicates "education_realism.
      credential_barrier" -- dropped from market.
    - "ontology.ontology_policy" is static schema documentation (identical
      across every field in the registry, describing what the OTHER
      ontology keys mean) -- dropped; "secondary_families"/"broadness_score"
      are dropped only when they're empty/zero (i.e. carry no signal for
      this particular field).
    - "modern_extensions.description"/"caution" are template-generated text
      (caution is byte-identical across every field; description is just
      the field's own label + extensions list restated in a sentence) --
      dropped in favor of the plain "extensions" list plus the one shared
      caution in _LEGEND.
    - "schema_version" was repeated on every single field -- moved to the
      export's top level (see build_cluster_field_export()).
    """
    def _clean(d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return {k: v for k, v in (d or {}).items() if v not in (None, "", [], {})}

    # -- available_at: normalized, filtered to institutions actually available --
    normalized = meta.get("available_at_normalized") or {}
    available_at: Dict[str, Any] = {}
    for inst, info in normalized.items():
        if not isinstance(info, dict) or not info.get("available"):
            continue
        entry: Dict[str, Any] = {}
        if info.get("campuses"):
            entry["campuses"] = info["campuses"]
        if info.get("availability_score") is not None:
            entry["availability_score"] = info["availability_score"]
        if info.get("confidence") and info["confidence"] != "none":
            entry["confidence"] = info["confidence"]
        if info.get("notes"):
            entry["notes"] = info["notes"]
        available_at[inst] = entry

    # -- tiers: only the level-specific niche (spec duplicates routes/label) --
    tier_map = meta.get("tier_map") or {}
    tiers = {
        level: t.get("niche")
        for level, t in tier_map.items()
        if isinstance(t, dict) and t.get("niche")
    }

    # -- routes: field-specific values only; labels/why live in _LEGEND once --
    routes = meta.get("routes") or {}
    ambitious = routes.get("ambitious_route") or {}
    safe = routes.get("safe_route") or {}
    backup = routes.get("backup_route") or {}
    routes_out = _clean({
        "ambitious": _clean({
            "ug": ambitious.get("ug"),
            "pg": ambitious.get("pg"),
            "phd": ambitious.get("phd_or_research"),
        }),
        "safe_path": safe.get("path"),
        "backup_path": backup.get("path"),
    })

    # -- education_realism: absorb risk's unique content, drop risk's dupes --
    education_realism = dict(meta.get("education_realism") or {})
    risk = meta.get("risk") or {}
    if risk.get("avoid_primary_when"):
        education_realism["avoid_primary_when"] = risk["avoid_primary_when"]

    # -- market: drop the credential_barrier duplicate --
    market = dict(meta.get("market") or {})
    market.pop("credential_barrier", None)

    # -- ontology: drop the static ontology_policy + empty/zero fields --
    ontology = _clean({k: v for k, v in (meta.get("ontology") or {}).items() if k != "ontology_policy"})

    # -- modern_extensions: just the list; caution/description are boilerplate --
    modern_extensions = (meta.get("modern_extensions") or {}).get("extensions") or []

    # -- admission_exams: canonical form once, not three times --
    admission_exams = meta.get("admission_exams_canonical") or meta.get("admission_exams") or []

    return _clean({
        "label": meta.get("label"),
        "domain": meta.get("domain"),
        "field": meta.get("field"),
        "track": meta.get("track"),
        "specialization": meta.get("specialization"),
        "niche": meta.get("niche"),
        "description": meta.get("description"),
        "degree_types": meta.get("degree_types"),
        "duration_years": meta.get("duration_years"),
        "admission_exams": admission_exams,
        "available_at": available_at,
        "tiers": tiers,
        "modern_extensions": modern_extensions,
        "ontology": ontology,
        "education_realism": education_realism,
        "curriculum": meta.get("curriculum"),
        "market": market,
        "routes": routes_out,
        "career_outcomes": meta.get("career_outcomes"),
    })


def build_cluster_field_export(results: List[Dict[str, Any]], payload: Any = None) -> Dict[str, Any]:
    top20 = list(results[:20])
    groups = top20_as_four_cluster_groups(top20)
    if not groups:
        return {"schema_version": "v12.0_enriched_registry", "legend": _LEGEND, "clusters": [], "fields": {}}

    top_score = float(top20[0].get("final_score", 0.0) or 0.0) if top20 else 0.0

    raw_groups = []
    for cluster, rows in groups:
        raw_groups.append({
            "cluster": cluster,
            "rows": rows,
            "raw_strength": cluster_strength_weighted(rows, top_score),
        })
    scored_groups = [g for g in raw_groups if g["cluster"] != "Additional Top-20 Branches"]
    max_strength = max((g["raw_strength"] for g in scored_groups), default=1.0) or 1.0

    registry_v12 = _load_course_registry()

    clusters_out: List[Dict[str, Any]] = []
    fields_out: Dict[str, Any] = {}
    _rank_counter = 0

    for g in raw_groups:
        display_only = g["cluster"] == "Additional Top-20 Branches"
        if not display_only:
            _rank_counter += 1

        field_entries = []
        for rank, row in g["rows"]:
            fid = _row_field_id(row)
            field_entries.append({
                "field_id": fid,
                "label": field_display_name(row),
                "rank_in_top20": rank,
                "final_score": round(float(row.get("final_score", 0.0) or 0.0), 2),
            })
            if fid and fid not in fields_out:
                entry = _optimize_field_entry(registry_v12.get(fid, {}) or {})
                entry["llm_narrative"] = _field_llm_narrative(row, payload)
                # ROOT-CAUSE FIX (2026-09): registry_v12 entries carry no
                # scoring info at all -- final_score/rank_in_top20/domain
                # live only on `row` (the actual per-run results object),
                # which was previously only copied into the per-cluster
                # `field_entries` list above, never into fields_out[fid].
                # Every consumer of cluster_field_export["fields"][fid]
                # (e.g. output.py's export_html_simple_summary()) was
                # therefore reading a key that simply did not exist and
                # silently getting None back. Stamp the real score here so
                # ALL callers of build_cluster_field_export() get it, not
                # just the HTML report.
                entry["final_score"] = round(float(row.get("final_score", 0.0) or 0.0), 2)
                entry["rank_in_top20"] = rank
                entry.setdefault("label", field_display_name(row))
                entry.setdefault("domain", row.get("domain"))
                fields_out[fid] = entry

        clusters_out.append({
            "rank": None if display_only else _rank_counter,
            "cluster": g["cluster"],
            "strength_pct": 0.0 if display_only else round(100.0 * g["raw_strength"] / max_strength, 1),
            "fields": field_entries,
        })

    return {
        "schema_version": "v12.0_enriched_registry",
        "legend": _LEGEND,
        "clusters": clusters_out,
        "fields": fields_out,
    }
