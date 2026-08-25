"""JyotishAI — ExplainabilityEngine and HTML report generators."""
import html, json, os
from typing import Dict, List, Tuple, Set, Any, Optional
from datetime import date, datetime

from .payload import ENGINE_VERSION, logger

# ─── Module-level constants used by ExplainabilityEngine ─────────────────────

_ROLE_LABEL_PARENT: Dict[str, str] = {
    "ak":  "your child's soul-karaka (deepest drive)",
    "amk": "the career-karaka (daily work planet)",
    "h10": "the lord of the career house",
    "h9":  "the lord of the higher-education house",
}

_ROLE_LABEL_ASTRO: Dict[str, str] = {
    "ak":  "AK",
    "amk": "AmK",
    "h10": "H10L",
    "h9":  "H9L",
}

# Bug fix (2026-08-20): these two dicts only covered 4 of the 10 canonical
# dignity_state values dignity.py::compute_dignity() can actually return
# (see dignity.py line ~46: DEBILITATED, NEECHA_BHANGA, GREAT_ENEMY, ENEMY,
# NEUTRAL, FRIEND, GREAT_FRIEND, OWN_SIGN, MOOLATRIKONA, EXALTED) -- plus a
# straight naming mismatch ("OWN" here vs. the real "OWN_SIGN" state), so a
# planet whose top-affinity dignity was OWN_SIGN, MOOLATRIKONA, NEUTRAL,
# FRIEND, GREAT_FRIEND, ENEMY, or GREAT_ENEMY crashed
# _parent_explanation()'s direct dict index (KeyError) and took down the
# entire full-trace HTML export for that report. Filled out to full
# coverage; the lookups below were also changed from `_DICT[key]` to
# `_DICT.get(key, ...)` as defense-in-depth so an unrecognized future
# dignity_state degrades to a generic phrase instead of crashing the report.
_DIGNITY_PARENT: Dict[str, str] = {
    "EXALTED":       "this planet is at peak strength (exalted)",
    "MOOLATRIKONA":  "this planet is in its Moolatrikona sign, giving it strong, near-own-sign footing",
    "OWN_SIGN":      "this planet is in its own sign, giving it natural strength",
    "GREAT_FRIEND":  "this planet sits in a sign owned by a great friend, giving it comfortable support",
    "FRIEND":        "this planet sits in a friendly sign, giving it steady support",
    "NEUTRAL":       "this planet sits in a neutral sign, neither helped nor hindered by sign placement",
    "ENEMY":         "this planet sits in an unfriendly sign, adding some friction to its results",
    "GREAT_ENEMY":   "this planet sits in a sign owned by a strong adversary, adding real friction to its results",
    "DEBILITATED":   "this planet faces challenges but can still contribute",
    "NEECHA_BHANGA": "a cancellation of debility makes this planet resilient",
}

_DIGNITY_ASTRO: Dict[str, str] = {
    "EXALTED":       "uccha (exalted)",
    "MOOLATRIKONA":  "moolatrikona",
    "OWN_SIGN":      "swa (own sign)",
    "GREAT_FRIEND":  "adhi mitra (great friend's sign)",
    "FRIEND":        "mitra (friend's sign)",
    "NEUTRAL":       "sama (neutral sign)",
    "ENEMY":         "shatru (enemy's sign)",
    "GREAT_ENEMY":   "adhi shatru (great enemy's sign)",
    "DEBILITATED":   "neecha (debilitated)",
    "NEECHA_BHANGA": "neecha bhanga (debility cancelled)",
}

_PLANET_TRAIT_PARENT: Dict[str, str] = {
    "Sun":     "leadership and administration",
    "Moon":    "nurturing and public service",
    "Mars":    "technical skill and drive",
    "Mercury": "analytical and communication ability",
    "Jupiter": "wisdom and advisory capacity",
    "Venus":   "creativity and aesthetic sense",
    "Saturn":  "discipline and structural thinking",
    "Rahu":    "innovation and technology",
    "Ketu":    "research and specialization",
}

# ─────────────────────────────────────────────────────────────────────────────

