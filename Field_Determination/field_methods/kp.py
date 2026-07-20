"""KP field-determination module."""
from __future__ import annotations

from typing import Any, Dict, List

from jyotish.boosts import (
    _kp_h10_branch_strength,
    _kp_career_h2h11_strength,
    _kp_edu_branch_strength,
    _h10_sublord_bonus,
    _kp_edu_starlord_bonus,
    _life_science_cluster_bonus,
    _space_aerospace_cluster_bonus,
    _planet_combustion_penalty,
    _dusthana_lord_penalty,
    _d1_vitality_coefficient,
    _karakatwa_domain_bonus,
    _house_signification_bonus,
    _wm,
)
from jyotish.constants import (
    _NAKSHATRA_CAREER_KW, _NAKSHATRA_LORD, _PADA_NAVAMSHA_SIGN,
    _NAVAMSHA_SIGN_CAREER_KW, _SIGN_LORD,
)
from .common import (
    METHOD_SCORE_CAPS,
    build_gate_text,
    build_score_rubric,
    chandra_lagna_h10_lord,
    clamp_score,
    method_result,
    rubric_section,
    top_weighted_planets,
)

# Earth/underground-domain field cluster — H8 career indicator applies for these
_EARTH_FIELD_HINTS = (
    "mining", "petroleum", "oil_gas", "metallurg", "geology", "geological",
    "mineral", "ore", "excavat", "quarr", "drill",
    "materials_science", "polymer", "rubber", "leather", "ceramic",
    "water_resource", "coal", "foundry",
)

def _is_earth_field(field_id: str, label: str) -> bool:
    combined = f"{field_id} {label}".lower()
    return any(h in combined for h in _EARTH_FIELD_HINTS)


