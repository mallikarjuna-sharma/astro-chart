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

_DIGNITY_PARENT: Dict[str, str] = {
    "EXALTED":       "this planet is at peak strength (exalted)",
    "OWN":           "this planet is in its own sign, giving it natural strength",
    "DEBILITATED":   "this planet faces challenges but can still contribute",
    "NEECHA_BHANGA": "a cancellation of debility makes this planet resilient",
}

_DIGNITY_ASTRO: Dict[str, str] = {
    "EXALTED":       "uccha (exalted)",
    "OWN":           "swa (own sign)",
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
        return sorted(rec["top_affinity_planets"].items(), key=lambda x: -x[1])[:n]

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
            dig_str = f" -- {_DIGNITY_PARENT[dig1]}" if dig1 else ""
            lines.append(f"{p1}{role_str} is the strongest planet for this field ({_PLANET_TRAIT_PARENT.get(p1,'broad capability')}){dig_str}.")

        # Append LLM-generated astrological reasoning when present
        llm_reason = rec.get("llm_astrological_reason", "").strip()
        if llm_reason:
            lines.append(f"Astrological basis: {llm_reason}")

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
        llm_reason = rec.get("llm_astrological_reason", "").strip()
        if llm_reason:
            lines.append(f"  [LLM] {llm_reason}")

        return "\n".join(lines)

    @classmethod
    def generate(cls, rankings, payload, active_lord, peak_lord, top_n=15):
        # Top-level LLM rationale comes from the first ranked result (same value on all)
        selection_rationale = rankings[0].get("llm_selection_rationale", "") if rankings else ""
        output = []
        for rank, rec in enumerate(rankings[:top_n], 1):
            output.append({
                "rank":                     rank,
                "field":                    rec["field_label"],
                "domain":                   rec["domain"],
                "final_score":              round(rec["final_score"], 2),
                "parent":                   cls._parent_explanation(rank, rec, payload, active_lord, peak_lord),
                "astrologer":               cls._astrologer_explanation(rank, rec, payload, active_lord, peak_lord),
                "llm_astrological_reason":  rec.get("llm_astrological_reason", ""),
                "llm_selection_rationale":  selection_rationale,
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
        """Render the full score computation chain as step-by-step HTML."""
        n = ct["normalization"]
        fc = ct["final_chain"]
        def fmt_mult(v, note):
            cls2 = "mult-red" if v < 1 else ("mult-grn" if v > 1 else "mult-neu")
            return f"<span class='{cls2}'>×{v:.3f}</span> <span class='chain-note'>{note}</span>"

        rows = [
            ("Composite Score (raw)",     f"{n['composite_score_raw']:.4f}",  "domain aptitude: shadbala + SAV + eff_strength blend"),
            ("Composite Score (norm)",    f"{n['composite_norm']:.4f}",        "log-norm (soft-cap 200, max ~115)"),
            ("Affinity Score (raw)",      f"{n['affinity_score_raw']:.4f}",    "Σ(planet_weight × eff_strength) × 100"),
            ("Affinity Score (norm)",     f"{n['affinity_norm']:.4f}",         "log-norm (soft-cap 180, max ~115)"),
            ("Blended Score",             f"{n['blended']:.4f}",               f"{n['domain_blend_weight']}×composite_norm + {n['affinity_blend_weight']}×affinity_norm"),
            ("After Gap Boost",           f"{fc['after_boost']:.4f}",          f"×(1 + {ct['gap_boost_total']:.4f}) gap_boost"),
            ("After Gap Penalty",         f"{fc['after_penalty']:.4f}",        f"×(1 − {abs(ct['gap_penalty_total']):.4f}) gap_penalty"),
            ("After Threshold Gate",      f"{fc['after_penalty']*fc['threshold_mult']:.4f}", fc['threshold_note']),
            ("After Mismatch Gate",       f"{fc['after_penalty']*fc['threshold_mult']*fc['mismatch_mult']:.4f}", fc['mismatch_note']),
            ("After Friction (QA)",       f"{fc['after_penalty']*fc['threshold_mult']*fc['mismatch_mult']*fc['friction_mult']:.4f}", f"friction_mult={fc['friction_mult']:.3f} | {fc['friction_note'][:60]}"),
            ("FINAL SCORE",               f"{fc['final_score']:.4f}",          fc['qa_gate_note']),
        ]
        trs = ""
        for step, val, note in rows:
            bold = " style='font-weight:700;background:#eef2ff'" if step == "FINAL SCORE" else ""
            trs += f"<tr{bold}><td class='chain-step'>{step}</td><td class='chain-val'>{val}</td><td class='chain-note-td'>{note}</td></tr>"
        return f"<table class='chain-table'><thead><tr><th>Step</th><th>Value</th><th>Note</th></tr></thead><tbody>{trs}</tbody></table>"

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
      </div>
    </details>

  </div>
</details>"""

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
                f"<td class='ro-score'>{rec['final_score']:.2f}</td>"
                f"</tr>"
            )
        return (
            f"<table class='ro-table'>"
            f"<thead><tr>"
            f"<th>#</th><th>Field</th><th>Domain</th>"
            f"<th title='Composite aptitude score normalised 0-100'>Comp/100</th>"
            f"<th title='Branch affinity score normalised 0-100'>Aff/100</th>"
            f"<th title='0.60×Comp + 0.40×Aff'>Blended</th>"
            f"<th title='Net gap boost+penalty applied'>Gap%</th>"
            f"<th title='Threshold / Mismatch / QA gates'>Gates</th>"
            f"<th>Score</th>"
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
            parent_rows += (
                f"<tr><td class='rank'>{rank}</td>"
                f"<td class='field'>{esc(rec['field_label'])}</td>"
                f"<td class='domain'>{esc(rec['domain'])}</td>"
                f"<td class='score'>{rec['final_score']:.2f}</td>"
                f"<td class='explanation'>{esc(exp)}</td></tr>"
            )

        # ── Astrologer tab rows ──
        astro_rows = ""
        for rank, rec in enumerate(rankings[:top_n], 1):
            exp  = cls._astrologer_explanation(rank, rec, payload, active_lord, peak_lord)
            fmt  = "<br>".join(esc(l) for l in exp.split("\n"))
            astro_rows += (
                f"<tr><td class='rank'>{rank}</td>"
                f"<td class='field'>{esc(rec['field_label'])}</td>"
                f"<td class='domain'>{esc(rec['domain'])}</td>"
                f"<td class='score'>{rec['final_score']:.2f}</td>"
                f"<td class='explanation astro-text'>{fmt}</td></tr>"
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

<div id="panel-trace" class="tab-panel">
  <p class="panel-title">Two-phase architecture: Phase 1 computed once for the chart, Phase 2 applied per branch.</p>
  {phase1_html}
  <div class='phase2-hdr'>PHASE 2 — Per-Branch Scoring (affinity weighting applied to Phase 1 strengths)</div>
  <div class='phase2-sub'>Ranking overview — all {n_shown} fields compared side-by-side</div>
  {ranking_table}
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
</script>
</body>
</html>"""

        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(html)
        logger.info(f"Full trace HTML exported --> {fp}")
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
            parent_rows += (
                "\n            <tr>"
                f"\n              <td class='rank'>{ex['rank']}</td>"
                f"\n              <td class='field'>{_esc(ex['field'])}</td>"
                f"\n              <td class='domain'>{_esc(ex['domain'])}</td>"
                f"\n              <td class='score'>{ex['final_score']:.2f}</td>"
                f"\n              <td class='explanation'>{_esc(ex['parent'])}</td>"
                "\n            </tr>"
            )

        # Build astrologer rows
        astro_rows = ""
        for ex in explanations:
            lines = ex['astrologer'].split('\n')
            formatted = '<br>'.join(_esc(l) for l in lines)
            astro_rows += (
                "\n            <tr>"
                f"\n              <td class='rank'>{ex['rank']}</td>"
                f"\n              <td class='field'>{_esc(ex['field'])}</td>"
                f"\n              <td class='domain'>{_esc(ex['domain'])}</td>"
                f"\n              <td class='score'>{ex['final_score']:.2f}</td>"
                f"\n              <td class='explanation astro-text'>{formatted}</td>"
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
  <p>Student: <strong>{_esc(student_name)}</strong> &bull; Generated: {gen_date} &bull; Engine: {ENGINE_VERSION} &bull; Top {n_fields} fields shown</p>
</header>
<div class="tabs">
  <button class="tab-btn active" onclick="showTab('parent', this)">Parent Explanations</button>
  <button class="tab-btn" onclick="showTab('astro', this)">Astrological Explanations</button>
</div>
<div id="panel-parent" class="tab-panel active">
  <p class="panel-title">Plain-language career guidance &mdash; for parents and students</p>
  <table>
    <thead>
      <tr><th>#</th><th>Field</th><th>Domain</th><th>Score</th><th>Explanation</th></tr>
    </thead>
    <tbody>{parent_rows}</tbody>
  </table>
</div>
<div id="panel-astro" class="tab-panel">
  <p class="panel-title">Technical astrological analysis &mdash; for Jyotish practitioners</p>
  <table>
    <thead>
      <tr><th>#</th><th>Field</th><th>Domain</th><th>Score</th><th>Planetary Analysis</th></tr>
    </thead>
    <tbody>{astro_rows}</tbody>
  </table>
</div>
<script>
function showTab(name, btn) {{
  document.querySelectorAll('.tab-panel').forEach(function(el) {{ el.classList.remove('active'); }});
  document.querySelectorAll('.tab-btn').forEach(function(el) {{ el.classList.remove('active'); }});
  document.getElementById('panel-' + name).classList.add('active');
  btn.classList.add('active');
}}
</script>
</body>
</html>"""

        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(html)
        logger.info(f"HTML explanations exported --> {fp}")
        return fp

    @classmethod
    def print_console(cls, explanations):
        import textwrap
        print("\n" + "="*120)
        print("  CAREER FIELD EXPLAINABILITY REPORT")
        print("="*120)
        for ex in explanations:
            print(f"\n{'--'*60}")
            print(f"  Rank #{ex['rank']}  |  {ex['field'].upper()}  |  "
                  f"Score {ex['final_score']:.2f}  |  Domain: {ex['domain'].upper()}")
            print(f"{'--'*60}")
            print("\n  -- FOR PARENTS --")
            for line in textwrap.wrap(ex["parent"], width=110, initial_indent="  ", subsequent_indent="  "):
                print(line)
            print("\n  -- FOR ASTROLOGERS --")
            for line in ex["astrologer"].split("\n"):
                print(f"  {line}")
            if ex.get("llm_astrological_reason"):
                print("\n  -- LLM ASTROLOGICAL REASONING --")
                for line in textwrap.wrap(ex["llm_astrological_reason"], width=110, initial_indent="  ", subsequent_indent="  "):
                    print(line)
        print("\n" + "="*120)
        if explanations and explanations[0].get("llm_selection_rationale"):
            print("\n  -- LLM FIELD SELECTION RATIONALE --")
            for line in textwrap.wrap(explanations[0]["llm_selection_rationale"], width=110, initial_indent="  ", subsequent_indent="  "):
                print(line)
            print("="*120)

"""

if __name__ == "__main__":
    if len(sys.argv) > 1:
        json_path     = sys.argv[1]
        _fname_stem   = os.path.splitext(os.path.basename(json_path))[0]
        student_name  = _fname_stem.split("_")[0].capitalize()
        logger.info(f"Loading payload from: {json_path}  (student: {student_name})")
        with open(json_path, "rb") as f:
            raw = f.read().rstrip(b'\x00')
        raw_payload    = json.loads(raw.decode("utf-8-sig"))
        sample_payload = parse_json_payload(raw_payload, student_name=student_name)
    else:
        logger.info("No payload file provided -- using hardcoded sample (Ramsunder).")
        student_name, target_year = "Ramsunder", "2027"
        # FIX-13: corrected to match actual JSON payload (ramsunder_chart_details.json).
        # Saturn in Leo = no dignity (enemy sign, NOT "OWN"). Mercury in Libra = neutral.
        # Shadbala values from actual JSON virupas.
        sample_payload = NatalPayloadV2(
            name="Ramsunder", lagna_sign="Libra", lagna_lord="Venus",
            h10_lord="Moon", atmakaraka="Saturn", amatyakaraka="Jupiter", karakamsha="Scorpio",
            planet_strength={"Saturn":0.64,"Mars":0.68,"Mercury":0.82,"Rahu":0.50,"Jupiter":0.65,"Moon":0.39,"Sun":0.38,"Venus":0.46,"Ketu":0.50},
            shadbala={"Saturn":383.41,"Mars":408.42,"Mercury":489.67,"Rahu":300.0,"Jupiter":387.51,"Moon":234.60,"Sun":229.45,"Venus":277.61,"Ketu":300.0},
            planet_house={"Saturn":11,"Mars":1,"Mercury":12,"Rahu":3,"Ketu":9,"Jupiter":2,"Moon":8,"Sun":1,"Venus":2},
            house_lords={"1":"Venus","2":"Mars","3":"Jupiter","4":"Saturn","5":"Saturn","6":"Jupiter","7":"Mars","8":"Venus","9":"Mercury","10":"Moon","11":"Sun","12":"Mercury"},
            yogas_present=["BudhaAditya","GajaKesari"],
            dasha_sequence=[{"lord":"Jupiter","start_age":14.8,"end_age":30.8}, {"lord":"Saturn","start_age":30.8,"end_age":49.8}],
            current_age=17.6, sun_moon_degrees_apart=141.5,
            sav_points_houses={"H1":31,"H2":26,"H3":28,"H4":23,"H5":26,"H6":28,"H7":26,"H8":25,"H9":28,"H10":28,"H11":39,"H12":29},
            planet_dignities={"Mars":"OWN","Jupiter":"OWN"},
            d24_planet_dignities={"Jupiter":"OWN","Venus":"OWN","Saturn":"OWN"},
            d9_planet_dignities={"Mars":"OWN","Jupiter":"DEBILITATED","Saturn":"DEBILITATED"},
            combust_planets=["Mercury","Mars"],
            gender="F",
        )

    final_rankings = run_engine(sample_payload)
    active_lord = _get_active_dasha_lord(sample_payload.dasha_sequence, float(sample_payload.current_age))

    # Calculate peak lord for the Explainability Engine
    _peak_lord, _ = _peak_career_dasha(
        getattr(sample_payload, "dasha_sequence", []),
        getattr(sample_payload, "shadbala", {}),
        getattr(sample_payload, "planet_dignities", {}),
        getattr(sample_payload, "house_lords", {}),
        getattr(sample_payload, "atmakaraka", ""),
        getattr(sample_payload, "amatyakaraka", ""),
        current_age=float(getattr(sample_payload, "current_age", 0)),
    )

    # DESIGN-5: Age-stage stream guidance
    _age_stage = classify_age_stage(float(getattr(sample_payload, "current_age", 0)), final_rankings)
    if _age_stage.get("stage") in ("class_9_10", "class_11_12"):
        print(f"\n{'='*60}")
        print(f"  STAGE: {_age_stage['stage'].replace('_',' ').upper()}")
        for s in _age_stage.get("top_streams_by_score", []):
            print(f"  Stream: {s['stream']}  (weighted score: {s['weighted_score']})")
        print(f"  Guidance: {_age_stage['guidance']}")
        print(f"{'='*60}")

    print(f"\n=== JyotishAI Career Rankings -- {sample_payload.name} (Top 20) ===")
    print(f"Engine: {ENGINE_VERSION}  |  Active Dasha: {active_lord or 'N/A'}")
    print(f"\n{'Rank':<5} {'Domain':<14} {'Score':>7}  {'Aff':>6}  {'GapB%':>6}  {'Pen%':>5}  {'Key Planets':<30}  Branch")
    print("-" * 120)
    for rank, rec in enumerate(final_rankings[:20], 1):
        top  = ", ".join(f"{p}({v:.1f})" for p,v in rec["top_affinity_planets"].items())
        sc   = rec["score_components"]
        print(f"{rank:<5} [{rec['domain'].upper():<12}]  {rec['final_score']:>6.2f}"
              f"  {sc['affinity_score']:>6.2f}  {sc['gap_boost_pct']:>+5.1f}%"
              f"  {sc['gap_penalty_pct']:>4.1f}%  {top:<30}  {rec['field_label']}")

    # EXPLAINABILITY ENGINE — HTML full trace (disabled — uncomment to enable)
    # ExplainabilityEngine.export_html_full_trace(
    #     final_rankings, sample_payload, active_lord, _peak_lord,
    #     student_name, top_n=20
    # )

    # Recompute eff_strengths for explainability text export
    _pb_main   = _paksha_bala(getattr(sample_payload, "sun_moon_degrees_apart", 0.0))
    _war_main  = _detect_planetary_war(getattr(sample_payload, "planets_d1", {}))
    _d9_main   = getattr(sample_payload, "divisional_charts", {}).get("D9_navamsha", {})
    _varg_main = [p for p in _ALL_PLANETS
                  if _is_vargottama(p, getattr(sample_payload,"planets_d1",{}).get(p,{}).get("sign",""), _d9_main)]
    _eff_main, _ = _compute_eff_strengths(
        getattr(sample_payload, "shadbala", {}),
        getattr(sample_payload, "planet_dignities", {}),
        getattr(sample_payload, "planet_retrograde", {}),
        _war_main, _varg_main,
        getattr(sample_payload, "nakshatra_data", {}),
        set(getattr(sample_payload, "neecha_bhanga_planets", [])),
        _pb_main,
        getattr(sample_payload, "house_lords", {}),
        getattr(sample_payload, "lagna_lord", ""),
        getattr(sample_payload, "planet_house", {}),
        set(getattr(sample_payload, "cazimi_planets", [])),
        getattr(sample_payload, "planets_d1", {}),
        set(getattr(sample_payload, "combust_planets", [])),
        set(getattr(sample_payload, "detected_yogas", []))
    )
    _peak_lord, _ = _peak_career_dasha(
        getattr(sample_payload, "dasha_sequence", []),
        getattr(sample_payload, "shadbala", {}),
        getattr(sample_payload, "planet_dignities", {}),
        getattr(sample_payload, "house_lords", {}),
        getattr(sample_payload, "atmakaraka", ""),
        getattr(sample_payload, "amatyakaraka", ""),
        current_age=float(getattr(sample_payload, "current_age", 0)),
    )
    explanations = ExplainabilityEngine.generate(
        final_rankings, sample_payload, active_lord, _peak_lord, top_n=15
    )
    #ExplainabilityEngine.print_console(explanations)
    ExplainabilityEngine.export_html(explanations, student_name)

from .payload import NatalPayloadV2
from .astro import (
    _compute_eff_strengths, _detect_planetary_war, _is_vargottama,
    _paksha_bala, _get_active_dasha_lord, _planet_abs_degree,
)
from .boosts import _peak_career_dasha, _ALL_PLANETS
"""