class ExplainabilityEngine:
    @staticmethod
    def _llm_parent_text(rec):
        return (rec.get("llm_parent_summary", "")
                or rec.get("parent_reason", "")
                or rec.get("llm_parent_reason", "")).strip()

    @staticmethod
    def _llm_astro_text(rec):
        return (rec.get("astrological_reason", "")
                or rec.get("llm_astrological_reason", "")
                or rec.get("llm_narrative", "")).strip()

    @staticmethod
    def _llm_payload(rec):
        return rec.get("llm_payload", {}) or {}

    @staticmethod
    def _method_norm(rec, key):
        return float((rec.get("method_normalized_scores", {}) or {}).get(key, 0.0))

    @staticmethod
    def _planet_roles(planet, payload):
        roles = []
        ak, amk = getattr(payload, "atmakaraka", ""), getattr(payload, "amatyakaraka", "")
        hl = getattr(payload, "house_lords", {})
        if planet == amk: roles.append("amk")
        if planet == ak: roles.append("ak")
        if hl.get("10") == planet: roles.append("h10")
        if hl.get("9")  == planet: roles.append("h9")
        return roles

    @staticmethod
    def _top_gap_drivers(gap_detail, n=4):
        return sorted([(k, v) for k, v in gap_detail.items() if v > 0.005], key=lambda x: -x[1])[:n]

    @staticmethod
    def _top_gap_penalties(gap_detail):
        return [(k, v) for k, v in gap_detail.items() if v < -0.005]

    @staticmethod
    def _top_planets(rec, n=3):
        planets = rec.get("top_affinity_planets") or rec.get("affinity_planets") or {}
        if isinstance(planets, dict):
            return sorted(planets.items(), key=lambda x: -x[1])[:n]
        return []

    @classmethod
    def _parent_explanation(cls, rank, rec, payload, active_lord, peak_lord):
        name = getattr(payload, "name", "Your child")
        label = rec["field_label"]
        top_ps = cls._top_planets(rec, 3)
        digs = getattr(payload, "planet_dignities", {})
        lines = [f"{label} is {name}'s {'top' if rank==1 else f'#{rank}'} career recommendation."]

        if top_ps:
            p1, w1 = top_ps[0]
            dig1 = digs.get(p1, "")
            roles1 = cls._planet_roles(p1, payload)
            role_str = f", who is also {_ROLE_LABEL_PARENT[roles1[0]]}" if roles1 else ""
            dig_str = f" -- {_DIGNITY_PARENT.get(dig1, 'this sign placement shapes its results')}" if dig1 else ""
            lines.append(f"{p1}{role_str} is the strongest planet for this field ({_PLANET_TRAIT_PARENT.get(p1,'broad capability')}){dig_str}.")

        # Append LLM-generated astrological reasoning when present
        # Key may be "astrological_reason" (from engine merge) or "llm_astrological_reason" (legacy)
        llm_reason = cls._llm_astro_text(rec)
        if llm_reason:
            lines.append(f"Astrological basis: {llm_reason}")

        llm_parent = cls._llm_parent_text(rec)
        if llm_parent:
            lines.append(f"Parent explanation: {llm_parent}")

        return " ".join(lines)

    @classmethod
    def _astrologer_explanation(cls, rank, rec, payload, active_lord, peak_lord):
        label = rec["field_label"]
        top_ps = cls._top_planets(rec, 3)
        digs = getattr(payload, "planet_dignities", {})
        lines = [f"{label} | Rank #{rank} | Score {rec['final_score']:.2f}"]

        for p, w in top_ps:
            dig = digs.get(p, "")
            roles = cls._planet_roles(p, payload)
            role_str = f" [{'; '.join(_ROLE_LABEL_ASTRO[r] for r in roles)}]" if roles else ""
            dig_str = f", {_DIGNITY_ASTRO.get(dig, 'neutral sign')}" if dig else ", neutral sign"
            lines.append(f"  {p}{role_str} {dig_str}: affinity {w:.2f}")

        # LLM-generated per-field astrological reasoning
        llm_reason = cls._llm_astro_text(rec)
        if llm_reason:
            lines.append(f"  [LLM] {llm_reason}")

        llm_parent = cls._llm_parent_text(rec)
        if llm_parent:
            lines.append(f"  [PARENT] {llm_parent}")

        return "\n".join(lines)

    @classmethod
    def generate(cls, rankings, payload, active_lord, peak_lord, top_n=15):
        # Top-level LLM rationale comes from the first ranked result (same value on all)
        selection_rationale = rankings[0].get("llm_selection_rationale", "") if rankings else ""
        output = []
        for rank, rec in enumerate(rankings[:top_n], 1):
            method_breakdown = rec.get("method_breakdown", {}) or {}
            output.append({
                "rank":                       rank,
                "field_id":                   rec.get("field_id", ""),
                "field":                      rec["field_label"],
                "domain":                     rec["domain"],
                "final_score":                round(rec["final_score"], 2),
                "composite_score":            round(float(rec.get("composite_score", 0.0)), 2),
                "affinity_score":             round(float(rec.get("affinity_score", 0.0)), 2),
                "blended_score":              round(float(rec.get("blended_score", 0.0)), 2),
                "knrao_score":                round(float(rec.get("knrao_score", method_breakdown.get("knrao", {}).get("score", 0.0))), 2),
                "kp_score":                   round(float(rec.get("kp_score", method_breakdown.get("kp", {}).get("score", 0.0))), 2),
                "jaimini_score":              round(float(rec.get("jaimini_score", method_breakdown.get("jaimini", {}).get("score", 0.0))), 2),
                "parashara_score":            round(float(rec.get("parashara_score", method_breakdown.get("parashara", {}).get("score", 0.0))), 2),
                "dashamsha_score":            round(float(rec.get("dashamsha_score", method_breakdown.get("dashamsha", {}).get("score", 0.0))), 2),
                "sudarshana_score":           round(float(rec.get("sudarshana_score", method_breakdown.get("sudarshana", {}).get("score", 0.0))), 2),
                "method_total_score":         round(float(rec.get("method_total_score", method_breakdown.get("weighted_total", 0.0))), 2),
                "weighted_method_score":      round(float(rec.get("weighted_method_score", rec.get("combined_score", method_breakdown.get("weighted_total", 0.0)))), 2),
                "knrao_normalized_score":     round(cls._method_norm(rec, "knrao"), 2),
                "kp_normalized_score":        round(cls._method_norm(rec, "kp"), 2),
                "jaimini_normalized_score":   round(cls._method_norm(rec, "jaimini"), 2),
                "parashara_normalized_score": round(cls._method_norm(rec, "parashara"), 2),
                "dashamsha_normalized_score": round(cls._method_norm(rec, "dashamsha"), 2),
                "sudarshana_normalized_score": round(cls._method_norm(rec, "sudarshana"), 2),
                "method_breakdown":           method_breakdown,
                "llm_rank":                   rec.get("llm_rank"),
                "llm_padded":                 rec.get("llm_padded", False),
                "engine_rank":                rec.get("engine_rank", rec.get("rank", rank)),
                "hard_lockout":               rec.get("hard_lockout", False),
                "selection_rationale":        selection_rationale,
                "astrological_reason":        cls._llm_astro_text(rec),
                "parent_friendly_explanation": rec.get("parent_friendly_explanation", ""),
                "parent":                     cls._parent_explanation(rank, rec, payload, active_lord, peak_lord),
                "astrologer":                 cls._astrologer_explanation(rank, rec, payload, active_lord, peak_lord),
                "llm_parent_summary":         cls._llm_parent_text(rec),
                "llm_selection_rationale":    selection_rationale,
                "llm_payload":                cls._llm_payload(rec),
            })
        return output


    @classmethod
    def export(cls, explanations, student_name, output_dir="educational_records"):
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp = os.path.join(
            output_dir,
            f"{student_name.lower().replace(' ','_')}_explanations_{ts}.json"
        )
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"explanations": explanations}, f, indent=4, ensure_ascii=False)
        logger.info(f"Explanations exported --> {fp}")
        return fp


    # ─────────────────────────────────────────────────────────────────────────
    # TRACE / DEBUG METHODS
    # ─────────────────────────────────────────────────────────────────────────

    _GAP_BOOST_LABELS: Dict[str, str] = {
        "ak_amk":               "AK/AmK affinity",
        "kp_h10_sig":           "KP H10 Significator",
        "stellium":             "House Stellium bonus",
        "h10_sublord":          "KP H10 Sub-lord",
        "dasha":                "Active Dasha keyword match",
        "karakamsha":           "Karakamsha sign-lord alignment",
        "d24_ak":               "D24 AK delta",
        "lagna_lord":           "Lagna lord keyword match",
        "risk_appetite":        "Risk-appetite alignment",
        "yogakaraka":           "Yogakaraka planet bonus",
        "h10_lord_str":         "H10 lord strength bonus",
        "ul_lord":              "Upapada Lagna lord",
        "kp_edu_star":          "KP edu cusp star-lord",
        "d9_ak":                "D9 AK delta",
        "yoga":                 "Detected yoga match",
        "h5_lord":              "H5 intelligence-lord",
        "amk_house":            "AmK house keyword",
        "ak_house":             "AK house keyword",
        "dasha_affinity_boost": "Active dasha affinity boost",
        "peak_md_boost":        "Peak MD alignment",
        "prd_boost":            "Pratyantar dasha bonus",
        "karakamsha_occ":       "Karakamsha occupant",
        "d9_h10":               "D9 H10 occupancy",
        "dharma_karma":         "Dharma-Karma yoga",
        "interest_pref":        "Student preference match",
        "brahma_lord":          "Brahma lord (Jaimini)",
        "d10_h10":              "D10 H10 occupancy",
        "gender_field":         "Gender-aware modifier",
        "aspect_h10":           "H10 Drishti bonus",
        "maheshwara":           "Maheshwara lord (Jaimini)",
        "bhavesha_phala":       "Bhavesha Phala (Edu Lord Placement)", # NEW TRACE LABEL
        "ak_combustion_penalty":"AK combustion penalty",
        "dusthana_penalty":     "Dusthana lord penalty",
        "d10_dusthana_penalty": "D10 dusthana penalty",
    }

    @classmethod
    def _planet_trace_html(cls, planet_trace: Dict) -> str:
        """Render per-planet effective-strength calculation as an HTML table."""
        esc = lambda t: str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        rows = ""
        for p, t in planet_trace.items():
            eff = t["eff_strength"]
            eff_cls = "tr-strong" if eff >= 1.5 else ("tr-weak" if eff < 0.8 else "tr-mid")
            retro_flag = " ⟲" if t["is_retro"] else ""
            nb_flag    = " NB" if t["in_nb"] else ""
            caz_flag   = " ☀" if t["cazimi"] else ""
            comb_flag  = " 🔥" if t["combust"] else ""
            varg_flag  = " V°" if t["vargottama"] else ""
            flags = f"{retro_flag}{nb_flag}{caz_flag}{comb_flag}{varg_flag}".strip()
            rows += (
                f"<tr class='{eff_cls}'>"
                f"<td class='pt-planet'>{esc(p)}</td>"
                f"<td class='pt-val'>{esc(t['sign'])} H{t['house']}</td>"
                f"<td class='pt-val'>{t['raw_shadbala']:.1f}/{t['min_v']:.0f}</td>"
                f"<td class='pt-ratio'>{t['raw_ratio']:.3f}</td>"
                f"<td class='pt-dig'>{esc(t['dignity'])}{esc(nb_flag)}</td>"
                f"<td class='pt-mod'>×{t['dig_mod']:.2f}<br><small>{esc(t['dig_note'])}</small></td>"
                f"<td class='pt-mod'>×{t['war_mod']:.2f}<br><small>{esc(t['war_status'])}</small></td>"
                f"<td class='pt-mod'>×{t['var_mod']:.2f}{esc(varg_flag)}</td>"
                f"<td class='pt-mod'>×{t['nak_mod']:.3f}<br><small>{esc(t['nakshatra'][:8])}</small></td>"
                f"<td class='pt-mod'>×{t['paksha_bala']:.3f}</td>"
                f"<td class='pt-mod'>×{t['func_mod']:.3f}</td>"
                f"<td class='pt-mod'>×{t['digbala_mod']:.2f}<br><small>H{t['digbala_house']}</small></td>"
                f"<td class='pt-mod'>×{t['caz_mod']:.2f}{esc(caz_flag)}</td>"
                f"<td class='pt-mod'>×{t['comb_mod']:.2f}<br><small>{esc(t['comb_note'])}</small></td>"
                f"<td class='pt-eff'>{eff:.4f}</td>"
                f"</tr>"
            )
        return f"""
        <table class='planet-table'>
          <thead><tr>
            <th>Planet</th><th>Sign/House</th><th>Shad/Min</th><th>Raw Ratio</th>
            <th>Dignity</th><th>Dig×Mod</th><th>War×Mod</th><th>Var×Mod</th>
            <th>Nak×Mod</th><th>PB×Mod</th><th>Func×Mod</th><th>DigBala×</th>
            <th>Caz×</th><th>Comb×</th><th class='eff-hdr'>Eff Strength</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>"""

    @classmethod
    def _norm_chain_html(cls, ct: Dict) -> str:
        """Render the full score computation chain as step-by-step HTML.

        Uses the directly-logged chain values (Gap-B fix) instead of recomputing
        intermediate products.  Falls back gracefully for older records that lack
        the new BVB / threshold / mismatch / friction / ak_flat steps.
        """
        n  = ct.get("normalization", {})
        fc = ct.get("final_chain", {})

        # ── helper ────────────────────────────────────────────────────────────
        def _v(key, fallback=0.0):
            return fc.get(key, fallback)

        # ── threshold / mismatch / qa note strings (keys removed in Gap-B fix) ──
        thresh_note   = ("×0.70 — field below aptitude threshold"
                         if _v("threshold_mult") < 1 else "threshold met ✓")
        mismatch_note = ("×0.85 — domain–chart mismatch flagged"
                         if _v("mismatch_mult") < 1 else "no mismatch ✓")
        qa_note       = ("×0.70 — QA gate failed"
                         if _v("qa_gate_mult") < 1 else "QA gate passed ✓")

        # ── build rows using logged values ────────────────────────────────────
        rows = [
            ("Composite Score (raw)",      f"{n.get('composite_score_raw', 0):.4f}",
             "domain aptitude: shadbala + SAV + eff_strength blend"),
            ("Composite Score (norm)",     f"{n.get('composite_norm', 0):.4f}",
             "log-norm (soft-cap 200, max ~115)"),
            ("Affinity Score (raw)",       f"{n.get('affinity_score_raw', 0):.4f}",
             "Σ(planet_weight × eff_strength) × 100"),
            ("Affinity Score (norm)",      f"{n.get('affinity_norm', 0):.4f}",
             "log-norm (soft-cap 180, max ~115)"),
            ("Blended Score",              f"{n.get('blended', _v('blended')):.4f}",
             f"{n.get('domain_blend_weight','?')}×composite_norm + "
             f"{n.get('affinity_blend_weight','?')}×affinity_norm"),
            ("After Gap Boost",            f"{_v('after_boost'):.4f}",
             f"×(1 + {ct.get('gap_boost_total', 0):.4f}) gap_boost"),
            ("After Gap Penalty",          f"{_v('after_penalty'):.4f}",
             f"×(1 − {abs(ct.get('gap_penalty_total', 0)):.4f}) gap_penalty"),
            # Gap-B fix: BVB astro_multiplier step (was invisible before)
            ("After BVB Multiplier",       f"{_v('after_bvb_multiplier', _v('after_penalty')):.4f}",
             f"×{_v('bvb_multiplier', 1):.4f} (BVB astro_mult) "
             f"+ {_v('bvb_combined_addend', 0):.4f} (combined_score addend)"),
            ("After Threshold Gate",       f"{_v('after_threshold', _v('after_bvb_multiplier')):.4f}",
             f"×{_v('threshold_mult', 1):.2f} — {thresh_note}"),
            ("After Mismatch Gate",        f"{_v('after_mismatch', _v('after_threshold')):.4f}",
             f"×{_v('mismatch_mult', 1):.2f} — {mismatch_note}"),
            ("After Friction/QA-Friction", f"{_v('after_friction', _v('after_mismatch')):.4f}",
             f"×{_v('friction_mult', 1):.4f} | {str(fc.get('friction_note',''))[:60]}"),
            ("After QA Gate",              f"{_v('after_qa', _v('after_friction')):.4f}",
             f"×{_v('qa_gate_mult', 1):.2f} — {qa_note}"),
            # Gap-B fix: ak_domain_flat addition (was invisible before)
            ("+ AK Domain Flat",           f"{_v('after_ak_flat', _v('after_qa')):.4f}",
             f"+{_v('ak_domain_flat', 0):.4f} soul-domain supplement (added after all multipliers)"),
            ("Pre-Norm Score",             f"{_v('final_score'):.4f}",
             "engine chain total (before cross-batch 20–100 normalization)"),
        ]

        trs = ""
        for step, val, note in rows:
            is_final = step in ("Pre-Norm Score",)
            bold = " style='font-weight:700;background:#eef2ff'" if is_final else ""
            trs += (f"<tr{bold}><td class='chain-step'>{step}</td>"
                    f"<td class='chain-val'>{val}</td>"
                    f"<td class='chain-note-td'>{note}</td></tr>")
        return (f"<table class='chain-table'>"
                f"<thead><tr><th>Step</th><th>Value</th><th>Note</th></tr></thead>"
                f"<tbody>{trs}</tbody></table>")

    @classmethod
    def _gap_table_html(cls, boosts: Dict, penalties: Dict) -> str:
        """Render gap boost + penalty details as an HTML table."""
        rows = ""
        all_items = sorted(boosts.items(), key=lambda x: -x[1]) + sorted(penalties.items(), key=lambda x: x[1])
        for k, v in all_items:
            if abs(v) < 0.001: continue
            label = cls._GAP_BOOST_LABELS.get(k, k)
            pct   = f"{v*100:+.1f}%"
            cls2  = "gap-pos" if v > 0 else "gap-neg"
            rows += f"<tr><td class='gap-key'>{k}</td><td class='gap-label'>{label}</td><td class='{cls2}'>{pct}</td></tr>"
        if not rows:
            return "<p style='color:#888;font-size:0.85rem'>No gap adjustments fired.</p>"
        return f"<table class='gap-table'><thead><tr><th>Key</th><th>Factor</th><th>Δ</th></tr></thead><tbody>{rows}</tbody></table>"

    @classmethod
    def _affinity_table_html(cls, weights: Dict, contribs: Dict, eff_map: Dict) -> str:
        """Render planet affinity weights × eff_strength = contribution."""
        rows = ""
        for p, w in sorted(weights.items(), key=lambda x: -x[1]):
            if w < 0.005: continue
            eff = eff_map.get(p, {}).get("eff_strength", 0.0)
            contrib = contribs.get(p, 0.0)
            rows += (f"<tr><td class='aff-planet'>{p}</td>"
                     f"<td class='aff-val'>{w:.4f}</td>"
                     f"<td class='aff-val'>{eff:.4f}</td>"
                     f"<td class='aff-contrib'>{contrib:.4f}</td></tr>")
        return (f"<table class='aff-table'>"
                f"<thead><tr><th>Planet</th><th>Weight</th><th>Eff Strength</th><th>Contribution</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>")

    @classmethod
    def _field_trace_html_block(cls, rank: int, rec: Dict, esc) -> str:
        """Phase-2 trace block for one field.
        Planet effective strengths (Phase 1) are shown once at the top of the page,
        not repeated here.  Each block shows only the branch-specific work:
        affinity weighting, normalization, gap adjustments, final chain.
        """
        ct    = rec.get("calc_trace", {})
        pt    = ct.get("planet_trace", {})
        label = esc(rec["field_label"])
        score = rec["final_score"]
        src   = rec.get("affinity_source", "?")
        boosts  = ct.get("gap_boosts", {})
        pens    = ct.get("gap_penalties", {})
        aff_w   = ct.get("affinity_weights", {})
        aff_c   = ct.get("affinity_contributions", {})
        n       = ct.get("normalization", {})
        fc      = ct.get("final_chain", {})

        # Gap-C: pre_norm / norm_note
        pre_norm  = rec.get("pre_norm_score")
        norm_note = rec.get("norm_note", "")

        # Gap-3: explainability_matrix
        em = rec.get("explainability_matrix", {})
        em_spread  = em.get("paradigm_spread", 0)
        em_conc    = em.get("paradigm_concurrence", {})
        em_flag    = em.get("structural_friction_flag", "")

        chain_table = cls._norm_chain_html(ct) if n else "<p>No chain trace.</p>"
        gap_table   = cls._gap_table_html(boosts, pens)
        aff_table   = cls._affinity_table_html(aff_w, aff_c, pt)

        # Build affinity source badge
        src_color = {"exact": "#1b5e20", "keyword": "#0d47a1", "domain_default": "#555"}.get(src, "#555")
        src_desc  = {"llm":    "planet affinities determined by Claude LLM for this chart",
                     "exact":  "LLM-provided field (exact match)",
                     "keyword":"LLM-provided field (keyword fallback)"}.get(src, src)

        # Composite vs affinity breakdown bar
        c_norm = n.get("composite_norm", 0)
        a_norm = n.get("affinity_norm", 0)
        blended = n.get("blended", 0)
        dw = n.get("domain_blend_weight", 0.6)
        aw = n.get("affinity_blend_weight", 0.4)
        bar_composite = min(c_norm, 100)
        bar_affinity  = min(a_norm, 100)

        # Top 3 contributing planets for this branch
        top3 = sorted(aff_c.items(), key=lambda x: -x[1])[:3]
        top3_str = " | ".join(f"{p} ({v:.1f})" for p, v in top3) if top3 else "none"

        # Method scores for summary header
        _ms = rec.get("method_scores", rec.get("bvb_method_scores", {}))
        knrao_s    = _ms.get("knrao", rec.get("knrao_score", 0))
        kp_s       = _ms.get("kp",    rec.get("kp_score", 0))
        jai_s      = _ms.get("jaimini", rec.get("jaimini_score", 0))
        par_s      = _ms.get("parashara", rec.get("parashara_score", 0))
        method_total = rec.get("method_total_score", rec.get("bvb_score", 0))
        method_log_html = cls._method_log_html(rec, esc)

        # LLM narrative — canonical key is "astrological_reason" (engine merge), fallback to legacy key
        llm_narr = (rec.get("astrological_reason","") or rec.get("llm_astrological_reason","")).strip()
        llm_score = rec.get("llm_score")
        if llm_narr:
            llm_score_badge = (f'<span style="background:#1565c0;color:#fff;font-size:.72rem;'
                               f'padding:2px 8px;border-radius:10px;margin-left:10px">LLM {llm_score:.0f}</span>'
                               if llm_score is not None else "")
            llm_narr_html = (
                f'<div style="margin:10px 0 6px;padding:12px 16px;background:#e8f4fd;border-left:4px solid #1565c0;'
                f'border-radius:0 6px 6px 0">'
                f'<div style="font-size:.72rem;font-weight:700;color:#1565c0;letter-spacing:.05em;margin-bottom:5px">'
                f'⊙ LLM ASTROLOGICAL JUSTIFICATION{llm_score_badge}</div>'
                f'<div style="font-size:.83rem;color:#1a1a2e;line-height:1.65">{esc(llm_narr)}</div>'
                f'</div>'
            )
        else:
            llm_narr_html = (
                '<div style="margin:10px 0 6px;padding:8px 16px;background:#f5f5f5;border-left:4px solid #bdbdbd;'
                'border-radius:0 6px 6px 0;color:#9e9e9e;font-size:.78rem;font-style:italic">'
                '⊙ LLM narrative not available for this field (LLM may not have been invoked or field was outside top-35).'
                '</div>'
            )
        llm_payload_html = cls._llm_payload_html(rec, esc)

        # Fired gap boosts summary (top 3)
        top_boosts = sorted(boosts.items(), key=lambda x: -x[1])[:3]
        boosts_str = ", ".join(f"{k}={v*100:+.1f}%" for k, v in top_boosts) if top_boosts else "none"
        top_pens   = sorted(pens.items(), key=lambda x: x[1])[:3]
        pens_str   = ", ".join(f"{k}={v*100:+.1f}%" for k, v in top_pens) if top_pens else "none"

        return f"""
<details class='field-block'>
  <summary class='field-summary'>
    <span class='fb-rank'>#{rank}</span>
    <span class='fb-label'>{label}</span>
    <span class='fb-domain'>[{esc(rec['domain'])}]</span>
    <span class='fb-score'>Score: {score:.2f}</span>
    <span class='fb-src' style='color:{src_color}'>{esc(src)}</span>
    <span class='fb-top3'>Top planets: {esc(top3_str)}</span>
  </summary>
  <div class='field-body'>

    {llm_narr_html}
    {llm_payload_html}

    <div class='trace-section'>
      <table style='width:100%;font-size:.82rem;border-collapse:collapse'>
        <tr>
          <td style='padding:4px 10px;width:50%'>
            <strong>Affinity source:</strong> <span style='color:{src_color};font-weight:600'>{esc(src)}</span><br>
            <small style='color:#555'>{esc(src_desc)}</small>
          </td>
          <td style='padding:4px 10px'>
            <strong>Top contributing planets:</strong> {esc(top3_str)}<br>
            <strong>Top boosts:</strong> <span style='color:#2e7d32'>{esc(boosts_str)}</span><br>
            <strong>Top penalties:</strong> <span style='color:#c62828'>{esc(pens_str)}</span>
          </td>
        </tr>
      </table>
      <div style='margin:8px 10px 4px;font-size:.79rem;color:#555'>
        Score blend: <strong>{dw}×</strong>composite({c_norm:.1f}) + <strong>{aw}×</strong>affinity({a_norm:.1f}) = <strong>{blended:.2f}</strong>
        <span style='margin-left:14px'>
          Composite <span style='display:inline-block;width:{bar_composite:.0f}px;height:8px;background:#1565c0;vertical-align:middle'></span>
          Affinity <span style='display:inline-block;width:{bar_affinity:.0f}px;height:8px;background:#4caf50;vertical-align:middle'></span>
        </span>
      </div>
    </div>

    <details class='sub-section' open>
      <summary class='ss-hdr'>① Branch Affinity Weights — planet weight × eff_strength → contribution</summary>
      <div class='ss-body'>
        <p class='ss-note'>Source: <strong>{esc(src)}</strong> — {esc(src_desc)}<br>
        Formula: contribution = weight × eff_strength × 100 &nbsp;|&nbsp; Affinity score = Σ all contributions = {n.get('affinity_score_raw',0):.4f}</p>
        {aff_table}
      </div>
    </details>

    <details class='sub-section' open>
      <summary class='ss-hdr'>② Gap Adjustments fired — {len(boosts)} boost(s), {len(pens)} penalt(ies)</summary>
      <div class='ss-body'>
        {gap_table}
        <p class='ss-note'>gap_boost_total (capped at +0.65/−0.20) = <strong>{ct.get('gap_boost_total',0)*100:+.2f}%</strong> &nbsp;|&nbsp;
        gap_penalty_total = <strong>{ct.get('gap_penalty_total',0)*100:.2f}%</strong></p>
      </div>
    </details>

    <details class='sub-section' open>
      <summary class='ss-hdr'>③ Final Score Chain — every multiplication step</summary>
      <div class='ss-body'>
        {chain_table}
        {(
          f"<p class='ss-note' style='margin-top:6px'>"
          f"<strong>Pre-normalisation score:</strong> {pre_norm:.4f} &nbsp;→&nbsp; "
          f"<strong>Displayed score:</strong> {score:.2f} &nbsp;|&nbsp; "
          f"<em>{esc(norm_note)}</em></p>"
        ) if pre_norm is not None else ""}
      </div>
    </details>

    <details class='sub-section' open>
      <summary class='ss-hdr'>④ Paradigm Concurrence — spread={em_spread:.1f}{" ⚠ FRICTION" if em_flag else ""}</summary>
      <div class='ss-body'>
        {(f"<div style='padding:6px 10px;background:#fff3e0;border-left:3px solid #e65100;"
           f"border-radius:4px;font-size:.80rem;color:#bf360c;margin-bottom:8px'>"
           f"⚠ {esc(em_flag)}</div>") if em_flag else
          "<p style='color:#2e7d32;font-size:.80rem;margin:0 0 6px'>✓ No paradigm friction detected.</p>"}
        <table style='border-collapse:collapse;width:100%;font-size:.80rem'>
          <thead><tr style='background:#f5f5f5'>
            <th style='padding:4px 10px;text-align:left'>Method</th>
            <th style='padding:4px 10px;text-align:right'>Norm Score</th>
            <th style='padding:4px 10px;text-align:left'>Status</th>
          </tr></thead>
          <tbody>
            {"".join(
              f"<tr><td style='padding:3px 10px;font-weight:600'>{esc(m.title())}</td>"
              f"<td style='padding:3px 10px;text-align:right;font-family:Consolas'>{v.get('score',0):.1f}</td>"
              f"<td style='padding:3px 10px;color:{'#2e7d32' if v.get('score',0)>=30 else '#c62828'}'>{esc(v.get('status',''))}</td></tr>"
              for m, v in em_conc.items()
            )}
          </tbody>
        </table>
        <p class='ss-note'>Paradigm spread = max − min of normalised method scores. Threshold: &gt;30 → friction flag.</p>
      </div>
    </details>

    <details class='sub-section'>
      <summary class='ss-hdr'>⑤ Method I/O Log — KNRao={knrao_s:.0f} · KP={kp_s:.0f} · Jaimini={jai_s:.0f} · Parashara={par_s:.0f} → combined={method_total:.0f}</summary>
      <div class='ss-body'>
        {method_log_html}
      </div>
    </details>

  </div>
</details>"""

    @classmethod
    def _registry_branch_meta(cls, field_id: str) -> Optional[Dict]:
        """Look up a field's branch metadata in the staged v12 course registry.

        Reuses the engine's existing lru_cache(1)-wrapped loader
        (engine_io._load_course_registry) rather than re-reading/parsing the
        1.9MB india_course_registry_v12.json here — the loader already
        guarantees a single shared in-memory dict for the process lifetime.
        Returns None (not {}) when the registry can't be loaded at all, or
        when field_id isn't a key in it (a genuine per-field coverage gap —
        callers must fall back to their existing generic content for that
        field only, not fail the whole section).
        """
        if not field_id:
            return None
        try:
            from .engine_io import _load_course_registry
        except ImportError:
            try:
                from engine_io import _load_course_registry  # type: ignore
            except Exception:
                return None
        try:
            registry = _load_course_registry()
        except Exception:
            return None
        return registry.get(field_id)

    @classmethod
    def _ranking_overview_html(cls, rankings: List[Dict], top_n: int, esc) -> str:
        """Ranking comparison table: all top-N fields, side-by-side key metrics."""
        rows = ""
        for i, rec in enumerate(rankings[:top_n], 1):
            ct  = rec.get("calc_trace", {})
            n   = ct.get("normalization", {})
            fc  = ct.get("final_chain", {})
            boosts  = ct.get("gap_boosts", {})
            pens    = ct.get("gap_penalties", {})
            bg  = "#e8f5e9" if i <= 3 else ("#fff8e1" if i <= 7 else "")
            gap_b = ct.get("gap_boost_total", 0)
            gap_p = ct.get("gap_penalty_total", 0)
            gap_net = gap_b + gap_p
            gap_col = "#2e7d32" if gap_net > 0 else ("#c62828" if gap_net < 0 else "#555")
            thresh_ok = fc.get("threshold_mult", 1.0) == 1.0
            qa_ok     = fc.get("qa_gate_mult", 1.0) == 1.0
            mm_ok     = fc.get("mismatch_mult", 1.0) == 1.0
            gates = ("✓" if thresh_ok else "✗thresh") + " " + ("✓" if mm_ok else "✗mm") + " " + ("✓" if qa_ok else "✗qa")
            gates_col = "#2e7d32" if (thresh_ok and qa_ok and mm_ok) else "#c62828"

            # ── Spec §12 item 4 extension: 4 new columns using data already
            # computed elsewhere in the pipeline (see class-level docstrings
            # on the §12 helper methods above for full sourcing notes). ──
            # Recommended Stream: india_course_registry_v12.json is now staged
            # (registry_loader_v12.py / _load_course_registry()). The registry
            # has NO literal "stream" key (no Science/Commerce/Arts taxonomy),
            # so a field's registry `field`/`track` label (a real, curated,
            # more specific classification than the coarse `domain` bucket)
            # is used as the stream label when the field_id is found in the
            # registry; falls back to `domain` for any field_id not present
            # in the registry (coverage gap — see _registry_branch_meta()).
            _reg_meta = cls._registry_branch_meta(rec.get("field_id", ""))
            if _reg_meta:
                rec_stream = esc(_reg_meta.get("field") or _reg_meta.get("track") or rec.get("domain", "?"))
            else:
                rec_stream = esc(rec.get("domain", "?"))

            # Peak Career Dasha Window: sourced from the per-field dasha-
            # coverage-reject verdict stashed on the row by engine.py's
            # §8.5 dasha_longevity integration (dasha_coverage_reject_end_age
            # / dasha_coverage_reject_applied).
            dc_end = rec.get("dasha_coverage_reject_end_age")
            dc_reject = rec.get("dasha_coverage_reject_applied")
            if dc_reject:
                dasha_window = f"Support ends ~age {dc_end}"
            elif dc_end is not None:
                dasha_window = f"Sustains through ~age {dc_end}"
            else:
                dasha_window = "n/a"

            # Wealth-Sustainability Note: sourced from boosts.py's
            # compute_wealth_potential() result, attached per-field as
            # rec['wealth_potential'] in engine.py.
            wp = rec.get("wealth_potential") or {}
            wealth_label = wp.get("wealth_potential", "—")
            wealth_flag  = wp.get("prestige_strong_wealth_uncertain_flag")
            wealth_note  = ("Prestige-strong, wealth-durability uncertain" if wealth_flag
                            else wealth_label)

            # Risk/Caveat: sourced from existing per-row flags already
            # attached by engine.py's finalize step (hard_lockout,
            # core_three_excluded_applied, dasha_coverage_reject_applied).
            risks = []
            if rec.get("hard_lockout"):
                risks.append("hard-lockout")
            if rec.get("core_three_excluded_applied"):
                risks.append("core-3 excluded")
            if dc_reject:
                risks.append("dasha-coverage downrank")
            risk_str = ", ".join(risks) if risks else "none flagged"
            risk_col = "#c62828" if risks else "#2e7d32"

            # ── Gap A fix: surface score_ceiling_tie / tier_decision_trace,
            # which were computed by the tiered-ranking algorithm but never
            # rendered anywhere in the HTML report. Missing on rows whose
            # code path never populated tie-resolution data. ──
            is_tie = bool(rec.get("score_ceiling_tie"))
            tie_trace = rec.get("tier_decision_trace") or []
            score_cell = f"{rec['final_score']:.2f}"
            if is_tie:
                trace_tip = esc(" | ".join(str(t) for t in tie_trace)) if tie_trace else "Tie resolved by Tier 2/3 mechanisms"
                t1 = rec.get("tier1_score")
                t2 = rec.get("tier2_score")
                t3 = rec.get("tier3_score")
                tier_parts = []
                if t1 is not None:
                    tier_parts.append(f"T1={t1:.2f}" if isinstance(t1, (int, float)) else f"T1={esc(str(t1))}")
                if t2 is not None:
                    tier_parts.append(f"T2={t2:.2f}" if isinstance(t2, (int, float)) else f"T2={esc(str(t2))}")
                if t3 is not None:
                    tier_parts.append(f"T3={t3:.2f}" if isinstance(t3, (int, float)) else f"T3={esc(str(t3))}")
                tier_breakdown = (" <span style='display:block;font-size:.68rem;color:#555;font-family:Consolas'>"
                                   f"{' / '.join(tier_parts)}</span>") if tier_parts else ""
                score_cell = (
                    f"{rec['final_score']:.2f}"
                    f"<span title='{trace_tip}' "
                    f"style='display:inline-block;margin-left:5px;padding:1px 5px;border-radius:8px;"
                    f"background:#fff3e0;color:#e65100;font-size:.66rem;font-weight:700;border:1px solid #ffb74d;"
                    f"cursor:help' >&#9878; tie-resolved</span>{tier_breakdown}"
                )

            rows += (
                f"<tr style='background:{bg}'>"
                f"<td class='ro-rank'>{i}</td>"
                f"<td class='ro-label'>{esc(rec['field_label'])}</td>"
                f"<td class='ro-dom'>{esc(rec['domain'])}</td>"
                f"<td class='ro-num'>{n.get('composite_norm',0):.1f}</td>"
                f"<td class='ro-num'>{n.get('affinity_norm',0):.1f}</td>"
                f"<td class='ro-num'>{n.get('blended',0):.2f}</td>"
                f"<td class='ro-num' style='color:{gap_col};font-weight:600'>{gap_net*100:+.1f}%</td>"
                f"<td class='ro-num' style='color:{gates_col}'>{gates}</td>"
                f"<td class='ro-score'>{score_cell}</td>"
                f"<td class='ro-dom'>{rec_stream}</td>"
                f"<td class='ro-dom' style='font-size:.76rem'>{esc(dasha_window)}</td>"
                f"<td class='ro-dom' style='font-size:.76rem'>{esc(wealth_note)}</td>"
                f"<td class='ro-dom' style='font-size:.76rem;color:{risk_col};font-weight:600'>{esc(risk_str)}</td>"
                f"</tr>"
            )

        # ── Gap A fix: concise CLI disclosure of tie-resolved fields,
        # built dynamically from each row's own tier_decision_trace text
        # (not hardcoded). ──
        tied_rows = [r for r in rankings[:top_n] if r.get("score_ceiling_tie")]
        if tied_rows:
            parts = []
            for r in tied_rows:
                trace = r.get("tier_decision_trace") or []
                reason = trace[-1] if trace else "resolved via Tier 2/3 mechanisms"
                parts.append(f"{r.get('field_label','?')} ({reason})")
            print(f"[TIE-BREAK DISCLOSURE] {len(tied_rows)} field(s) had score_ceiling_tie: "
                  + "; ".join(parts))

        return (
            f"<table class='ro-table'>"
            f"<thead><tr>"
            f"<th>#</th><th>Field</th><th>Domain</th>"
            f"<th title='Composite aptitude score normalised 0-100'>Comp/100</th>"
            f"<th title='Branch affinity score normalised 0-100'>Aff/100</th>"
            f"<th title='0.60×Comp + 0.40×Aff'>Blended</th>"
            f"<th title='Net gap boost+penalty applied'>Gap%</th>"
            f"<th title='Threshold / Mismatch / QA gates'>Gates</th>"
            f"<th title='&#9878; badge = score_ceiling_tie: near-tie resolved by Tier 2/3; hover badge for tier_decision_trace'>Score</th>"
            f"<th title='From india_course_registry_v12.json (field/track); falls back to Domain when a field is not in the registry'>Rec. Stream</th>"
            f"<th title='From dasha_longevity §8.5 coverage-reject verdict'>Peak Dasha Window</th>"
            f"<th title='From compute_wealth_potential()'>Wealth Note</th>"
            f"<th title='hard_lockout / core-3 exclusion / dasha-coverage downrank flags'>Risk/Caveat</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    @classmethod
    def _edu_planet_table_html(cls, edu_reasons: Dict, edu_effs: Dict,
                                planet_trace: Dict, esc) -> str:
        """Table of educational planets: why included, raw eff_strength, Kendradi Bala, edu_eff."""
        rows = ""
        ranked = sorted(edu_effs.items(), key=lambda x: -x[1])
        for rank_i, (p, edu_eff) in enumerate(ranked, 1):
            reasons  = ", ".join(edu_reasons.get(p, []))
            pt       = planet_trace.get(p, {})
            raw_eff  = pt.get("eff_strength", 0.0)
            kb_mod   = round(edu_eff / raw_eff, 3) if raw_eff > 0 else 1.0
            house    = pt.get("house", "?")
            sign     = pt.get("sign", "?")
            dignity  = pt.get("dignity", "")
            eff_cls  = "tr-strong" if edu_eff >= 1.2 else ("tr-weak" if edu_eff < 0.7 else "tr-mid")
            rows += (f"<tr class='{eff_cls}'>"
                     f"<td style='font-weight:700;color:#1a237e'>{rank_i}</td>"
                     f"<td style='font-weight:700'>{esc(p)}</td>"
                     f"<td>{esc(sign)} H{house}</td>"
                     f"<td style='font-style:italic;font-size:.78rem'>{esc(dignity or 'neutral')}</td>"
                     f"<td style='font-family:Consolas;text-align:right'>{raw_eff:.4f}</td>"
                     f"<td style='text-align:center'>{kb_mod:.3f}×</td>"
                     f"<td style='font-weight:700;color:#1b5e20;text-align:right'>{edu_eff:.4f}</td>"
                     f"<td style='font-size:.75rem;color:#555'>{esc(reasons)}</td>"
                     f"</tr>")
        return (f"<table class='planet-table' style='min-width:700px'>"
                f"<thead><tr style='background:#2e7d32'>"
                f"<th>Rank</th><th>Planet</th><th>Sign/House</th><th>Dignity</th>"
                f"<th>Eff Strength</th><th>Kendradi×</th>"
                f"<th style='background:#1b5e20'>Edu Strength</th><th>Why Included</th>"
                f"</tr></thead><tbody>{rows}</tbody></table>")

    @classmethod
    def _phase1_html(cls, planet_trace: Dict, active_lord: str, peak_lord: str,
                     karakas: Dict, aspects_h10: List[str], yogas: List[str],
                     edu_reasons: Dict, edu_effs: Dict, esc) -> str:
        """Phase 1 summary: chart-level calculations computed once for all branches.
        Shows (a) all 9 planet effective strengths, and (b) the educational planet
        subset with Kendradi Bala applied — this subset is what drives field scoring.
        """
        planet_table = cls._planet_trace_html(planet_trace) if planet_trace else "<p>No planet data.</p>"
        edu_table    = cls._edu_planet_table_html(edu_reasons, edu_effs, planet_trace, esc) if edu_effs else "<p>No educational planet data.</p>"
        ak  = esc(karakas.get("AK", "?"))
        amk = esc(karakas.get("AmK", "?"))
        asp = esc(", ".join(aspects_h10) if aspects_h10 else "none")
        yog = esc(", ".join(yogas) if yogas else "none")

        # All-planet rank
        ranked_all = sorted(planet_trace.items(), key=lambda x: -x[1].get("eff_strength",0)) if planet_trace else []
        rank_all_str = " > ".join(f"{p}({t['eff_strength']:.3f})" for p, t in ranked_all)

        # Educational planet rank
        ranked_edu = sorted(edu_effs.items(), key=lambda x: -x[1]) if edu_effs else []
        rank_edu_str = " > ".join(f"{p}({v:.3f})" for p, v in ranked_edu)
        edu_excluded = [p for p in (t for t, _ in ranked_all) if p not in edu_effs]
        excluded_str = ", ".join(edu_excluded) if edu_excluded else "none"

        return f"""
<div class='phase1-block'>
  <div class='phase1-hdr'>PHASE 1 — Chart-Level Calculations (computed once for all branches)</div>
  <div class='phase1-meta'>
    <span><strong>Active Dasha:</strong> {esc(active_lord or '?')}</span>
    <span><strong>Peak Career MD:</strong> {esc(peak_lord or '?')}</span>
    <span><strong>AK:</strong> {ak}</span>
    <span><strong>AmK:</strong> {amk}</span>
    <span><strong>Yogas:</strong> {yog}</span>
    <span><strong>Aspecting H10:</strong> {asp}</span>
  </div>

  <details class='sub-section'>
    <summary class='ss-hdr'>Step 1a — All 9 Planet Effective Strengths (raw chart computation)</summary>
    <div class='ss-body'>
      <p class='ss-note'>Formula: (raw_shadbala ÷ min_v) × dig × war × var × nak × pb × func × digbala × caz × comb</p>
      {planet_table}
      <p class='ss-note'>⟲=Retrograde  NB=NeechaBhanga  ☀=Cazimi  🔥=Combust  V°=Vargottama</p>
      <div class='phase1-rank'>All-planet ranking: <span class='rank-chain'>{esc(rank_all_str)}</span></div>
    </div>
  </details>

  <details class='sub-section' open>
    <summary class='ss-hdr'>Step 1b — Educational Planet Set (H1/2/4/5/9/10/11 lords + occupants + AK + AmK)</summary>
    <div class='ss-body'>
      <p class='ss-note'>
        Only these {len(edu_effs)} planets signify education/career houses and drive field scoring.<br>
        Strength = eff_strength × Kendradi Bala (positional modifier: Kendra=1.0×, Trikona=0.92×, Panapara=0.85×, Apoklima/Dusthana=0.70×)<br>
        <strong>Excluded from field scoring</strong> (no educational house connection): {esc(excluded_str)}
      </p>
      {edu_table}
      <div class='phase1-rank' style='margin-top:8px'>
        Educational planet ranking: <span class='rank-chain'>{esc(rank_edu_str)}</span>
      </div>
    </div>
  </details>
</div>"""


    @classmethod
    def _method_log_html(cls, rec: Dict, esc) -> str:
        """Render per-method input/output log for one field as an HTML section."""
        ml = rec.get("method_log", {})
        if not ml:
            return "<p style=\'color:#888\'>No method log available.</p>"

        METHOD_COLORS = {
            "knrao":    ("#1a237e", "#e8eaf6"),
            "kp":       ("#1b5e20", "#e8f5e9"),
            "jaimini":  ("#4a148c", "#f3e5f5"),
            "parashara":("#e65100", "#fff3e0"),
            "dashamsha":("#880e4f", "#fce4ec"),
            "sudarshana":("#0f766e", "#ecfdf5"),
        }
        blocks = []
        for mkey in ("knrao", "kp", "jaimini", "parashara", "dashamsha", "sudarshana"):
            m = ml.get(mkey, {})
            if not m:
                continue
            fg, bg = METHOD_COLORS.get(mkey, ("#333", "#f9f9f9"))
            score   = m.get("score", 0)
            weight  = m.get("weight", 0)
            norm    = m.get("normalized_score", 0)
            contrib = m.get("weighted_contribution", round(float(norm) * float(weight), 2))
            comps   = m.get("components", {})
            traces  = m.get("trace", [])
            ms      = m.get("exec_ms", m.get("ms", 0))   # Gap-6 fix: renamed ms→exec_ms
            inp     = m.get("inputs", {})

            # Input row
            inp_cells = "".join(
                f"<td style=\'padding:3px 8px;font-size:.76rem\'><strong>{esc(str(k))}:</strong> {esc(str(v))}</td>"
                for k, v in inp.items() if v
            )

            # Component rows
            # Pre-existing gap fix: some methods (e.g. Parashara) store non-numeric
            # narrative strings alongside numeric components in `comps`, and
            # round(float(v), 2) crashed the whole report build on the first
            # such string it hit. Render numeric values rounded as before;
            # render anything that isn't float-able as plain escaped text.
            def _comp_val_html(v):
                try:
                    return esc(str(round(float(v), 2)))
                except (TypeError, ValueError):
                    return esc(str(v))
            comp_rows = "".join(
                f"<tr><td style=\'font-family:Consolas;font-size:.75rem;padding:2px 8px;color:#555\'>{esc(k)}</td>"
                f"<td style=\'text-align:right;font-family:Consolas;font-size:.75rem;padding:2px 8px;font-weight:600;color:{fg}\'>{_comp_val_html(v)}</td></tr>"
                for k, v in comps.items()
            ) if comps else "<tr><td colspan=\'2\' style=\'color:#999;font-size:.75rem\'>—</td></tr>"

            # Trace lines
            trace_html = "<br>".join(esc(t) for t in traces[:8]) if traces else "<em style=\'color:#999\'>none</em>"

            blocks.append(f"""
<div style=\'border:1px solid {fg}30;border-radius:8px;margin-bottom:10px;overflow:hidden\'>
  <div style=\'background:{bg};border-left:4px solid {fg};padding:8px 14px;display:flex;align-items:center;gap:16px\'>
    <span style=\'font-weight:700;color:{fg};font-size:.88rem\'>{esc(m.get("name","?"))}</span>
    <span style=\'background:{fg};color:#fff;border-radius:4px;padding:2px 10px;font-size:.8rem;font-weight:700\'>
      Score: {score:.1f}
    </span>
    <span style=\\'color:#555;font-size:.78rem\\'>Norm: {norm:.1f}/100 | Weight: {weight:.0%} → contrib: {contrib:.1f}</span>
    <span style=\'margin-left:auto;color:#888;font-size:.73rem\'>{ms:.0f}ms</span>
  </div>
  <div style=\'display:grid;grid-template-columns:1fr 1fr;gap:0;padding:0\'>
    <div style=\'padding:8px 14px;border-right:1px solid #eee\'>
      <div style=\'font-size:.76rem;font-weight:700;color:{fg};margin-bottom:4px;text-transform:uppercase\'>Inputs</div>
      <table style=\'border-collapse:collapse;width:100%\'><tr>{inp_cells}</tr></table>
    </div>
    <div style=\'padding:8px 14px\'>
      <div style=\'font-size:.76rem;font-weight:700;color:{fg};margin-bottom:4px;text-transform:uppercase\'>Components</div>
      <table style=\'border-collapse:collapse;width:100%\'>{comp_rows}</table>
    </div>
  </div>
  <div style=\'padding:6px 14px 8px;border-top:1px solid #eee;background:#fafafa\'>
    <div style=\'font-size:.74rem;font-weight:700;color:#555;margin-bottom:3px\'>Trace</div>
    <div style=\'font-family:Consolas;font-size:.73rem;color:#333;line-height:1.55\'>{trace_html}</div>
  </div>
        </div>""")
        return "\n".join(blocks)

    @classmethod
    def _llm_payload_html(cls, rec: Dict, esc) -> str:
        """Render the full LLM JSON payload for one field as a collapsible section."""
        payload = rec.get("llm_payload", {}) or {}
        if not payload:
            return "<p style='color:#888'>No LLM JSON payload available.</p>"
        try:
            payload_text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
        except Exception:
            payload_text = str(payload)
        selection = esc(str(payload.get("selection_rationale", rec.get("llm_selection_rationale", "")) or ""))
        provider = esc(str(payload.get("provider", "unknown")))
        return f"""
<details style='border:1px solid #dfe3ec;border-radius:8px;background:#fbfcff;margin-top:10px'>
  <summary style='cursor:pointer;padding:10px 14px;font-weight:700;color:#1a237e;list-style:none'>
    LLM JSON Payload <span style='font-weight:600;color:#546e7a'>[{provider}]</span>
  </summary>
  <div style='padding:12px 14px;border-top:1px solid #e7ebf5'>
    <div style='font-size:.78rem;color:#555;margin-bottom:8px'><strong>Selection rationale:</strong> {selection or "—"}</div>
    <pre style='margin:0;font-family:Consolas,"Courier New",monospace;font-size:.76rem;line-height:1.55;white-space:pre-wrap;word-break:break-word;background:#0b1020;color:#dbe4ff;padding:12px;border-radius:6px;overflow-x:auto'>{esc(payload_text)}</pre>
  </div>
</details>"""

    @classmethod
    def _all_fields_table_html(cls, rankings: List[Dict], esc) -> str:
        """Full sortable table: all fields × Eng% × LLM% × method scores × LLM narrative."""
        if not rankings:
            return "<p>No results.</p>"
        top_raw = rankings[0]["final_score"] if rankings else 1.0
        top_llm = max((r.get("llm_score") or 0) for r in rankings) or 1.0

        domain_colours = {
            "technology":     "#0d47a1", "engineering":   "#1b5e20", "medicine":      "#b71c1c",
            "science":        "#006064", "arts":          "#6a1b9a", "design":        "#880e4f",
            "law":            "#e65100", "business":      "#4e342e", "education":     "#33691e",
            "humanities":     "#37474f", "interdisciplinary": "#455a64",
        }

        rows = ""
        for i, r in enumerate(rankings, 1):
            eng_pct = max(1, min(100, round(r["final_score"] / top_raw * 100)))
            llm_raw = r.get("llm_score") or 0
            llm_pct = max(1, min(100, round(llm_raw / top_llm * 100))) if llm_raw else 0
            llm_pct_str = f"{llm_pct}%" if llm_raw else "—"

            dom     = r.get("domain","")
            dc      = domain_colours.get(dom, "#455a64")
            bg      = "#e8f5e9" if i<=3 else ("#fff8e1" if i<=7 else ("" if i<=15 else "#fafafa"))

            knrao_s   = r.get("knrao_score",   r.get("method_scores",{}).get("knrao",0))
            kp_s      = r.get("kp_score",      r.get("method_scores",{}).get("kp",0))
            jai_s     = r.get("jaimini_score",  r.get("method_scores",{}).get("jaimini",0))
            par_s     = r.get("parashara_score",r.get("method_scores",{}).get("parashara",0))

            narrative = (r.get("astrological_reason","")
                         or r.get("llm_astrological_reason","")
                         or r.get("llm_narrative","")).strip()
            narr_html = (f'<span style="color:#1a1a2e;font-size:.78rem;line-height:1.6">{esc(narrative)}</span>'
                         if narrative else '<em style="color:#bbb;font-size:.75rem">No LLM narrative</em>')

            eng_bar_w = eng_pct
            eng_col   = "#1b5e20" if eng_pct>=80 else ("#f57f17" if eng_pct>=60 else "#b71c1c")
            llm_bar_w = llm_pct
            llm_col   = "#1565c0" if llm_pct>=80 else ("#7b1fa2" if llm_pct>=60 else "#546e7a")

            rows += f"""<tr style="background:{bg}" data-eng="{eng_pct}" data-llm="{llm_pct}"
                data-knrao="{knrao_s}" data-kp="{kp_s}" data-jai="{jai_s}" data-par="{par_s}">
  <td style="text-align:center;font-weight:700;color:#1a237e;width:36px">{i}</td>
  <td style="font-weight:600;min-width:180px">{esc(r["field_label"])}</td>
  <td style="width:100px">
    <span style="background:{dc};color:#fff;font-size:.7rem;padding:1px 7px;border-radius:10px">{esc(dom)}</span>
  </td>
  <td style="width:90px">
    <div style="display:flex;align-items:center;gap:6px">
      <div style="width:50px;height:8px;background:#eee;border-radius:4px;overflow:hidden">
        <div style="width:{eng_bar_w}%;height:100%;background:{eng_col};border-radius:4px"></div>
      </div>
      <span style="font-weight:700;color:{eng_col};font-size:.82rem">{eng_pct}%</span>
    </div>
  </td>
  <td style="width:90px">
    <div style="display:flex;align-items:center;gap:6px">
      <div style="width:50px;height:8px;background:#eee;border-radius:4px;overflow:hidden">
        <div style="width:{llm_bar_w}%;height:100%;background:{llm_col};border-radius:4px"></div>
      </div>
      <span style="font-weight:700;color:{llm_col};font-size:.82rem">{llm_pct_str}</span>
    </div>
  </td>
  <td style="font-family:Consolas;font-size:.78rem;text-align:center;color:#1a237e">{knrao_s:.0f}</td>
  <td style="font-family:Consolas;font-size:.78rem;text-align:center;color:#1b5e20">{kp_s:.0f}</td>
  <td style="font-family:Consolas;font-size:.78rem;text-align:center;color:#4a148c">{jai_s:.0f}</td>
  <td style="font-family:Consolas;font-size:.78rem;text-align:center;color:#e65100">{par_s:.0f}</td>
  <td style="min-width:280px;padding:6px 10px">{narr_html}</td>
</tr>"""

        return f"""
<div style="overflow-x:auto">
<table id="all-fields-tbl" style="width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.10)">
  <thead>
    <tr style="background:#1a237e;color:#fff">
      <th onclick="sortTbl(0)" style="padding:9px 8px;cursor:pointer;white-space:nowrap;font-size:.73rem">#</th>
      <th onclick="sortTbl(1)" style="padding:9px 10px;cursor:pointer;text-align:left;font-size:.73rem">Field ↕</th>
      <th onclick="sortTbl(2)" style="padding:9px 10px;cursor:pointer;text-align:left;font-size:.73rem">Domain ↕</th>
      <th onclick="sortTbl(3)" style="padding:9px 8px;cursor:pointer;text-align:left;font-size:.73rem">Eng% ↕</th>
      <th onclick="sortTbl(4)" style="padding:9px 8px;cursor:pointer;text-align:left;font-size:.73rem">LLM% ↕</th>
      <th onclick="sortTbl(5)" style="padding:9px 8px;cursor:pointer;font-size:.73rem" title="K.N. Rao score /100">KNRao ↕</th>
      <th onclick="sortTbl(6)" style="padding:9px 8px;cursor:pointer;font-size:.73rem" title="KP score /100">KP ↕</th>
      <th onclick="sortTbl(7)" style="padding:9px 8px;cursor:pointer;font-size:.73rem" title="Jaimini score /100">Jai ↕</th>
      <th onclick="sortTbl(8)" style="padding:9px 8px;cursor:pointer;font-size:.73rem" title="Parashara score /100">Para ↕</th>
      <th style="padding:9px 10px;text-align:left;font-size:.73rem;min-width:280px">LLM Narrative</th>
    </tr>
  </thead>
  <tbody id="all-fields-tbody">{rows}</tbody>
</table>
</div>"""

    # ── Spec §12 sections 1,2,4-ext,5,6,7 ──────────────────────────────────
    # Built on top of already-computed pipeline data (payload attrs, rec/
    # calc_trace fields, rankings-level flags). No fabricated numbers.

    @classmethod
    def _chart_summary_html(cls, payload, rankings: List[Dict], esc) -> str:
        """Spec §12 item 1 — Chart Summary: Lagna, Moon/Sun sign, career-house
        lords, AK/AmK, birth-time confidence note.

        Source: payload.lagna_sign / payload.planets_d1 (Moon/Sun sign) /
        payload.house_lords (H1/H9/H10 lords) / payload.atmakaraka /
        payload.amatyakaraka / payload.birth_time_precision — all already
        populated on the NatalPayloadV2 object passed into this function.
        """
        lagna = getattr(payload, "lagna_sign", "") or "?"
        planets_d1 = getattr(payload, "planets_d1", {}) or {}
        moon_sign = (planets_d1.get("Moon", {}) or {}).get("sign", "?")
        sun_sign  = (planets_d1.get("Sun", {}) or {}).get("sign", "?")
        hl = getattr(payload, "house_lords", {}) or {}
        h1_lord  = hl.get("1")  or hl.get(1)  or "?"
        h9_lord  = hl.get("9")  or hl.get(9)  or "?"
        h10_lord = hl.get("10") or hl.get(10) or "?"
        ak  = getattr(payload, "atmakaraka", "") or "?"
        amk = getattr(payload, "amatyakaraka", "") or "?"
        btp = getattr(payload, "birth_time_precision", "unknown") or "unknown"
        d60_allowed = None
        cp = getattr(payload, "calculation_policy", None)
        if cp is not None:
            d60_allowed = getattr(cp, "d60_claims_allowed", None)
        btp_note = {
            "exact": "Birth time is treated as exact — full precision techniques (KP sub-lord, D60 Shashtiamsha) are applied at full weight.",
            "approximate": "Birth time is approximate — cusp-sensitive/high-division techniques (KP sub-lord, D60) are down-weighted per calculation policy.",
            "unknown": "Birth time precision is unknown/unrecorded — cusp-sensitive/high-division techniques (KP sub-lord, D60) are treated cautiously or excluded per calculation policy.",
        }.get(str(btp).lower(), f"Birth-time precision recorded as '{esc(btp)}'.")
        if d60_allowed is not None:
            btp_note += f" D60 claims allowed by policy: {'yes' if d60_allowed else 'no'}."

        n_top = len(rankings)
        html = f"""
<div class='phase1-block' style='background:#e3f2fd;border-color:#1565c0'>
  <div class='phase1-hdr' style='color:#0d47a1'>SECTION 1 — Chart Summary</div>
  <div class='phase1-meta'>
    <span><strong>Lagna:</strong> {esc(lagna)}</span>
    <span><strong>Moon Sign:</strong> {esc(moon_sign)}</span>
    <span><strong>Sun Sign:</strong> {esc(sun_sign)}</span>
    <span><strong>H1 Lord:</strong> {esc(h1_lord)}</span>
    <span><strong>H9 Lord:</strong> {esc(h9_lord)}</span>
    <span><strong>H10 Lord:</strong> {esc(h10_lord)}</span>
    <span><strong>AK:</strong> {esc(ak)}</span>
    <span><strong>AmK:</strong> {esc(amk)}</span>
  </div>
  <p class='ss-note'>{esc(btp_note)}</p>
  <p class='ss-note'>{n_top} field(s) evaluated for this chart.</p>
</div>"""
        print(f"[SECTION 1 — CHART SUMMARY] Lagna={lagna} Moon={moon_sign} Sun={sun_sign} "
              f"H1={h1_lord} H9={h9_lord} H10={h10_lord} AK={ak} AmK={amk} "
              f"birth_time_precision={btp}")
        return html

    @classmethod
    def _evidence_table_html(cls, rankings: List[Dict], _pt0: Dict, esc) -> str:
        """Spec §12 item 2 — technique-first Evidence Table.

        Rebuilt as one row per named technique (not field x method). For
        field-scoped techniques (D1 Shadbala/Combustion/Avastha/Maitri, D9,
        D10, D24, D60, Yogas, Jaimini, Dasha timeline, Sudarshan, K.N. Rao,
        KP) the finding is pulled from the top-ranked field's own
        method_log/calc_trace (already-computed real data, not fabricated),
        since that is the strongest concrete instance of each technique
        actually firing on this chart. Techniques that are genuinely
        chart-level (D1 Shadbala/Combustion/Avastha/Maitri) are pulled from
        _pt0 (planet_trace), which is shared across all fields.
        """
        top = rankings[0] if rankings else {}
        ml  = top.get("method_log", {}) or {}
        ct  = top.get("calc_trace", {}) or {}

        rows = []

        # D1 Shadbala / Combustion / Avastha / Maitri — chart-level, from planet_trace
        if _pt0:
            strongest = max(_pt0.items(), key=lambda kv: kv[1].get("eff_strength", 0.0))
            combust = [p for p, t in _pt0.items() if t.get("combust")]
            finding = (f"Strongest planet by adjusted shadbala: {strongest[0]} "
                       f"(eff_strength={strongest[1].get('eff_strength',0):.3f}). "
                       f"Combust: {', '.join(combust) if combust else 'none'}.")
            rows.append(("D1 Shadbala / Combustion / Avastha / Maitri", finding,
                         "Governs baseline planetary vitality driving all downstream career/wealth field scores."))
        else:
            rows.append(("D1 Shadbala / Combustion / Avastha / Maitri",
                         "Not available in this report context (planet_trace empty).", "—"))

        # D9 (Navamsha) — from the dedicated D9 confirmation block (navamsha.py's
        # score_navamsha_adjustment output), stored as a sibling of method_log
        # (not a voting method, so it is not inside `ml`/method_log at all).
        d9_block = top.get("d9_navamsha_confirmation", {}) or {}
        if d9_block and d9_block.get("status") == "OBSERVED":
            rows.append(("D9 Navamsha", "; ".join(d9_block.get("trace", [])[:2]) or
                        f"Confirmation score {d9_block.get('d9_confirmation_score', 0):.1f}/100 "
                        f"(multiplier {d9_block.get('multiplier', 1.0)}) for top field.",
                        f"Confirms/refines strength of {esc(top.get('field_label','top field'))} at marriage/dharma-linked maturity."))
        else:
            rows.append(("D9 Navamsha", "Not available in this report context (D9 dignities/field affinity missing).", "—"))

        # D10 Dashamsha
        d10_block = ml.get("dashamsha", {})
        if d10_block:
            rows.append(("D10 Dashamsha", "; ".join(d10_block.get("trace", [])[:2]) or f"Score {d10_block.get('score',0):.1f}/100 for top field.",
                        f"Direct career-house divisional chart evidence for {esc(top.get('field_label','top field'))}."))
        else:
            rows.append(("D10 Dashamsha", "Not available in this report context.", "—"))

        # D24 Siddhamsha — 7th voting method (field_methods/siddhamsha.py via
        # compute_field_method_bundle); method_log key now reachable since
        # siddhamsha.py/shashtiamsha.py are staged in this working copy.
        d24_block = ml.get("siddhamsha", {})
        if d24_block:
            rows.append(("D24 Siddhamsha", "; ".join(d24_block.get("trace", [])[:2]) or f"Score {d24_block.get('score',0):.1f}/100 for top field.",
                        f"Vidya-varga (learning capacity/higher study) evidence for {esc(top.get('field_label','top field'))}, from D24 lagna/4th/5th/9th-lord dignity and vidya karakas."))
        else:
            rows.append(("D24 Siddhamsha", "Not available in this report context.", "—"))

        # D60 Shashtiamsha — 8th voting method (field_methods/shashtiamsha.py
        # via compute_field_method_bundle, score_d60_vote wrapper), small
        # fine-grained confirmation weight.
        d60_block = ml.get("shashtiamsha", {})
        if d60_block:
            rows.append(("D60 Shashtiamsha", "; ".join(d60_block.get("trace", [])[:2]) or f"Score {d60_block.get('score',0):.1f}/100 for top field.",
                        f"Finest-grained deity-quality confirmation on {esc(top.get('field_label','top field'))} (tiebreaker weight, not a primary vote)."))
        else:
            rows.append(("D60 Shashtiamsha", "Not available in this report context.", "—"))

        # Yogas
        yogas = ct.get("yogas_present", []) or []
        if yogas:
            rows.append(("Yogas", f"Detected: {', '.join(yogas)}.", "Raja/Dhana-type yogas strengthen the fields their significators govern."))
        else:
            rows.append(("Yogas", "No yogas recorded on the top field's calc_trace for this run.", "—"))

        # Shadbala — same source as D1 row above, cross-referenced
        rows.append(("Shadbala (six-fold strength)", "See D1 Shadbala row above — six-fold strength feeds eff_strength directly.", "Foundational strength ranking used across every technique below."))

        # Jaimini
        jai = ml.get("jaimini", {})
        if jai:
            rows.append(("Jaimini (Karakas/Chara Dasha)", "; ".join(jai.get("trace", [])[:2]) or f"Score {jai.get('score',0):.1f}/100.",
                        f"AK/AmK-based soul-purpose and career-means signal for {esc(top.get('field_label','top field'))}."))
        else:
            rows.append(("Jaimini (Karakas/Chara Dasha)", "Not available in this report context.", "—"))

        # Combustion/Avastha/Maitri — see D1 row (chart-level, already covered)
        # (kept as a single combined row above per spec's grouping suggestion)

        # Dasha timeline
        dc_reject = top.get("dasha_coverage_reject_applied")
        dc_end = top.get("dasha_coverage_reject_end_age")
        if dc_reject is not None or dc_end is not None:
            finding = (f"Dasha-coverage reject applied (support ends age {dc_end})" if dc_reject
                       else "Dasha coverage sustains through the lookahead window.")
            rows.append(("Dasha Timeline (Vimshottari sustainability)", finding,
                        "Determines whether the top field's astrological support persists through a realistic career horizon."))
        else:
            rows.append(("Dasha Timeline (Vimshottari sustainability)", "Not available in this report context.", "—"))

        # Sudarshana
        sud = ml.get("sudarshana", {})
        if sud:
            rows.append(("Sudarshana Chakra", "; ".join(sud.get("trace", [])[:2]) or f"Score {sud.get('score',0):.1f}/100.",
                        "Tri-lagna (Lagna/Chandra/Surya) composite cross-check on the top field."))
        else:
            rows.append(("Sudarshana Chakra", "Not available in this report context.", "—"))

        # K.N. Rao
        knr = ml.get("knrao", {})
        if knr:
            rows.append(("K.N. Rao (event-timing significators)", "; ".join(knr.get("trace", [])[:2]) or f"Score {knr.get('score',0):.1f}/100.",
                        "Cross-validates significator strength using K.N. Rao's timing methodology."))
        else:
            rows.append(("K.N. Rao (event-timing significators)", "Not available in this report context.", "—"))

        # KP
        kp = ml.get("kp", {})
        if kp:
            rows.append(("KP (Krishnamurti Paddhati sub-lords)", "; ".join(kp.get("trace", [])[:2]) or f"Score {kp.get('score',0):.1f}/100.",
                        "Sub-lord level precision check, gated by birth-time confidence."))
        else:
            rows.append(("KP (Krishnamurti Paddhati sub-lords)", "Not available in this report context.", "—"))

        row_html = "".join(
            f"<tr><td style='font-weight:700;color:#1a237e;padding:6px 10px;border-bottom:1px solid #e8e8e8'>{esc(t)}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e8e8e8;font-size:.82rem'>{esc(f)}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e8e8e8;font-size:.82rem;color:#555'>{esc(i)}</td></tr>"
            for t, f, i in rows
        )
        print(f"[SECTION 2 — EVIDENCE TABLE] {len(rows)} techniques rendered; "
              f"{sum(1 for _,f,_ in rows if f.startswith('Not available'))} marked not-available-in-context.")
        return (f"<table class='sum-tbl'><thead><tr><th>Technique</th><th>Finding</th>"
                f"<th>Career/Wealth Implication</th></tr></thead><tbody>{row_html}</tbody></table>")

    @classmethod
    def _grouped_stream_html(cls, rankings: List[Dict], top_n: int, esc) -> str:
        """Spec §12 item 5 — Grouped Stream Recommendation.

        Source: 'domain' on each rankings[] row (already-computed, real
        classification — technology/engineering/medicine/etc. — used
        elsewhere in this file, e.g. _all_fields_table_html's domain
        colour map). No separate stream/domain registry
        (india_course_registry_v12.json / registry_loader_v12.py) is
        staged in this environment, so 'domain' is used as the stream
        label rather than fabricating a finer-grained stream taxonomy.
        """
        from collections import Counter
        top_rows = rankings[:top_n]
        domain_counts = Counter(r.get("domain", "unknown") for r in top_rows)
        grouped = {d: [r["field_label"] for r in top_rows if r.get("domain", "unknown") == d]
                   for d, c in domain_counts.items() if c > 1}
        if grouped:
            parts = [f"<strong>{esc(d)}</strong> ({len(fields)} fields: {esc(', '.join(fields))})"
                     for d, fields in sorted(grouped.items(), key=lambda kv: -len(kv[1]))]
            narrative = (f"{len(grouped)} stream(s) have more than one Top-{top_n} field, suggesting the chart's "
                         f"support is concentrated rather than scattered: " + "; ".join(parts) +
                         ". Prioritising these streams over single-field domains is generally lower-risk, since "
                         "multiple independent evidence signals converge on the same broad area.")
        else:
            narrative = (f"No single stream carries more than one Top-{top_n} field for this chart — the "
                         f"astrological support is spread across distinct domains rather than concentrated in "
                         f"one stream. Prioritisation should therefore be by individual field strength "
                         f"(see the ranking table) rather than by stream.")
        print(f"[SECTION 5 — GROUPED STREAM] {len(grouped)} stream(s) with >1 Top-{top_n} field: "
              f"{', '.join(grouped.keys()) if grouped else 'none'}")
        return f"<div class='ss-note' style='background:#fff;padding:12px 14px;border-radius:6px'>{narrative}</div>"

    @classmethod
    def _next_steps_html(cls, rankings: List[Dict], esc, n_fields: int = 5) -> str:
        """Spec §12 item 6 — Practical Next Steps for the top 3-5 fields.

        india_course_registry_v12.json is now staged and is consulted (via
        cls._registry_branch_meta(), reusing engine_io._load_course_registry's
        cached loader) for real per-field entrance exams / routes /
        certifications. When a top field's field_id genuinely isn't a key in
        the registry (a real coverage gap, not an error), that field alone
        falls back to the prior generic template — the rest of the section
        still renders with real registry content.
        """
        top = rankings[:max(3, min(n_fields, 5))]
        blocks = []
        registry_hits, registry_gaps = [], []
        for i, r in enumerate(top, 1):
            label = r.get("field_label", "?")
            domain = r.get("domain", "")
            meta = cls._registry_branch_meta(r.get("field_id", ""))
            if meta:
                registry_hits.append(label)
                exams = meta.get("admission_exams_canonical") or meta.get("admission_exams") or []
                exams_str = ", ".join(esc(x) for x in exams) if exams else "no canonical entrance exam listed in registry"
                routes = meta.get("routes") or {}
                safe_route = (routes.get("safe_route") or {}).get("path")
                backup_route = (routes.get("backup_route") or {}).get("path")
                career_outcomes = meta.get("career_outcomes") or {}
                cert_targets = career_outcomes.get("government_psu") or career_outcomes.get("core") or []
                portfolio_line = (
                    f"Target outcomes referenced by the registry for {esc(label)}: {esc(', '.join(cert_targets))}."
                    if cert_targets else
                    f"Seek projects, competitions, or extracurriculars in {esc(domain) or esc(label)} that demonstrate sustained interest ahead of applications."
                )
                alias_note = ""
                if meta.get("is_registry_alias"):
                    alias_note = (f"<li style='color:#8a6100'><strong>Note:</strong> course/route details for {esc(label)} are inherited "
                                   f"from the registry's '{esc(meta.get('alias_of') or meta.get('ontology_parent') or '?')}' entry, "
                                   f"not independently curated for this exact field.</li>")
                blocks.append(f"""
<div style='border:1px solid #dde1f0;border-radius:6px;padding:10px 14px;margin-bottom:8px;background:#fff'>
  <div style='font-weight:700;color:#1a237e'>{i}. {esc(label)} <span style='color:#777;font-weight:400;font-size:.8rem'>({esc(domain)})</span></div>
  <ul style='margin:6px 0 0 18px;font-size:.82rem;line-height:1.6;color:#333'>
    <li><strong>Entrance exams (registry):</strong> {exams_str}.</li>
    <li><strong>Route:</strong> {esc(safe_route) if safe_route else 'n/a'}{f' (backup: {esc(backup_route)})' if backup_route else ''}</li>
    <li><strong>Portfolio/target outcomes:</strong> {portfolio_line}</li>
    <li><strong>Certifications:</strong> Look for recognised introductory certifications or foundation courses in {esc(label)} to validate interest before committing.</li>
    {alias_note}
  </ul>
</div>""")
            else:
                registry_gaps.append(label)
                blocks.append(f"""
<div style='border:1px solid #dde1f0;border-radius:6px;padding:10px 14px;margin-bottom:8px;background:#fff'>
  <div style='font-weight:700;color:#1a237e'>{i}. {esc(label)} <span style='color:#777;font-weight:400;font-size:.8rem'>({esc(domain)})</span></div>
  <ul style='margin:6px 0 0 18px;font-size:.82rem;line-height:1.6;color:#333'>
    <li><strong>Entrance exams:</strong> Consult current entrance-exam requirements for {esc(label)} — this field is not present in the staged course registry, so this report does not source live exam data for it.</li>
    <li><strong>Portfolio/extracurricular actions:</strong> Seek projects, competitions, or extracurriculars in {esc(domain) or esc(label)} that demonstrate sustained interest ahead of applications.</li>
    <li><strong>Certifications:</strong> Look for recognised introductory certifications or foundation courses in {esc(label)} to validate interest before committing.</li>
  </ul>
</div>""")
        print(f"[SECTION 6 — NEXT STEPS] Registry-backed guidance for {len(registry_hits)}/{len(top)} field(s): "
              f"{', '.join(registry_hits) or 'none'}. Generic fallback (registry coverage gap) for: "
              f"{', '.join(registry_gaps) or 'none'}.")
        return "".join(blocks)

    @classmethod
    def _caveats_html(cls, payload, rankings: List[Dict], evidence_gaps: int, esc) -> str:
        """Spec §12 item 7 — Caveats & Confidence Notes.

        Source: payload.birth_time_precision (same signal used in the Chart
        Summary section), plus each Top-N row's own score_confidence /
        score_confidence_note (already computed in engine.py's finalize
        step), plus the count of 'not available' rows surfaced by the new
        Evidence Table (conflicting/incomplete-data signal), plus a
        hardcoded standard vocational-counseling disclaimer (spec calls for
        exactly this fixed sentence).
        """
        btp = getattr(payload, "birth_time_precision", "unknown") or "unknown"
        low_conf = [r for r in rankings if str(r.get("score_confidence", "")).upper() in ("LOW", "WEAK")]
        low_conf_str = ", ".join(r.get("field_label", "?") for r in low_conf[:5]) if low_conf else "none"

        # ── Gap B fix: confidence_dimensions (structural/educational/
        # professional/research/leadership/timing fit bands) were computed
        # per-field but never rendered anywhere. Build a compact per-field
        # "weakest dimensions" summary for the visible Top-N, plus an
        # explicit relative-vs-absolute framing note for confidence_band.
        # Missing on rows whose code path never populated the dict. ──
        dim_rows_html = ""
        dim_cli_parts = []
        DIM_LABELS = {
            "structural_fit": "Structural", "educational_fit": "Educational",
            "professional_fit": "Professional", "research_fit": "Research",
            "leadership_fit": "Leadership", "timing_fit": "Timing",
        }
        BAND_COLOR = {"VERY_LOW": "#c62828", "LOW": "#ef6c00", "MODERATE": "#f9a825",
                      "HIGH": "#2e7d32", "VERY_HIGH": "#1b5e20"}
        for r in rankings[:5]:
            cdims = r.get("confidence_dimensions") or {}
            if not cdims:
                continue
            cband = r.get("confidence_band", "n/a")
            # sort by score ascending -> weakest first
            sortable = [(k, v) for k, v in cdims.items() if isinstance(v, dict)]
            sortable.sort(key=lambda kv: kv[1].get("score", 100))
            weakest = sortable[:2]
            weakest_str = ", ".join(
                f"{DIM_LABELS.get(k, k)}={v.get('band','?')} ({v.get('score',0):.1f})"
                for k, v in weakest
            )
            all_bands_str = " &nbsp; ".join(
                f"<span style='color:{BAND_COLOR.get(v.get('band',''), '#555')};font-weight:600'>"
                f"{DIM_LABELS.get(k,k)}:{esc(str(v.get('band','?')))}</span>"
                for k, v in sortable
            )
            dim_rows_html += (
                f"<tr><td style='font-weight:700'>{esc(r.get('field_label','?'))}</td>"
                f"<td style='font-size:.78rem'>{esc(str(cband))}</td>"
                f"<td style='font-size:.76rem'>{all_bands_str}</td></tr>"
            )
            dim_cli_parts.append(f"{r.get('field_label','?')}: band={cband}, weakest: {weakest_str}")

        dims_block = ""
        if dim_rows_html:
            dims_block = f"""
  <div class='ss-note' style='background:#ffebee;border:1px solid #ef9a9a;border-radius:6px;padding:10px 12px;margin-top:10px'>
    <p style='margin:0 0 6px 0;font-size:.82rem;color:#333'>
      <strong>Relative vs. absolute confidence:</strong> the headline <code>confidence_band</code>
      shown for each field (e.g. "High (relative)") is scored <em>relative to the other candidate
      fields evaluated in this run</em> — it is NOT an absolute confidence level. A field can be
      top-ranked and still show LOW/VERY_LOW on most individual <code>confidence_dimensions</code>
      below; this is expected when the whole candidate pool is weak on a given dimension (e.g. the
      chart-wide Mercury-combustion effect already noted elsewhere in this report depresses
      educational_fit for every field, not just this one).
    </p>
    <table class='ro-table' style='width:100%'>
      <thead><tr><th>Field</th><th>confidence_band (relative)</th><th>confidence_dimensions (structural/educational/professional/research/leadership/timing)</th></tr></thead>
      <tbody>{dim_rows_html}</tbody>
    </table>
  </div>"""

        html = f"""
<div class='ss-note' style='background:#fff8e1;border:1px solid #f9a825;border-radius:6px;padding:12px 14px'>
  <ul style='margin:0 0 0 18px;line-height:1.7;font-size:.84rem;color:#333'>
    <li><strong>Birth-time reliability:</strong> recorded precision is '{esc(btp)}' — techniques sensitive to
      exact birth time (KP sub-lords, D60 Shashtiamsha) are weighted/gated accordingly (see Chart Summary above).</li>
    <li><strong>Low-confidence fields:</strong> {esc(low_conf_str)} carry a LOW/WEAK score_confidence label from
      cross-method agreement scoring — treat their ranking with extra caution.</li>
    <li><strong>Data-completeness gaps:</strong> {evidence_gaps} technique(s) in the Evidence Table above were
      marked "not available in this report context" — their absence is disclosed rather than backfilled with
      assumed findings.</li>
    <li><strong>Standard disclaimer:</strong> This report is an astrological input, not a substitute for
      standard vocational counseling — families should supplement it with a qualified vocational/career
      counselor's assessment before making final education or career decisions.</li>
  </ul>
</div>{dims_block}"""
        dims_cli = ("; confidence_dimensions (relative-band caveat): " + " | ".join(dim_cli_parts)
                    if dim_cli_parts else "; confidence_dimensions: not populated for these rows")
        print(f"[SECTION 7 — CAVEATS] birth_time_precision={btp}; low-confidence fields: {low_conf_str}; "
              f"evidence gaps disclosed: {evidence_gaps}; vocational-counseling disclaimer included"
              + dims_cli)
        return html

    @classmethod
    def export_html_full_trace(cls, rankings: List[Dict], payload, active_lord: str,
                                peak_lord: str, student_name: str,
                                top_n: int = 20,
                                output_dir: str = "educational_records") -> str:
        """Export a 3-tab HTML: Parent | Astrologer | Full Debug Trace.

        Debug Trace tab layout:
          PHASE 1 — chart-level calculations (planet strengths, dasha, yogas) — shown ONCE
          Ranking Overview — all top-N fields side-by-side comparison table
          PHASE 2 — per-field collapsible blocks (affinity weights, gaps, final chain only)
        """
        import os
        from datetime import datetime

        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp = os.path.join(output_dir, f"{student_name.lower().replace(' ','_')}_full_trace_{ts}.html")

        def esc(t):
            return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

        # ── Parent tab rows ──
        parent_rows = ""
        for rank, rec in enumerate(rankings[:top_n], 1):
            exp = cls._parent_explanation(rank, rec, payload, active_lord, peak_lord)
            llm_parent_p = cls._llm_parent_text(rec)
            llm_narr_p = cls._llm_astro_text(rec)
            narr_cell = ""
            if llm_parent_p or llm_narr_p:
                narr_cell = (
                    f'<div style="margin-top:7px;display:grid;gap:8px">'
                    f'<div style="padding:8px 12px;background:#f3e5f5;'
                    f'border-left:3px solid #7b1fa2;border-radius:0 4px 4px 0;'
                    f'font-size:.78rem;color:#4a148c;line-height:1.5">'
                    f'<strong>Parent Tone:</strong> {esc(llm_parent_p or "Not available")}</div>'
                    f'<div style="padding:8px 12px;background:#e3f2fd;'
                    f'border-left:3px solid #1565c0;border-radius:0 4px 4px 0;'
                    f'font-size:.78rem;color:#1a237e;line-height:1.5">'
                    f'<strong>Astro Tone:</strong> {esc(llm_narr_p or "Not available")}</div>'
                    f'</div>'
                )
            parent_rows += (
                f"<tr><td class='rank'>{rank}</td>"
                f"<td class='field'>{esc(rec['field_label'])}</td>"
                f"<td class='domain'>{esc(rec['domain'])}</td>"
                f"<td class='score'>{rec['final_score']:.2f}</td>"
                f"<td class='explanation'>{esc(exp)}{narr_cell}</td></tr>"
            )

        # ── Astrologer tab rows ──
        astro_rows = ""
        for rank, rec in enumerate(rankings[:top_n], 1):
            exp  = cls._astrologer_explanation(rank, rec, payload, active_lord, peak_lord)
            fmt  = "<br>".join(esc(l) for l in exp.split("\n"))
            llm_parent_a = cls._llm_parent_text(rec)
            llm_narr_a = cls._llm_astro_text(rec)
            llm_score_a = rec.get("llm_score")
            narr_cell_a = ""
            if llm_parent_a or llm_narr_a:
                badge = (f' &nbsp;<span style="background:#1565c0;color:#fff;font-size:.68rem;'
                         f'padding:1px 6px;border-radius:8px">LLM {llm_score_a:.0f}</span>'
                         if llm_score_a is not None else "")
                narr_cell_a = (
                    f'<div style="margin-top:8px;display:grid;gap:8px">'
                    f'<div style="padding:9px 12px;background:#f3e5f5;'
                    f'border-left:3px solid #7b1fa2;border-radius:0 5px 5px 0;'
                    f'font-size:.79rem;color:#4a148c;line-height:1.6">'
                    f'<span style="font-weight:700;color:#7b1fa2;font-size:.7rem;'
                    f'letter-spacing:.06em">◌ PARENT TONE</span><br>'
                    f'{esc(llm_parent_a or "Not available")}</div>'
                    f'<div style="padding:9px 12px;background:#e8f4fd;'
                    f'border-left:3px solid #1565c0;border-radius:0 5px 5px 0;'
                    f'font-size:.79rem;color:#1a1a2e;line-height:1.6">'
                    f'<span style="font-weight:700;color:#1565c0;font-size:.7rem;'
                    f'letter-spacing:.06em">⊙ ASTRO TONE{badge}</span><br>'
                    f'{esc(llm_narr_a or "Not available")}</div>'
                    f'</div>'
                )
            astro_rows += (
                f"<tr><td class='rank'>{rank}</td>"
                f"<td class='field'>{esc(rec['field_label'])}</td>"
                f"<td class='domain'>{esc(rec['domain'])}</td>"
                f"<td class='score'>{rec['final_score']:.2f}</td>"
                f"<td class='explanation astro-text'>{fmt}{narr_cell_a}</td></tr>"
            )

        # ── Trace tab ──
        # Phase 1: pull planet_trace from any result (same for all — computed once)
        _ct0        = rankings[0].get("calc_trace", {}) if rankings else {}
        _pt0        = _ct0.get("planet_trace", {})
        _karakas0   = _ct0.get("karakas", {})
        _aspects0   = _ct0.get("aspects_on_h10", [])
        _yogas0     = getattr(payload, "detected_yogas", []) or getattr(payload, "yogas_present", [])

        _edu_reasons0  = _ct0.get("edu_planet_reasons", {})
        _edu_effs0     = _ct0.get("edu_eff_strengths", {})
        phase1_html    = cls._phase1_html(_pt0, active_lord, peak_lord, _karakas0, _aspects0, _yogas0,
                                           _edu_reasons0, _edu_effs0, esc)
        ranking_table  = cls._ranking_overview_html(rankings, top_n, esc)

        trace_blocks = ""
        for rank, rec in enumerate(rankings[:top_n], 1):
            trace_blocks += cls._field_trace_html_block(rank, rec, esc)

        # ── All-fields scores table ────────────────────────────────────────────
        all_fields_tbl  = cls._all_fields_table_html(rankings, esc)

        # ── Spec §12 sections: 1 Chart Summary, 2 Evidence Table, 5 Grouped
        # Stream, 6 Next Steps, 7 Caveats. (Section 3 raw-vs-adjusted
        # planetary strength stays as the existing print()-only block below;
        # section 4 Top-N extension is already inside ranking_table above.)
        chart_summary_html = cls._chart_summary_html(payload, rankings, esc)
        evidence_table_html = cls._evidence_table_html(rankings, _pt0, esc)
        _evidence_gap_count = evidence_table_html.count("Not available in this report context")
        grouped_stream_html = cls._grouped_stream_html(rankings, top_n, esc)
        next_steps_html = cls._next_steps_html(rankings, esc)
        caveats_html = cls._caveats_html(payload, rankings, _evidence_gap_count, esc)

        gen_date = datetime.now().strftime("%d %b %Y, %H:%M")
        name_str = esc(student_name)
        n_shown  = min(top_n, len(rankings))

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>JyotishAI Full Trace — {name_str}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f9;color:#222;font-size:13px}}
header{{background:linear-gradient(135deg,#1a237e,#4a148c);color:#fff;padding:18px 32px}}
header h1{{font-size:1.3rem;letter-spacing:.03em}}
header p{{margin-top:5px;opacity:.85;font-size:.83rem}}
.tabs{{display:flex;background:#fff;border-bottom:2px solid #e0e0e0;padding:0 32px}}
.tab-btn{{padding:12px 26px;cursor:pointer;font-size:.9rem;font-weight:600;border:none;background:none;color:#555;border-bottom:3px solid transparent;margin-bottom:-2px;transition:color .15s,border-color .15s}}
.tab-btn:hover{{color:#1a237e}}
.tab-btn.active{{color:#1a237e;border-bottom-color:#1a237e}}
.tab-panel{{display:none;padding:22px 32px}}
.tab-panel.active{{display:block}}
.panel-title{{font-size:.95rem;font-weight:700;color:#1a237e;margin-bottom:14px}}

/* Summary tables */
table.sum-tbl{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.09)}}
table.sum-tbl thead tr{{background:#1a237e;color:#fff}}
table.sum-tbl th{{padding:9px 12px;text-align:left;font-size:.74rem;letter-spacing:.05em;text-transform:uppercase;white-space:nowrap}}
table.sum-tbl td{{padding:9px 12px;vertical-align:top;border-bottom:1px solid #e8e8e8;line-height:1.55}}
table.sum-tbl tr:last-child td{{border-bottom:none}}
table.sum-tbl tr:nth-child(even){{background:#f7f8fc}}
table.sum-tbl tr:hover{{background:#eef2ff}}
td.rank{{font-weight:700;color:#1a237e;text-align:center;width:38px}}
td.score{{font-weight:700;color:#6a1b9a;text-align:center;width:58px}}
td.field{{font-weight:600;width:180px}}
td.domain{{color:#555;width:110px;text-transform:capitalize}}
td.explanation{{max-width:680px}}
td.astro-text{{font-family:'Consolas','Courier New',monospace;font-size:.78rem;color:#1a1a2e;line-height:1.6}}

/* Phase 1 block */
.phase1-block{{background:#e8eaf6;border:2px solid #3949ab;border-radius:8px;padding:14px 18px;margin-bottom:18px}}
.phase1-hdr{{font-size:.95rem;font-weight:700;color:#1a237e;margin-bottom:10px;letter-spacing:.02em}}
.phase1-meta{{display:flex;flex-wrap:wrap;gap:18px;font-size:.83rem;margin-bottom:8px}}
.phase1-meta span{{background:#fff;padding:3px 10px;border-radius:4px;border:1px solid #c5cae9}}
.phase1-rank{{font-size:.79rem;color:#333;margin-top:6px;line-height:1.6}}
.rank-chain{{font-family:'Consolas',monospace;font-size:.78rem;color:#1a237e}}
.phase2-hdr{{font-size:.92rem;font-weight:700;color:#1a237e;margin:18px 0 6px;padding:10px 14px;background:#e3e7f8;border-radius:6px}}
.phase2-sub{{font-size:.83rem;color:#555;margin:8px 0 6px}}

/* Ranking overview table */
table.ro-table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.09);margin-bottom:6px}}
table.ro-table thead tr{{background:#283593;color:#fff}}
table.ro-table th{{padding:7px 10px;text-align:left;font-size:.73rem;letter-spacing:.05em;text-transform:uppercase;white-space:nowrap;cursor:help}}
table.ro-table td{{padding:6px 10px;border-bottom:1px solid #e8e8e8;font-size:.82rem}}
table.ro-table tr:hover{{background:#eef2ff!important}}
.ro-rank{{font-weight:700;color:#1a237e;text-align:center;width:32px}}
.ro-label{{font-weight:600;width:200px}}
.ro-dom{{color:#555;font-size:.78rem;width:110px}}
.ro-num{{font-family:'Consolas',monospace;text-align:right;width:70px}}
.ro-score{{font-weight:700;color:#6a1b9a;text-align:right;width:60px}}

/* Field block summary extras */
.fb-top3{{color:#555;font-size:.77rem;flex:1;text-align:right}}

/* Trace tab */
.field-block{{background:#fff;border:1px solid #dde1f0;border-radius:8px;margin-bottom:14px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.field-summary{{padding:12px 18px;cursor:pointer;display:flex;align-items:center;gap:12px;background:#f0f2fb;font-size:.88rem;list-style:none;user-select:none}}
.field-summary:hover{{background:#e3e7f8}}
.fb-rank{{font-weight:700;color:#1a237e;min-width:28px}}
.fb-label{{font-weight:700;flex:1}}
.fb-domain{{color:#555;font-size:.8rem}}
.fb-score{{font-weight:700;color:#6a1b9a;font-size:.88rem}}
.fb-src{{color:#777;font-size:.78rem}}
.field-body{{padding:16px 18px;display:flex;flex-direction:column;gap:14px}}

.sub-section{{border:1px solid #e0e4f0;border-radius:6px;overflow:hidden}}
.ss-hdr{{padding:8px 14px;cursor:pointer;background:#eef0fa;font-weight:600;font-size:.83rem;color:#1a237e;list-style:none;user-select:none}}
.ss-hdr:hover{{background:#e2e6f5}}
.ss-body{{padding:12px 14px;overflow-x:auto}}
.ss-note{{font-size:.78rem;color:#555;margin:6px 0}}

.trace-section{{background:#f9f9fe;border:1px solid #e0e4f0;border-radius:6px;padding:8px 14px}}
.ts-hdr{{font-size:.82rem;color:#333}}

/* Planet table */
table.planet-table{{width:100%;border-collapse:collapse;font-size:.76rem;min-width:900px}}
table.planet-table th{{background:#283593;color:#fff;padding:5px 8px;text-align:center;font-size:.72rem;white-space:nowrap}}
table.planet-table td{{padding:4px 8px;border-bottom:1px solid #e8e8e8;text-align:center;vertical-align:top}}
table.planet-table small{{color:#666;font-size:.7rem;display:block}}
.pt-planet{{font-weight:700;text-align:left!important}}
.pt-val{{text-align:left!important}}
.pt-ratio{{font-weight:600;color:#283593}}
.pt-dig{{font-style:italic;font-size:.75rem}}
.pt-mod{{color:#555}}
.pt-eff{{font-weight:700;color:#1b5e20;background:#e8f5e9}}
.eff-hdr{{background:#1b5e20!important}}
tr.tr-strong td.pt-eff{{color:#1b5e20}}
tr.tr-weak  td.pt-eff{{color:#b71c1c;background:#ffebee}}
tr.tr-mid   td.pt-eff{{color:#e65100;background:#fff3e0}}

/* Chain table */
table.chain-table{{width:100%;border-collapse:collapse;font-size:.82rem}}
table.chain-table th{{background:#4a148c;color:#fff;padding:6px 10px;text-align:left;font-size:.76rem}}
table.chain-table td{{padding:5px 10px;border-bottom:1px solid #eee;vertical-align:top}}
.chain-step{{font-weight:600;width:220px}}
.chain-val{{font-weight:700;color:#4a148c;width:80px;font-family:'Consolas',monospace}}
.chain-note-td{{color:#555;font-size:.78rem}}
.mult-grn{{color:#2e7d32;font-weight:600}}
.mult-red{{color:#c62828;font-weight:600}}
.mult-neu{{color:#555}}

/* Gap table */
table.gap-table{{width:100%;border-collapse:collapse;font-size:.80rem}}
table.gap-table th{{background:#37474f;color:#fff;padding:5px 10px;text-align:left;font-size:.74rem}}
table.gap-table td{{padding:4px 10px;border-bottom:1px solid #eee}}
.gap-key{{font-family:'Consolas',monospace;font-size:.76rem;width:200px}}
.gap-label{{color:#333}}
.gap-pos{{font-weight:700;color:#2e7d32;text-align:right;width:70px}}
.gap-neg{{font-weight:700;color:#c62828;text-align:right;width:70px}}

/* Affinity table */
table.aff-table{{width:100%;border-collapse:collapse;font-size:.80rem}}
table.aff-table th{{background:#006064;color:#fff;padding:5px 10px;text-align:left;font-size:.74rem}}
table.aff-table td{{padding:4px 10px;border-bottom:1px solid #eee}}
.aff-planet{{font-weight:700;width:90px}}
.aff-val{{font-family:'Consolas',monospace;text-align:right;width:90px}}
.aff-contrib{{font-weight:700;color:#006064;text-align:right;width:100px}}
</style>
</head>
<body>
<header>
  <h1>JyotishAI Full Calculation Trace — {name_str}</h1>
  <p>Engine: {ENGINE_VERSION} &bull; Generated: {gen_date} &bull; Top {n_shown} fields &bull; Active MD: {esc(active_lord or 'N/A')} &bull; Peak MD: {esc(peak_lord or 'N/A')}</p>
</header>
<div class="tabs">
  <button class="tab-btn active" onclick="showTab('parent',this)">Parent Explanations</button>
  <button class="tab-btn" onclick="showTab('astro',this)">Astrological Explanations</button>
  <button class="tab-btn" onclick="showTab('scores',this)">All Fields &amp; Scores</button>
  <button class="tab-btn" onclick="showTab('trace',this)">Full Calculation Trace</button>
</div>

<div id="panel-parent" class="tab-panel active">
  <p class="panel-title">Plain-language career guidance — for parents and students</p>
  <table class="sum-tbl">
    <thead><tr><th>#</th><th>Field</th><th>Domain</th><th>Score</th><th>Explanation</th></tr></thead>
    <tbody>{parent_rows}</tbody>
  </table>
</div>

<div id="panel-astro" class="tab-panel">
  <p class="panel-title">Technical astrological analysis — for Jyotish practitioners</p>
  <table class="sum-tbl">
    <thead><tr><th>#</th><th>Field</th><th>Domain</th><th>Score</th><th>Planetary Analysis</th></tr></thead>
    <tbody>{astro_rows}</tbody>
  </table>
</div>

<div id="panel-scores" class="tab-panel">
  <p class="panel-title">All {n_shown} fields — Engine %, LLM %, method scores, and per-field narrative</p>
  {all_fields_tbl}
</div>

<div id="panel-trace" class="tab-panel">
  <p class="panel-title">Two-phase architecture: Phase 1 computed once for the chart, Phase 2 applied per branch.</p>
  {chart_summary_html}
  <div class='phase2-hdr'>SECTION 2 — Evidence Table (technique-first)</div>
  {evidence_table_html}
  {phase1_html}
  <div class='phase2-hdr'>PHASE 2 — Per-Branch Scoring (affinity weighting applied to Phase 1 strengths)</div>
  <div class='phase2-sub'>Ranking overview — all {n_shown} fields compared side-by-side (Section 4: incl. Recommended Stream / Peak Dasha Window / Wealth Note / Risk-Caveat)</div>
  {ranking_table}
  <div class='phase2-hdr'>SECTION 5 — Grouped Stream Recommendation</div>
  {grouped_stream_html}
  <div class='phase2-hdr'>SECTION 6 — Practical Next Steps (Top fields)</div>
  {next_steps_html}
  <div class='phase2-hdr'>SECTION 7 — Caveats &amp; Confidence Notes</div>
  {caveats_html}
  <div class='phase2-sub' style='margin-top:18px'>Detailed trace per field — click to expand</div>
  {trace_blocks}
</div>

<script>
function showTab(name,btn){{
  document.querySelectorAll('.tab-panel').forEach(function(el){{el.classList.remove('active')}});
  document.querySelectorAll('.tab-btn').forEach(function(el){{el.classList.remove('active')}});
  document.getElementById('panel-'+name).classList.add('active');
  btn.classList.add('active');
}}
var _sortDir={{}};
function sortTbl(col){{
  var tb=document.getElementById("all-fields-tbody");
  if(!tb)return;
  var rows=Array.from(tb.rows);
  var asc=!_sortDir[col]; _sortDir[col]=asc;
  rows.sort(function(a,b){{
    var av=a.cells[col]?a.cells[col].innerText.replace("%","").trim():"";
    var bv=b.cells[col]?b.cells[col].innerText.replace("%","").trim():"";
    var an=parseFloat(av),bn=parseFloat(bv);
    if(!isNaN(an)&&!isNaN(bn))return asc?an-bn:bn-an;
    return asc?av.localeCompare(bv):bv.localeCompare(av);
  }});
  rows.forEach(function(r){{tb.appendChild(r)}});
}}
</script>
</body>
</html>"""

        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(html)
        logger.info(f"Full trace HTML exported --> {fp}")

        # ── FINAL REPORT ASSEMBLY: planetary-strength ranking + narrative ──
        # export_html_full_trace() is the true "last mile" top-level function:
        # it is the only place in the pipeline that consumes rankings + payload
        # + active_lord/peak_lord together and assembles the complete published
        # report (Parent / Astrologer / Debug Trace tabs) to a single output file.
        # Section 3 of the spec ("final composite planetary-strength ranking,
        # raw base strength AND fully adjusted strength side by side") is printed
        # here from _pt0 (planet_trace), which is computed once per chart and is
        # already available in scope — raw_shadbala/min_v give the raw base ratio,
        # eff_strength gives the fully-adjusted value. Printed unconditionally,
        # matching the print() convention used elsewhere in this pipeline
        # (e.g. astro.py's "Final planetary strengths" block).
        print("\n[FINAL REPORT] Composite planetary-strength ranking (raw base vs fully adjusted):")
        print(f"  {'Planet':<8} {'Raw Base (shadbala/min)':>24} {'Adjusted (eff_strength)':>26}")
        _ranked_planets = sorted(_pt0.items(), key=lambda kv: -kv[1].get("eff_strength", 0.0)) if _pt0 else []
        for _pname, _pt in _ranked_planets:
            _raw_base = _pt.get("raw_ratio", (_pt.get("raw_shadbala", 0.0) / _pt.get("min_v", 1.0)) if _pt.get("min_v") else 0.0)
            print(f"  {_pname:<8} {_raw_base:>24.4f} {_pt.get('eff_strength', 0.0):>26.4f}")

        _n_top = len(rankings[:top_n])
        _top_rec = rankings[0] if rankings else {}
        _top_ct = _top_rec.get("calc_trace", {})
        _top_boosts = _top_ct.get("gap_boosts", {}) or {}
        _top_pens = _top_ct.get("gap_penalties", {}) or {}
        _dom_evidence = max(_top_boosts.items(), key=lambda kv: kv[1])[0] if _top_boosts else None
        _dom_evidence_label = cls._GAP_BOOST_LABELS.get(_dom_evidence, _dom_evidence) if _dom_evidence else "no single dominant boost"
        _hard_lockouts = [r.get("field_label", r.get("field_id", "?")) for r in rankings[:top_n] if r.get("hard_lockout")]
        _dasha_downranks = [r.get("field_label", r.get("field_id", "?")) for r in rankings[:top_n]
                             if any("dasha" in str(k).lower() and v < 0 for k, v in (r.get("calc_trace", {}).get("gap_penalties", {}) or {}).items())]
        _strongest_planet = _ranked_planets[0][0] if _ranked_planets else "?"
        _strongest_val = _ranked_planets[0][1].get("eff_strength", 0.0) if _ranked_planets else 0.0
        _report_narrative = (
            f"[FINAL REPORT NARRATIVE] For {student_name}, {_n_top} field(s) made the Top-{top_n} list out of "
            f"{len(rankings)} evaluated. The top result, '{_top_rec.get('field_label', '?')}' "
            f"(score {_top_rec.get('final_score', 0):.2f}), was most influenced by "
            f"'{_dom_evidence_label}' among its fired evidence signals, with active dasha lord {active_lord or '?'} "
            f"and peak career MD {peak_lord or '?'} as the chart's dasha context. "
            + (f"{len(_hard_lockouts)} field(s) in the Top-{top_n} carried a hard-lockout flag ({', '.join(_hard_lockouts)}). "
               if _hard_lockouts else "No Top-N field carried a hard-lockout exclusion flag. ")
            + (f"{len(_dasha_downranks)} field(s) showed a dasha-related downrank penalty ({', '.join(_dasha_downranks)}). "
               if _dasha_downranks else "No Top-N field showed a dasha-related downrank penalty. ")
            + f"Overall, the chart's single strongest astrological signal is {_strongest_planet} at "
            f"eff_strength={_strongest_val:.2f}, the dominant planetary driver behind this report's rankings."
        )
        print(_report_narrative)

        return fp

    @classmethod
    def export_html(cls, explanations, student_name, output_dir="educational_records"):
        """Export career explanations as a two-tab HTML file with tabular layout."""
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp = os.path.join(
            output_dir,
            f"{student_name.lower().replace(' ', '_')}_explanations_{ts}.html"
        )

        def _esc(text):
            return (str(text)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;"))

        # Build parent rows
        parent_rows = ""
        for ex in explanations:
            payload_block = ""
            payload = ex.get("llm_payload", {}) or {}
            if payload:
                try:
                    payload_text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
                except Exception:
                    payload_text = str(payload)
                payload_block = (
                    "<details style='margin-top:8px;border:1px solid #dfe3ec;border-radius:6px;background:#fbfcff'>"
                    "<summary style='cursor:pointer;padding:8px 10px;font-size:.78rem;font-weight:700;color:#1a237e;list-style:none'>LLM JSON Payload</summary>"
                    f"<div style='padding:10px 12px;border-top:1px solid #e7ebf5'><pre style='margin:0;font-family:Consolas,\"Courier New\",monospace;font-size:.76rem;line-height:1.5;white-space:pre-wrap;word-break:break-word;background:#0b1020;color:#dbe4ff;padding:10px;border-radius:6px'>{_esc(payload_text)}</pre></div>"
                    "</details>"
                )
            parent_rows += (
                "\n            <tr>"
                f"\n              <td class='rank'>{ex['rank']}</td>"
                f"\n              <td class='field'>{_esc(ex['field'])}</td>"
                f"\n              <td class='domain'>{_esc(ex['domain'])}</td>"
                f"\n              <td class='score'>{ex['final_score']:.2f}</td>"
                f"\n              <td class='explanation'>{_esc(ex['parent'])}{payload_block}</td>"
                "\n            </tr>"
            )

        # Build astrologer rows
        astro_rows = ""
        for ex in explanations:
            lines = ex['astrologer'].split('\n')
            formatted = '<br>'.join(_esc(l) for l in lines)
            payload_block = ""
            payload = ex.get("llm_payload", {}) or {}
            if payload:
                try:
                    payload_text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
                except Exception:
                    payload_text = str(payload)
                payload_block = (
                    "<details style='margin-top:8px;border:1px solid #dfe3ec;border-radius:6px;background:#fbfcff'>"
                    "<summary style='cursor:pointer;padding:8px 10px;font-size:.78rem;font-weight:700;color:#1a237e;list-style:none'>LLM JSON Payload</summary>"
                    f"<div style='padding:10px 12px;border-top:1px solid #e7ebf5'><pre style='margin:0;font-family:Consolas,\"Courier New\",monospace;font-size:.76rem;line-height:1.5;white-space:pre-wrap;word-break:break-word;background:#0b1020;color:#dbe4ff;padding:10px;border-radius:6px'>{_esc(payload_text)}</pre></div>"
                    "</details>"
                )
            astro_rows += (
                "\n            <tr>"
                f"\n              <td class='rank'>{ex['rank']}</td>"
                f"\n              <td class='field'>{_esc(ex['field'])}</td>"
                f"\n              <td class='domain'>{_esc(ex['domain'])}</td>"
                f"\n              <td class='score'>{ex['final_score']:.2f}</td>"
                f"\n              <td class='explanation astro-text'>{formatted}{payload_block}</td>"
                "\n            </tr>"
            )

        gen_date = datetime.now().strftime("%d %b %Y, %H:%M")
        n_fields = len(explanations)
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JyotishAI Career Report - {_esc(student_name)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #222; }}
  header {{ background: linear-gradient(135deg, #1a237e 0%, #4a148c 100%); color: #fff; padding: 22px 36px; }}
  header h1 {{ font-size: 1.5rem; letter-spacing: 0.03em; }}
  header p  {{ margin-top: 6px; opacity: 0.85; font-size: 0.88rem; }}
  .tabs {{ display: flex; background: #fff; border-bottom: 2px solid #e0e0e0; padding: 0 36px; }}
  .tab-btn {{ padding: 14px 30px; cursor: pointer; font-size: 0.97rem; font-weight: 600; border: none; background: none; color: #555; border-bottom: 3px solid transparent; margin-bottom: -2px; transition: color 0.15s, border-color 0.15s; }}
  .tab-btn:hover  {{ color: #1a237e; }}
  .tab-btn.active {{ color: #1a237e; border-bottom-color: #1a237e; }}
  .tab-panel {{ display: none; padding: 28px 36px; }}
  .tab-panel.active {{ display: block; }}
  .panel-title {{ font-size: 1.05rem; font-weight: 700; color: #1a237e; margin-bottom: 16px; letter-spacing: 0.02em; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 5px rgba(0,0,0,0.09); }}
  thead tr {{ background: #1a237e; color: #fff; }}
  th {{ padding: 11px 14px; text-align: left; font-size: 0.80rem; letter-spacing: 0.06em; text-transform: uppercase; white-space: nowrap; }}
  td {{ padding: 11px 14px; vertical-align: top; border-bottom: 1px solid #e8e8e8; font-size: 0.92rem; line-height: 1.6; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:nth-child(even) {{ background: #f7f8fc; }}
  tr:hover {{ background: #eef2ff; }}
  td.rank   {{ font-weight: 700; color: #1a237e; text-align: center; width: 46px; }}
  td.score  {{ font-weight: 700; color: #6a1b9a; text-align: center; width: 64px; }}
  td.field  {{ font-weight: 600; width: 190px; }}
  td.domain {{ color: #555; width: 120px; text-transform: capitalize; }}
  td.explanation {{ max-width: 680px; }}
  td.astro-text {{ font-family: 'Consolas', 'Courier New', monospace; font-size: 0.83rem; color: #1a1a2e; line-height: 1.65; }}
</style>
</head>
<body>
<header>
  <h1>JyotishAI Career Field Explainability Report</h1>
  <p>Student: <strong>{_esc(student_name)}</strong> &bull; Generated: {gen_date} &bull; Engine: {ENGINE_VERSION}</p>
</header>
<nav class="tabs">
  <button class="tab-btn active" onclick="showTab('parent',this)">Parent View</button>
  <button class="tab-btn"        onclick="showTab('astro',this)">Astrologer View</button>
</nav>
<div id="parent" class="tab-panel active">
  <p class="panel-title">Career Field Recommendations — {n_fields} fields analysed</p>
  <table>
    <thead><tr>
      <th>Rank</th><th>Field</th><th>Domain</th><th>Score</th><th>Explanation (Parent)</th>
    </tr></thead>
    <tbody>{parent_rows}</tbody>
  </table>
</div>
<div id="astro" class="tab-panel">
  <p class="panel-title">Astrological Technical View</p>
  <table>
    <thead><tr>
      <th>Rank</th><th>Field</th><th>Domain</th><th>Score</th><th>Explanation (Astrologer)</th>
    </tr></thead>
    <tbody>{astro_rows}</tbody>
  </table>
</div>
<script>
function showTab(id, btn) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}}
</script>
</body>
</html>"""
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(html)
        return fp