def score_kp(
    payload_data: Any,
    domain: str,
    field_affinity: Dict[str, float],
    field_id: str = "",
    field_entry: Dict[str, Any] = None,
) -> Dict[str, Any]:
    kp_sigs_raw   = getattr(payload_data, "kp_significators", {}) or {}
    # G10 (10/10 fix): retrograde planets also signify their previous house, but
    # classical KP treats this as a *secondary, weaker* signification (retrogression
    # implies delay/reversal of the direct promise, not an equally-strong duplicate).
    # Previously this expansion injected the previous house into the SAME level as
    # the direct signification, giving it identical weight — overstating retrograde
    # planets across every method that consumes kp_sigs. Now the retrograde-implied
    # house is demoted one level (level_1 source -> level_2 addition, etc.), landing
    # in the weaker LW tier used by _kp_h10_branch_strength / _kp_edu_branch_strength,
    # and is only added if not already present at an equal-or-stronger level.
    _retro_pl = getattr(payload_data, "retrograde_planets", set()) or set()
    _LEVEL_KEYS = ("level_1", "level_2", "level_3", "level_4")
    kp_sigs: dict = {}
    for _pl, _sig in kp_sigs_raw.items():
        if _pl not in _retro_pl or not isinstance(_sig, dict):
            kp_sigs[_pl] = _sig
            continue
        _expanded = {lk: list(_sig.get(lk, []) or []) for lk in _LEVEL_KEYS}
        for _idx, _lk in enumerate(_LEVEL_KEYS):
            _houses = _sig.get(_lk, []) or []
            if not isinstance(_houses, list):
                continue
            _demoted_key = _LEVEL_KEYS[min(_idx + 1, len(_LEVEL_KEYS) - 1)]
            for _h in _houses:
                _prev_h = ((_h - 2) % 12) + 1
                _already_present = any(_prev_h in _expanded[_lk2] for _lk2 in _LEVEL_KEYS[: _idx + 1])
                if not _already_present and _prev_h not in _expanded[_demoted_key]:
                    _expanded[_demoted_key].append(_prev_h)
        # preserve any non-list keys (defensive)
        for _lk, _v in _sig.items():
            if _lk not in _expanded:
                _expanded[_lk] = _v
        kp_sigs[_pl] = _expanded
    kp_cusps  = getattr(payload_data, "kp_cusps", {}) or {}
    d10_occ   = getattr(payload_data, "d10_house_occupancy", {}) or {}
    # Gap-18b (generalized fix, audit 2026-07): see field_methods/common.py::build_gate_text.
    label     = build_gate_text(field_id, field_entry)
    neecha_bhanga = set(getattr(payload_data, "neecha_bhanga_planets", []) or [])

    def _vit(planet: str) -> float:
        return _d1_vitality_coefficient(planet, payload_data) if planet else 1.0

    score = 0.0
    trace: List[str] = []
    components: Dict[str, float] = {}
    rubric_core       = 0.0
    rubric_support    = 0.0
    rubric_validation = 0.0
    rubric_penalty    = 0.0

    # T3-C / Q4 (10/10 fix): Birth-time confidence gate for KP sublord components.
    # KP sublords shift sign every 4-12 minutes of birth time. Krishnamurti Paddhati's
    # entire cuspal-chain method (sign_lord -> star_lord -> sub_lord -> sub_sub_lord)
    # is built on the precondition that the birth moment is known precisely — it is
    # not a system with a "reduced-confidence" mode. A previous version of this gate
    # partially trusted the sub-lord chain at "approximate" precision (0.60x), which
    # is not real KP: KP does not treat an uncertain sub-lord as "60% believable," it
    # treats a cusp computed from an uncertain time as *not computable* at all, since
    # the wrong sub-lord (or even wrong star-lord, near a boundary) can flip a house's
    # entire signification. The fix removes the partial-trust hedge: sub-lord-derived
    # components are fully stripped (0.0x) whenever birth time is not exact, not just
    # when it is fully unknown. Star-lord (nakshatra) boundaries move roughly once
    # every 1.5-2 hours, so they remain usable at "approximate" precision (small risk
    # of a boundary miss) but are also stripped at "unknown" precision since there is
    # then no time reference to anchor even a coarse cusp at all.
    _policy = getattr(payload_data, "calculation_policy", None)
    _birth_prec = (
        getattr(_policy, "birth_time_precision", None)
        or getattr(payload_data, "birth_time_precision", "exact")
        or "exact"
    )
    # GAP-FIX (2026-07-18, precision-policy wiring): sub-lord trust now consults
    # CalculationPolicy.precise_cusps_allowed directly instead of re-deriving an
    # equivalent "== 'exact'" string check locally. This makes KP's gate the
    # actual consumer of the declared policy (previously precise_cusps_allowed
    # was computed but never read outside to_dict(), so this module's local
    # check could silently drift from the policy's own definition of "precise").
    # precise_cusps_allowed additionally requires birth_time_uncertainty_minutes
    # <= 2, which the old local check did not enforce -- an "exact" precision
    # label with a large uncertainty_minutes value is now correctly treated as
    # not precise enough for the sub-lord chain, closing that gap.
    if _policy is not None and hasattr(_policy, "precise_cusps_allowed"):
        _kp_precise = bool(_policy.precise_cusps_allowed)
    else:
        _kp_precise = _birth_prec == "exact"

    if _birth_prec == "unknown":
        _kp_conf_sub  = 0.0
        _kp_conf_star = 0.0
    elif not _kp_precise:
        _kp_conf_sub  = 0.0
        _kp_conf_star = 0.85 if _birth_prec == "approximate" else 0.0
    else:
        _kp_conf_sub  = 1.00
        _kp_conf_star = 1.00
    _kp_conf = _kp_conf_sub   # legacy alias
    _kp_low_confidence = not _kp_precise
    if _kp_low_confidence:
        trace.append(
            f"KP birth-time precision is '{_birth_prec}' — cuspal sub-lord/sub-sub-lord "
            "signals are not computable with confidence and have been fully excluded "
            "(KP assumes a precise birth time as a precondition, not a partial one)."
        )

    branch_strength = _kp_h10_branch_strength(field_affinity, kp_sigs)
    sublord_bonus   = _h10_sublord_bonus(field_affinity, kp_cusps) * _kp_conf_sub
    edu_star_bonus  = _kp_edu_starlord_bonus(field_affinity, kp_cusps) * _kp_conf_star

    # ── H10 career branch vitality gate ──────────────────────────────────────
    branch_vitality_total  = 0.0
    branch_vitality_weight = 0.0
    for planet, weight in field_affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(("level_1", "level_2", "level_3", "level_4")):
            if 10 in sig.get(key, []):
                branch_piece = weight * (1.0 if idx == 0 else 0.75 if idx == 1 else 0.50 if idx == 2 else 0.25)
                branch_vitality_total  += branch_piece * _vit(planet)
                branch_vitality_weight += branch_piece
                break

    branch_vitality = (branch_vitality_total / branch_vitality_weight) if branch_vitality_weight > 0 else 1.0
    _h10_branch     = 40.0 * branch_strength * branch_vitality

    h10_sub      = kp_cusps.get("H10", {}).get("sub_lord", "")
    _h10_sublord = 30.0 * sublord_bonus * _vit(h10_sub)

    # ── 10/10 fix: H10 sub-sub-lord (4th cuspal level) direct bonus ──────────
    # KP's decisive chain for a cusp is sign_lord -> star_lord -> sub_lord -> sub_sub_lord.
    # The sub_lord settles whether the house's promise fructifies at all; the
    # sub_sub_lord then refines *which* of the sub_lord's significations actually
    # plays out. It was previously only reachable indirectly (as level_4 inside the
    # generic branch-strength scan, at the lowest 0.25x tier) — never scored as a
    # first-class H10 cuspal signal the way sign/star/sub lord already are.
    # Weighted below the sub-lord bonus (30 pts) since it refines rather than
    # decides, but above generic support-tier bonuses since it is still a direct
    # cuspal-chain signal, not a derived one.
    h10_ssl = kp_cusps.get("H10", {}).get("sub_sub_lord", "")
    _h10_ssl_aff = field_affinity.get(h10_ssl, 0.0) if h10_ssl else 0.0
    _h10_sub_sub_lord = 0.0
    if h10_ssl and _h10_ssl_aff > 0.0:
        _h10_sub_sub_lord = 15.0 * _h10_ssl_aff * _vit(h10_ssl) * _kp_conf_sub
        # Consensus amplifier: sub-sub-lord agreeing with the sub-lord chain (same
        # planet, or same sign dispositor) is a strong KP confirmation.
        if h10_ssl == h10_sub:
            _h10_sub_sub_lord *= 1.35
            trace.append(f"KP H10 sub-lord and sub-sub-lord both {h10_ssl} — strong cuspal consensus.")
        elif h10_sub and _SIGN_LORD.get(
            (getattr(payload_data, "planets_d1", {}) or {}).get(h10_ssl, {}).get("sign", ""), ""
        ) == h10_sub:
            _h10_sub_sub_lord *= 1.15
            trace.append(f"KP H10 sub-sub-lord {h10_ssl} is dispositor-linked to sub-lord {h10_sub}.")

    # ── Education house CSL sub-lords (H4/H5/H9) ─────────────────────────────
    edu_sub_lords = [
        kp_cusps.get("H4", {}).get("sub_lord", ""),
        kp_cusps.get("H5", {}).get("sub_lord", ""),
        kp_cusps.get("H9", {}).get("sub_lord", ""),
    ]
    edu_vit_values = [_vit(p) for p in edu_sub_lords if p]
    edu_vitality   = sum(edu_vit_values) / len(edu_vit_values) if edu_vit_values else 1.0
    _edu_star      = 20.0 * edu_star_bonus * edu_vitality

    # ── KP Education House Combination (H4/H5/H9/H11) ────────────────────────
    edu_branch_strength = _kp_edu_branch_strength(field_affinity, kp_sigs)
    edu_bvit_total  = 0.0
    edu_bvit_weight = 0.0
    _EDU_HOUSES = {4, 5, 9, 11}
    for planet, weight in field_affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(("level_1", "level_2", "level_3", "level_4")):
            if any(h in sig.get(key, []) for h in _EDU_HOUSES):
                piece = weight * (1.0 if idx == 0 else 0.75 if idx == 1 else 0.50 if idx == 2 else 0.25)
                edu_bvit_total  += piece * _vit(planet)
                edu_bvit_weight += piece
                break
    edu_branch_vitality = (edu_bvit_total / edu_bvit_weight) if edu_bvit_weight > 0 else 1.0
    _edu_branch = 15.0 * edu_branch_strength * edu_branch_vitality

    # ── Gap 3: H2+H11 secondary career branch ────────────────────────────────
    # Classical KP: H2+H6+H10+H11 must all connect. H2 (wealth) and H11 (gains)
    # are primary significators for earth/industry charts where H10 is Venus-locked.
    h2h11_strength      = _kp_career_h2h11_strength(field_affinity, kp_sigs)
    h2h11_vit_total     = 0.0
    h2h11_vit_weight    = 0.0
    _H2H11 = {2, 11}
    for planet, weight in field_affinity.items():
        sig = kp_sigs.get(planet, {}) or {}
        for idx, key in enumerate(("level_1", "level_2", "level_3", "level_4")):
            if any(h in sig.get(key, []) for h in _H2H11):
                lw = 1.0 if idx == 0 else 0.75 if idx == 1 else 0.50 if idx == 2 else 0.25
                piece = weight * lw
                h2h11_vit_total  += piece * _vit(planet)
                h2h11_vit_weight += piece
                break
    h2h11_vitality = (h2h11_vit_total / h2h11_vit_weight) if h2h11_vit_weight > 0 else 1.0
    _h2h11_branch  = 20.0 * h2h11_strength * h2h11_vitality

    score       += _h10_branch + _h10_sublord + _h10_sub_sub_lord + _edu_star + _edu_branch + _h2h11_branch
    rubric_core += _h10_branch + _h10_sublord + _h10_sub_sub_lord + _edu_star + _edu_branch
    rubric_support += _h2h11_branch
    components["h10_branch"]   = round(_h10_branch, 2)
    components["h10_sublord"]  = round(_h10_sublord, 2)
    components["h10_sub_sub_lord"] = round(_h10_sub_sub_lord, 2)
    components["edu_star"]     = round(_edu_star, 2)
    components["edu_branch"]   = round(_edu_branch, 2)
    components["h2h11_branch"] = round(_h2h11_branch, 2)

    # T1-D: Moon's natal star is a first-class KP significator rather than an
    # incidental generic nakshatra boost.  The star-lord supplies the domain
    # affinity; direct nakshatra-career keyword agreement supplies the upper
    # tier. It is unavailable—not neutral—when the birth time is unknown.
    _moon_nak = str(getattr(payload_data, "moon_nakshatra", "") or "")
    if not _moon_nak:
        _moon_raw = (getattr(payload_data, "nakshatra_data", {}) or {}).get("Moon", "")
        _moon_nak = str((_moon_raw.get("nakshatra") or _moon_raw.get("name") or "")
                        if isinstance(_moon_raw, dict) else _moon_raw)
    _moon_nak_points = 0.0
    if _birth_prec != "unknown" and _moon_nak:
        _moon_star_lord = _NAKSHATRA_LORD.get(_moon_nak, "")
        _star_aff = field_affinity.get(_moon_star_lord, 0.0)
        _keyword_hit = any(_wm(kw, label.lower()) for kw in _NAKSHATRA_CAREER_KW.get(_moon_nak, []))
        if _star_aff >= 0.15:
            _moon_nak_points = 25.0 if _keyword_hit else 20.0
        elif _keyword_hit and _star_aff > 0:
            _moon_nak_points = 20.0
    score += _moon_nak_points
    rubric_support += _moon_nak_points
    components["moon_nakshatra_first_class"] = round(_moon_nak_points, 2)
    if _moon_nak_points:
        trace.append(f"Moon nakshatra {_moon_nak} supplies a first-class KP field signal.")

    # ── G24: domain-based career bonus (replaces fragile keyword string match) ─
    _CAREER_DOMAINS = {"engineering","medicine","technology","science","law",
                       "management","research","commerce","healthcare","defense"}
    if domain in _CAREER_DOMAINS:
        _bonus = (100.0 - score) * 0.05
        score += _bonus
        rubric_support += _bonus
        components["career_domain_bonus"] = round(_bonus, 2)

    # ── Top-2 planet L1 H10 / H5 / H9 bonus ─────────────────────────────────
    for planet in top_weighted_planets(field_affinity, 2):
        sig = kp_sigs.get(planet, {}) or {}
        if 10 in sig.get("level_1", []):
            _bonus = 4.0 * field_affinity.get(planet, 0.0) * _vit(planet)
            score += _bonus
            rubric_core += _bonus
            trace.append(f"KP level-1 H10 significator alignment via {planet}.")
        elif 5 in sig.get("level_1", []) or 9 in sig.get("level_1", []):
            _bonus = 2.5 * field_affinity.get(planet, 0.0) * _vit(planet)
            score += _bonus
            rubric_support += _bonus

    # ── H10 cusp consensus (sub_lord == star_lord) ───────────────────────────
    if h10_sub and h10_sub == kp_cusps.get("H10", {}).get("star_lord", ""):
        _bonus = (100.0 - score) * 0.06 * _vit(h10_sub)
        score += _bonus
        rubric_validation += _bonus
        components["h10_consensus"] = round(_bonus, 2)
        trace.append("KP H10 cusp consensus is strong.")

    # ── N6: H7 sub-lord scoring for partnership/business fields ─────────────
    # H7 (partnerships/business associates) is critical for management, law, commerce.
    _PARTNERSHIP_DOMAINS = {"management", "law", "commerce", "interdisciplinary"}
    if domain in _PARTNERSHIP_DOMAINS:
        sub_h7 = kp_cusps.get("H7", {}).get("sub_lord", "")
        if sub_h7:
            w7 = field_affinity.get(sub_h7, 0.0)
            if w7 >= 0.15:
                b7 = 5.0 * _vit(sub_h7) * _kp_conf_sub * (1.0 if w7 >= 0.25 else 0.55 if w7 >= 0.15 else 0.0)
                if b7 > 0:
                    score += b7; rubric_support += b7
                    components["h7_sublord"] = round(b7, 2)
                    trace.append(f"KP H7 (partnerships) sub-lord {sub_h7} "
                                 f"supports {domain} field (w={w7:.2f}).")

    # ── C4: H4 H11 H6 H2 sub-lord scoring ────────────────────────────────────
    for cusp_key, base_pts in (("H4", 7.0), ("H11", 8.0), ("H6", 12.0), ("H2", 5.0)):  # G4: H6 = employment house
        sub = kp_cusps.get(cusp_key, {}).get("sub_lord", "")
        if not sub:
            continue
        w = field_affinity.get(sub, 0.0)
        v = _vit(sub)
        if w >= 0.25:
            b = base_pts * v
        elif w >= 0.15:
            b = base_pts * 0.55 * v
        elif w >= 0.08:
            b = base_pts * 0.20 * v
        else:
            continue
        b *= _kp_conf_sub
        if b <= 0:
            continue
        score += b
        rubric_support += b
        components[f"{cusp_key.lower()}_sublord"] = round(b, 2)
        trace.append(f"KP {cusp_key} sub-lord {sub} aligns with field (w={w:.2f}).")

    # ── Life-science / space-aerospace cluster bonuses ────────────────────────
    life_bonus  = _life_science_cluster_bonus(field_id, label, field_affinity, getattr(payload_data, "eff_strengths", {}) or {}) * 20.0
    space_bonus = _space_aerospace_cluster_bonus(field_id, label, field_affinity, getattr(payload_data, "eff_strengths", {}) or {}) * 20.0
    if life_bonus > 0:
        _bonus = (100.0 - score) * (life_bonus / 100.0)
        score += _bonus
        rubric_validation += _bonus
        components["life_science_cluster"] = round(_bonus, 2)
    if space_bonus > 0:
        _bonus = (100.0 - score) * (space_bonus / 100.0)
        score += _bonus
        rubric_validation += _bonus
        components["space_aerospace_cluster"] = round(_bonus, 2)

    # ── Gap 4: H8 earth/underground branch (mining, petroleum, geology, etc.) ─
    if _is_earth_field(field_id, label):
        h8_raw        = 0.0
        h8_vit_total  = 0.0
        h8_vit_weight = 0.0
        for planet, weight in field_affinity.items():
            sig = kp_sigs.get(planet, {}) or {}
            for idx, key in enumerate(("level_1", "level_2", "level_3", "level_4")):
                if 8 in sig.get(key, []):
                    lw = 1.0 if idx == 0 else 0.75 if idx == 1 else 0.50 if idx == 2 else 0.25
                    piece = weight * lw
                    h8_raw        += piece
                    h8_vit_total  += piece * _vit(planet)
                    h8_vit_weight += piece
                    break
        if h8_raw > 0:
            h8_vitality  = (h8_vit_total / h8_vit_weight) if h8_vit_weight > 0 else 1.0
            _max_h8      = sum(field_affinity.values()) or 1.0
            h8_strength  = min(h8_raw / _max_h8, 1.0)
            _h8_branch   = 24.0 * h8_strength * h8_vitality
            score         += _h8_branch
            rubric_support += _h8_branch
            components["h8_earth_branch"] = round(_h8_branch, 2)
            trace.append("KP H8 (underground/earth resources) branch active for earth-domain field.")

    # ── D10 H10 occupant bonus ────────────────────────────────────────────────
    d10_h10_planets = d10_occ.get("10", []) or d10_occ.get(10, [])
    d10_bonus = 0.0
    for p in d10_h10_planets:
        w = field_affinity.get(p, 0.0)
        if w >= 0.10:
            d10_bonus += 3.5 * w
    if d10_bonus > 0:
        d10_bonus = min(d10_bonus, 8.0)
        _bonus    = (100.0 - score) * (d10_bonus / 100.0)
        occupant_vits = [_vit(p) for p in d10_h10_planets if field_affinity.get(p, 0.0) >= 0.10]
        if occupant_vits:
            _bonus *= sum(occupant_vits) / len(occupant_vits)
        score             += _bonus
        rubric_validation += _bonus
        components["d10_h10_occupants"] = round(_bonus, 2)
        trace.append("D10 H10 occupants reinforce KP career significators.")

    # ── Gap 6: D10 H11 occupant bonus (gains/income, secondary career) ────────
    d10_h11_planets  = d10_occ.get("11", []) or d10_occ.get(11, [])
    d10_h11_bonus    = 0.0
    for p in d10_h11_planets:
        w = field_affinity.get(p, 0.0)
        if w >= 0.10:
            d10_h11_bonus += 3.5 * w * 0.5
    if d10_h11_bonus > 0:
        d10_h11_bonus = min(d10_h11_bonus, 4.0)
        _bonus_h11    = (100.0 - score) * (d10_h11_bonus / 100.0)
        h11_vits      = [_vit(p) for p in d10_h11_planets if field_affinity.get(p, 0.0) >= 0.10]
        if h11_vits:
            _bonus_h11 *= sum(h11_vits) / len(h11_vits)
        score             += _bonus_h11
        rubric_validation += _bonus_h11
        components["d10_h11_occupants"] = round(_bonus_h11, 2)
        trace.append("D10 H11 occupants provide gains/income signal (secondary career).")

    # ── Systematic karaka-domain bonus (Gap fix: KP was the only method not ──
    # wired to this shared fallback; knrao/jaimini/parashara/dashamsha already had it) ─
    _kp_planets_d1 = getattr(payload_data, "planets_d1", {}) or {}
    _kp_ph_all = getattr(payload_data, "planet_house", {}) or {}
    _karaka_total_kp, _karaka_hits_kp = _karakatwa_domain_bonus(
        domain, field_affinity, _kp_planets_d1, _kp_ph_all, payload_data, scale=6.0, cap=12.0,
    )
    if _karaka_total_kp > 0:
        score += _karaka_total_kp; rubric_support += _karaka_total_kp
        components["karaka_domain_bonus"] = round(_karaka_total_kp, 2)
        trace.append(
            f"Karakatwa domain match ({domain}): {', '.join(_karaka_hits_kp)} carry classical "
            "significator authority for this domain (systematic karaka-to-field mapping)."
        )

    # ── Ontology fix: house-signification-first primitive ────────────────────
    # Structural house-first signal (2/6/10/11 already covered by KP's own
    # cuspal chain above): scores the lord of each house classically
    # significant for this domain (e.g. H6/H8/H12 for medicine, H6/H7/H9 for
    # law), grounded in this specific field's own affinity weights, so KP's
    # judgment is not solely dependent on cuspal-chain signals matching field
    # labels via keywords elsewhere in this file.
    _kp_house_lords = getattr(payload_data, "house_lords", {}) or {}
    _house_total_kp, _house_hits_kp = _house_signification_bonus(
        domain, field_affinity, _kp_house_lords, _kp_ph_all, _kp_planets_d1,
        payload_data, scale=5.0, cap=12.0,
    )
    if _house_total_kp > 0:
        score += _house_total_kp; rubric_support += _house_total_kp
        components["house_signification_bonus"] = round(_house_total_kp, 2)
        trace.append(
            f"House signification ({domain}): {', '.join(_house_hits_kp)} lord(s) "
            "carry classical house authority for this field, independent of cuspal chain."
        )

    # ── Combustion penalty ────────────────────────────────────────────────────
    combustion_penalty = _planet_combustion_penalty(
        field_affinity,
        getattr(payload_data, "combust_planets", []) or [],
        getattr(payload_data, "planet_dignities", {}) or {},
        getattr(payload_data, "planets_d1", {}) or {},
        vargottama_planets=getattr(payload_data, "vargottama_planets", []),
    ) * 100.0
    if combustion_penalty > 0:
        score         -= combustion_penalty
        rubric_penalty -= combustion_penalty
        components["combustion_penalty"] = round(-combustion_penalty, 2)
        trace.append("Combust planets weaken KP event-fructification.")

    # ── Dusthana lord penalty ─────────────────────────────────────────────────
    dusthana_penalty = _dusthana_lord_penalty(
        field_affinity,
        getattr(payload_data, "lagna_sign", "") or "",
        getattr(payload_data, "house_lords", {}) or {},
        getattr(payload_data, "lagna_lord", "") or "",
        field_id or "",
        getattr(payload_data, "eff_strengths", {}) or {},
        planet_house=getattr(payload_data, "planet_house", {}) or {},
    ) * 100.0
    if dusthana_penalty > 0:
        score         -= dusthana_penalty
        rubric_penalty -= dusthana_penalty
        components["dusthana_penalty"] = round(-dusthana_penalty, 2)
        trace.append("Dusthana lordship weakens KP cusp delivery.")

    # ── S3: top-4 vitality penalty; S4: skip Neecha Bhanga planets ────────────
    for planet in top_weighted_planets(field_affinity, 4):
        if planet in neecha_bhanga:
            continue
        vitality = _d1_vitality_coefficient(planet, payload_data)
        if vitality < 1.0:
            penalty = (1.0 - vitality) * field_affinity.get(planet, 0.0) * 20.0
            if penalty > 0:
                score         -= penalty
                rubric_penalty -= penalty
                components[f"{planet.lower()}_vitality_penalty"] = round(-penalty, 2)
                trace.append(f"{planet} vitality is reduced by D1 impairments.")

    # ── G12: H10 from Chandra Lagna (Gap-14 fix: shared common helper) ────────
    _cl_h10 = chandra_lagna_h10_lord(getattr(payload_data, "planets_d1", {}) or {})
    if _cl_h10:
        _cl_sig = kp_sigs.get(_cl_h10, {})
        if 10 in _cl_sig.get('level_1', []) or 10 in _cl_sig.get('level_2', []):
            _cl_b = field_affinity.get(_cl_h10, 0.0) * 6.0 * _vit(_cl_h10)
            if _cl_b > 0:
                score += _cl_b; rubric_support += _cl_b
                components['chandra_h10_kp'] = round(_cl_b, 2)
                trace.append(f'H10 from Chandra Lagna ({_cl_h10}) is KP significator.')

    # ── T1-D: Moon nakshatra as first-class KP career signal ─────────────────
    # Krishnamurti explicitly identifies Moon's nakshatra as the primary career
    # determinant in KP — it reveals the native's emotional career direction.
    _planet_naks = getattr(payload_data, "planet_nakshatras", {}) or {}
    _moon_nak    = _planet_naks.get("Moon", "")
    if _moon_nak:
        _moon_nak_lord = _NAKSHATRA_LORD.get(_moon_nak, "")
        if _moon_nak_lord:
            _moon_nak_kws = _NAKSHATRA_CAREER_KW.get(_moon_nak, [])
            if any(_wm(kw, label) for kw in _moon_nak_kws):
                _mnl_aff = field_affinity.get(_moon_nak_lord, 0.0)
                _mnl_vit = _vit("Moon")
                _moon_nak_pts = max(_mnl_aff * 22.0, 1.5) * _mnl_vit * _kp_conf

                # P1: Pada refinement — navamsha sign of Moon's pada adds sub-domain precision.
                # Each pada occupies 3°20′ of the nakshatra and falls in a specific navamsha sign,
                # giving the nakshatra a finer career flavour (Krishnamurti Paddhati, Vol. 2).
                _moon_pada = getattr(payload_data, "moon_nakshatra_pada", 0) or 0
                _pada_signs = _PADA_NAVAMSHA_SIGN.get(_moon_nak, [])
                if 1 <= _moon_pada <= 4 and _pada_signs:
                    _pada_nav_sign = _pada_signs[_moon_pada - 1]
                    _pada_kws = _NAVAMSHA_SIGN_CAREER_KW.get(_pada_nav_sign, [])
                    if any(_wm(kw, label) for kw in _pada_kws):
                        # Pada confirms the nakshatra signal — amplify by 20%
                        _moon_nak_pts *= 1.20
                        trace.append(
                            f"KP Moon pada {_moon_pada} ({_pada_nav_sign} navamsha) "
                            f"confirms {domain} field — pada-level career specificity."
                        )
                    else:
                        # Pada in a different navamsha sign — mildly dampen (partial mismatch)
                        _moon_nak_pts *= 0.90

                score += _moon_nak_pts
                rubric_core += _moon_nak_pts
                components["moon_nakshatra_kp"] = round(_moon_nak_pts, 2)
                trace.append(
                    f"KP Moon nakshatra {_moon_nak} (lord {_moon_nak_lord}) "
                    f"career keywords match field — primary KP emotional determinant."
                )

    # ── 10/10 fix: Ruling Planets (RP) technique ─────────────────────────────
    # Classical KP judgment technique (Krishnamurti Paddhati, horary chapter, also
    # applied to natal career confirmation): the "Ruling Planets" at a moment are
    # the day lord (Vara), the ascendant's sign lord + star lord, and the Moon's
    # sign lord + star lord. When a node (Rahu/Ketu) would be a ruling planet, its
    # sign dispositor is used instead (nodes act through their dispositor). This
    # set was entirely absent from the KP module — every other KP signal here is
    # cuspal/significator-based, but RP is KP's standard *cross-check* layer used
    # to confirm or reject a judgment reached from significators. When the H10
    # sub-lord (the decisive cuspal factor) or the top field-affinity planet is
    # itself a Ruling Planet, that is a strong independent confirmation; when
    # neither the field's top planets nor the H10 sub-lord appear in the RP set
    # at all, KP tradition treats the judgment as less reliable.
    def _rp_dispositor(planet: str) -> str:
        if planet in ("Rahu", "Ketu"):
            _p_sign = (getattr(payload_data, "planets_d1", {}) or {}).get(planet, {}).get("sign", "")
            return _SIGN_LORD.get(_p_sign, "") or planet
        return planet

    _birth_weekday = getattr(payload_data, "birth_weekday", "") or ""
    if not _birth_weekday:
        try:
            import datetime as _dt_rp
            _bdate_rp = getattr(payload_data, "birth_date", "") or ""
            if _bdate_rp:
                _WD_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                _birth_weekday = _WD_NAMES[_dt_rp.date.fromisoformat(str(_bdate_rp)[:10]).weekday()]
        except Exception:
            _birth_weekday = ""
    _DAY_TO_PLANET_RP = {"Monday": "Moon", "Tuesday": "Mars", "Wednesday": "Mercury",
                          "Thursday": "Jupiter", "Friday": "Venus", "Saturday": "Saturn", "Sunday": "Sun"}
    _day_lord = _DAY_TO_PLANET_RP.get(_birth_weekday, "")

    _lagna_sign_rp = getattr(payload_data, "lagna_sign", "") or ""
    _lagna_nak_rp  = getattr(payload_data, "lagna_nakshatra", "") or kp_cusps.get("H1", {}).get("nakshatra", "")
    _lagna_sign_lord = kp_cusps.get("H1", {}).get("sign_lord", "") or _SIGN_LORD.get(_lagna_sign_rp, "")
    _lagna_star_lord = kp_cusps.get("H1", {}).get("star_lord", "") or _NAKSHATRA_LORD.get(_lagna_nak_rp, "")

    _moon_sign_rp = (getattr(payload_data, "planets_d1", {}) or {}).get("Moon", {}).get("sign", "")
    _moon_sign_lord = _SIGN_LORD.get(_moon_sign_rp, "")
    _moon_nak_rp  = (getattr(payload_data, "planet_nakshatras", {}) or {}).get("Moon", "")
    _moon_star_lord = _NAKSHATRA_LORD.get(_moon_nak_rp, "")

    _rp_raw = [_day_lord, _lagna_sign_lord, _lagna_star_lord, _moon_sign_lord, _moon_star_lord]
    ruling_planets = {_rp_dispositor(p) for p in _rp_raw if p}

    _rp_bonus = 0.0
    if ruling_planets:
        _rp_confirms = []
        if h10_sub and h10_sub in ruling_planets:
            _rp_confirms.append(h10_sub)
        _top2 = top_weighted_planets(field_affinity, 2)
        for _tp in _top2:
            if _tp in ruling_planets and _tp not in _rp_confirms:
                _rp_confirms.append(_tp)
        if _rp_confirms:
            _rp_vit = sum(_vit(p) for p in _rp_confirms) / len(_rp_confirms)
            _rp_bonus = (100.0 - score) * 0.06 * min(len(_rp_confirms), 3) / 3.0 * _rp_vit
            if _rp_bonus > 0:
                score += _rp_bonus
                rubric_validation += _rp_bonus
                components["ruling_planets"] = round(_rp_bonus, 2)
                trace.append(
                    f"KP Ruling Planets {sorted(ruling_planets)} confirm field via "
                    f"{', '.join(_rp_confirms)} — classical RP cross-check technique."
                )
        else:
            # No overlap between RP set and the field's decisive planets — classical
            # KP treats an unconfirmed judgment as weaker, not necessarily wrong.
            _rp_penalty = score * 0.03
            if _rp_penalty > 0:
                score -= _rp_penalty
                rubric_penalty -= _rp_penalty
                components["ruling_planets_unconfirmed"] = round(-_rp_penalty, 2)
                trace.append(
                    f"KP Ruling Planets {sorted(ruling_planets)} do not overlap the field's "
                    f"decisive planets — judgment lacks RP cross-check confirmation."
                )

    rubric = build_score_rubric(
        "kp",
        [
            rubric_section(
                "core",
                rubric_core,
                40.0,
                note="H10 branch, H10 sub-lord/sub-sub-lord, Moon nakshatra, education CSL (H4/H5/H9 sub-lords).",
                items=["h10_branch", "h10_sublord", "h10_sub_sub_lord", "moon_nakshatra_kp", "edu_star", "edu_branch"],
            ),
            rubric_section(
                "support",
                rubric_support,
                25.0,
                note="Career keyword, H2+H11 career branch, H8 earth branch, secondary cusp support, "
                     "systematic karaka-domain bonus, and house-signification-first bonus.",
                items=["career_keyword", "h2h11_branch", "h8_earth_branch", "h4_sublord", "h11_sublord",
                       "karaka_domain_bonus", "house_signification_bonus"],
            ),
            rubric_section(
                "validation",
                rubric_validation,
                20.0,
                note="D10 occupancy (H10+H11), cluster confirmations, and Ruling Planets cross-check.",
                items=["h10_consensus", "life_science_cluster", "d10_h10_occupants",
                       "d10_h11_occupants", "ruling_planets"],
            ),
            rubric_section(
                "penalty",
                rubric_penalty,
                20.0,
                kind="penalty",
                note="Combustion, dusthana, vitality friction, and unconfirmed Ruling Planets.",
                items=["combustion_penalty", "dusthana_penalty", "ruling_planets_unconfirmed"],
            ),
        ],
    )

    components["birth_time_precision"] = _birth_prec
    components["kp_low_confidence"] = 1.0 if _kp_low_confidence else 0.0

    # Gap-1 (audit 2026-07) fix: cap unified with the bundle via METHOD_SCORE_CAPS.
    # Gap-3/9 fix: pass raw signed `score` (not pre-clamped) so contraindicated
    # charts (net penalties > positives) are distinguishable from neutral ones;
    # method_result() still clamps internally for the "score" field.
    return method_result("kp", score, trace, components, rubric=rubric,
                          normalization_cap=METHOD_SCORE_CAPS["kp"])
