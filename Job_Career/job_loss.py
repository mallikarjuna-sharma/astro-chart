"""JyotishAI — Adverse-Career-Event subsystem (job loss / forced exit / burnout).

Implements the multi-layer job-loss confirmation framework on top of data the
engine already computes (KP significators & cusps, D10 Dashamsha, SAV,
Vimshottari DBA lords, transits, Jaimini A10/AmK). Nothing here calls an LLM
and every function is defensive: missing payload fields degrade gracefully to a
neutral / low-confidence answer rather than raising.

Framework mapping (see JOB_LOSS_FRAMEWORK_GAP_ANALYSIS_2026-07.md):
    G2  compute_jobloss_balance      — 5/8/12/9 vs 2/6/10/11 overpower score
    G3  significator_strength        — full DBA significators, occupancy>star>sub>own
    G4  kp_job_promise               — 2/6/10/11/12 cusp sub-lords as job promise
    G5  d10_career_affliction        — D10 6/10 afflicted, 8/12 activated
    G6  transit_career_triggers      — Saturn/Rahu/Ketu over the career axis
    G7  av_severity                  — Ashtakavarga severity multiplier
    G8  jaimini_status_risk          — A10 8/12, malefics/nodes on A10, AmK
    G9  varshaphala_year_pressure    — Muntha-based annual pressure (lightweight)
    G11 jobloss_confirmation_ledger  — independent-layer 5-of-7 gate
    G1  classify_adverse_event       — JOB_LOSS/FORCED_EXIT/BURNOUT/RESTRUCTURING
    G12 jupiter_protects             — protection downgrade (loss -> change)

Public entry point used by the timeline:
    classify_adverse_event(scores, flags, payload, active_h, coarse_adverse)
        -> (event_type | None, detail_dict)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Set

# ── House vocabulary ────────────────────────────────────────────────────────
# CLARIFICATION (2026-08-22, audit item #20): this set is intentionally NOT
# "5th and 9th as trikona houses of fortune" — it is bhavat-bhavam loss
# derivation. 5 = 12th-from-6th (loss of service/health axis), 8 = dusthana
# (sudden disruption), 12 = dusthana (loss/expenditure), 9 = 12th-from-10th
# (loss FROM the 10th/career house, via (2*(10-1))%12+1 = 9). The numeral 9
# here plays the role of "12th from career," not the 9th-house trikona of
# fortune — those are two different classical meanings that happen to share
# the same house number. Verified correct as-is; no code change needed.
LOSS_HOUSES: Set[int] = {5, 8, 12, 9}       # 5=12th-from-6th, 9=12th-from-10th
PROTECT_HOUSES: Set[int] = {2, 6, 10, 11}   # salary / service / position / gain

# KP significator level weights — matches the convention already used in
# astro_enhancer.py (level_1 strongest). occupancy > star-lord > sub-lord > owner.
_LEVEL_WEIGHTS: Dict[str, float] = {
    "level_1": 1.00, "level_2": 0.80, "level_3": 0.55, "level_4": 0.30,
}
# Dasha role weights: MD is the permission-giver, AD the operator, PD the trigger.
_ROLE_WEIGHTS: Dict[str, float] = {"md": 1.0, "ad": 0.85, "pd": 0.55}

_MALEFICS = frozenset({"Saturn", "Mars", "Rahu", "Ketu", "Sun"})
_BURNOUT_PLANETS = frozenset({"Moon", "Saturn", "Ketu"})

_SIGN_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
_SIGN_IDX = {s: i for i, s in enumerate(_SIGN_ORDER)}
_SIGN_LORD = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn",
    "Pisces": "Jupiter",
}
_AFFLICTED_DIGNITIES = frozenset({"DEBILITATED", "FALLEN", "COMBUST", "ENEMY"})


# ───────────────────────────────────────────────────────────────────────────
# G3 — significator strength (occupancy > star-lord > sub-lord > ownership)
# ───────────────────────────────────────────────────────────────────────────
def significator_strength(planet: str, houses: Set[int], payload: Any) -> float:
    """Weighted strength with which `planet` signifies any house in `houses`.

    Uses the payload's kp_significators level map when present. For each target
    house the planet signifies, credit the strongest (lowest-level) weight at
    which it does so. Falls back to occupancy(1.0)+ownership(0.5) when the
    significator map is missing (partial/synthetic charts).
    """
    if not planet:
        return 0.0
    sig = (getattr(payload, "kp_significators", {}) or {}).get(planet)
    total = 0.0
    if isinstance(sig, dict) and any(sig.values()):
        for h in houses:
            best = 0.0
            for level, wt in _LEVEL_WEIGHTS.items():
                lvl_houses = sig.get(level, []) or []
                if h in lvl_houses and wt > best:
                    best = wt
            total += best
        return total
    # ── Fallback: occupancy + ownership ─────────────────────────────────────
    ph = getattr(payload, "planet_house", {}) or {}
    hl = getattr(payload, "house_lords", {}) or {}
    occ = ph.get(planet, 0)
    if occ in houses:
        total += 1.0
    for hstr, lord in hl.items():
        if lord == planet:
            try:
                if int(hstr) in houses:
                    total += 0.5
            except (TypeError, ValueError):
                continue
    return total


# ───────────────────────────────────────────────────────────────────────────
# G2 — loss-vs-protection balance across the operating DBA lords
# ───────────────────────────────────────────────────────────────────────────
def compute_jobloss_balance(period_lords: Dict[str, str], payload: Any) -> Dict[str, Any]:
    """Score how strongly the operating dasha lords signify loss vs protection.

    period_lords: {"md": planet, "ad": planet, "pd": planet}  (pd optional)
    Returns loss_strength, protect_strength, net (loss-protect, normalised),
    and a per-house breakdown for transparency in the report.
    """
    loss = 0.0
    protect = 0.0
    per_lord: Dict[str, Dict[str, float]] = {}
    for role, lord in period_lords.items():
        if not lord:
            continue
        rw = _ROLE_WEIGHTS.get(role, 0.5)
        l = significator_strength(lord, LOSS_HOUSES, payload) * rw
        p = significator_strength(lord, PROTECT_HOUSES, payload) * rw
        loss += l
        protect += p
        per_lord[role] = {"lord": lord, "loss": round(l, 3), "protect": round(p, 3)}
    denom = (loss + protect) or 1.0
    net = (loss - protect) / denom            # -1 (fully protected) .. +1 (fully loss)
    return {
        "loss_strength": round(loss, 3),
        "protect_strength": round(protect, 3),
        "net": round(net, 3),
        "loss_overpowers": loss > protect,
        "per_lord": per_lord,
    }


# ───────────────────────────────────────────────────────────────────────────
# G4 — KP cusp sub-lords 2/6/10/11/12 as job promise
# ───────────────────────────────────────────────────────────────────────────
def kp_job_promise(payload: Any) -> Dict[str, Any]:
    """Judge whether the job-continuity cusp sub-lords protect or fail.

    For each of H2/H6/H10/H11/H12 read the cusp sub-lord and weigh its
    signification of protection houses against loss houses. protection_fails
    is True when the continuity cusps (2/6/10/11) collectively signify loss
    more than protection.
    """
    kp_cusps = getattr(payload, "kp_cusps", {}) or {}
    # BUGFIX (2026-07, birth-time-sensitivity audit): default was "exact",
    # silently treating missing precision as a fully-known birth time; and
    # an empty string was previously excluded from low_conf, which is
    # backwards -- no declared precision is exactly the case KP cusp
    # sub-lords are most sensitive to. Default and empty-string now both
    # correctly count as low confidence.
    precision = str(getattr(payload, "birth_time_precision", "unknown") or "unknown").lower()
    # GAP-FIX (P0-2, CalculationPolicy threading): defer to the single declared
    # policy's precise_cusps_allowed (which also enforces uncertainty_minutes
    # <= 2) instead of a local == "exact" string check, for the same KP
    # cusp-sensitivity reason documented in field_methods/kp.py's T3-C gate.
    _policy = getattr(payload, "calculation_policy", None)
    if _policy is not None and hasattr(_policy, "precise_cusps_allowed"):
        low_conf = not bool(_policy.precise_cusps_allowed)
    else:
        low_conf = precision != "exact"     # cusp sub-lords are birth-time sensitive

    per_cusp: Dict[str, Dict[str, Any]] = {}
    protect_score = 0.0
    loss_score = 0.0
    for hnum in (2, 6, 10, 11, 12):
        cusp = kp_cusps.get(f"H{hnum}", kp_cusps.get(str(hnum), {})) or {}
        sub = cusp.get("sub_lord", "") if isinstance(cusp, dict) else ""
        if not sub:
            continue
        p = significator_strength(sub, PROTECT_HOUSES, payload)
        l = significator_strength(sub, LOSS_HOUSES, payload)
        per_cusp[f"H{hnum}"] = {"sub_lord": sub, "protect": round(p, 3), "loss": round(l, 3)}
        # H12 is naturally an exit cusp — its loss signification is expected and
        # is not counted as a protection failure of the continuity cusps.
        if hnum in (2, 6, 10, 11):
            protect_score += p
            loss_score += l
    protection_fails = loss_score > protect_score and bool(per_cusp)
    return {
        "per_cusp": per_cusp,
        "protect_score": round(protect_score, 3),
        "loss_score": round(loss_score, 3),
        "protection_fails": protection_fails,
        "low_confidence": low_conf,
        "computable": bool(per_cusp),
    }


# ───────────────────────────────────────────────────────────────────────────
# G5 — D10 career affliction / protection
# ───────────────────────────────────────────────────────────────────────────
def d10_career_affliction(period_lords: Dict[str, str], payload: Any) -> Dict[str, Any]:
    """D10 confirmation layer: are the period lords activating D10 8/12 or
    afflicting D10 6/10, and does strong D10 6/11 protect employment?"""
    occ = getattr(payload, "d10_house_occupancy", {}) or {}
    d10_lords = getattr(payload, "d10_house_lords", {}) or {}
    d10_digs = getattr(payload, "d10_planet_dignities", {}) or {}

    def _house_occupants(h: int) -> List[str]:
        return occ.get(str(h), occ.get(f"H{h}", [])) or []

    lords = [l for l in period_lords.values() if l]
    # period lord sitting in D10 8th/12th (sudden break / exit)
    activates_8_12 = any(
        l in _house_occupants(8) or l in _house_occupants(12) for l in lords
    )
    # period lord sitting in D10 6th (service conflict) counts as pressure not exit
    activates_6 = any(l in _house_occupants(6) for l in lords)

    # D10 10th lord / D10 lagna lord afflicted
    d10_10_lord = d10_lords.get("10", d10_lords.get("H10", ""))
    d10_1_lord = d10_lords.get("1", d10_lords.get("H1", ""))

    def _afflicted(planet: str) -> bool:
        return str(d10_digs.get(planet, "")).upper() in _AFFLICTED_DIGNITIES

    tenth_afflicted = bool(d10_10_lord) and _afflicted(d10_10_lord)
    lagna_afflicted = bool(d10_1_lord) and _afflicted(d10_1_lord)

    # Protection: benefic occupancy of D10 6/11 with a non-afflicted lord.
    # GAP-FIX (2026-08-22): previously any occupant of D10 6/11 counted as
    # "protective" as long as the house LORD wasn't afflicted, without
    # checking whether the occupant itself was a malefic. A malefic sitting
    # in the 6th/11th is not classically protective merely because the house
    # lord is undamaged. Now requires at least one non-malefic occupant.
    d10_6_lord = d10_lords.get("6", d10_lords.get("H6", ""))
    d10_11_lord = d10_lords.get("11", d10_lords.get("H11", ""))
    occ_6_benefic = [p for p in _house_occupants(6) if p not in _MALEFICS]
    occ_11_benefic = [p for p in _house_occupants(11) if p not in _MALEFICS]
    protects = (
        (bool(occ_6_benefic) and bool(d10_6_lord) and not _afflicted(d10_6_lord))
        or (bool(occ_11_benefic) and bool(d10_11_lord) and not _afflicted(d10_11_lord))
    )

    afflicted = activates_8_12 or tenth_afflicted or lagna_afflicted
    computable = bool(occ or d10_lords or d10_digs)
    return {
        "activates_8_12": activates_8_12,
        "activates_6": activates_6,
        "tenth_lord_afflicted": tenth_afflicted,
        "lagna_lord_afflicted": lagna_afflicted,
        "protects": protects,
        "afflicted": afflicted,
        "computable": computable,
    }


# ───────────────────────────────────────────────────────────────────────────
# G6 — transit triggers over the natal / D10 career axis
# ───────────────────────────────────────────────────────────────────────────
def transit_career_triggers(payload: Any, flags: List[str]) -> Dict[str, Any]:
    """Detect Saturn/Rahu/Ketu pressure over the career axis. Transits only
    *trigger* — the caller must confirm a dasha promise before escalating."""
    tp = getattr(payload, "transit_house_positions", {}) or {}
    ph = getattr(payload, "planet_house", {}) or {}
    h10_lord = getattr(payload, "h10_lord", "") or getattr(payload, "h10_lord_planet", "")
    hl = getattr(payload, "house_lords", {}) or {}
    sixth_lord = hl.get("6", hl.get("H6", ""))
    second_lord = hl.get("2", hl.get("H2", ""))

    triggers: List[str] = []

    # Saturn pressure zones
    sat_h = tp.get("Saturn", 0)
    if sat_h in (8, 10, 12):
        triggers.append(f"SATURN_TRANSIT_H{sat_h}")
    # Nodes are the sudden-shock triggers
    for node in ("Rahu", "Ketu"):
        nh = tp.get(node, 0)
        if nh in (1, 4, 7, 10, 6, 12):
            triggers.append(f"{node.upper()}_TRANSIT_H{nh}")

    # Transit over the natal 10th lord (career restructuring / detachment)
    if h10_lord:
        h10_lord_house = ph.get(h10_lord, 0)
        for planet in ("Saturn", "Rahu", "Ketu"):
            if h10_lord_house and tp.get(planet, 0) == h10_lord_house:
                triggers.append(f"{planet.upper()}_OVER_H10_LORD")
    # Node over 6th / 2nd lord (service conflict / salary hit)
    for lord, tag in ((sixth_lord, "H6_LORD"), (second_lord, "H2_LORD")):
        if lord:
            lh = ph.get(lord, 0)
            for node in ("Rahu", "Ketu"):
                if lh and tp.get(node, 0) == lh:
                    triggers.append(f"{node.upper()}_OVER_{tag}")
    # Saturn over natal Sun / Moon (authority pressure / emotional heaviness)
    for lum in ("Sun", "Moon"):
        lh = ph.get(lum, 0)
        if lh and tp.get("Saturn", 0) == lh:
            triggers.append(f"SATURN_OVER_{lum.upper()}")

    # Fold in transit flags the timeline already produced
    for f in (flags or []):
        if any(k in f for k in ("SATURN_H8", "SATURN_H9", "SATURN_H12",
                                "RAHU", "KETU", "SADE_SATI",
                                "SAT_TRANSIT_ASPECT_H10_LORD")):
            triggers.append(f)

    triggers = sorted(set(triggers))
    return {"triggers": triggers, "present": bool(triggers)}


# ───────────────────────────────────────────────────────────────────────────
# G12 — Jupiter protection (loss -> change with continuity)
# ───────────────────────────────────────────────────────────────────────────
def jupiter_protects(payload: Any) -> Dict[str, Any]:
    """True when transit Jupiter supports 2/6/10/11 (natal), by occupancy or
    by its 5th/7th/9th aspect."""
    tp = getattr(payload, "transit_house_positions", {}) or {}
    jup_h = tp.get("Jupiter", 0)
    if not jup_h:
        return {"protects": False, "computable": False}
    aspected = {jup_h}
    for off in (4, 6, 8):                       # 5th, 7th, 9th houses from Jupiter
        aspected.add(((jup_h - 1 + off) % 12) + 1)
    protects = bool(aspected & PROTECT_HOUSES)
    return {"protects": protects, "aspected": sorted(aspected), "computable": True}


# ───────────────────────────────────────────────────────────────────────────
# G7 — Ashtakavarga severity multiplier
# ───────────────────────────────────────────────────────────────────────────
def av_severity(payload: Any) -> Dict[str, Any]:
    """SAV-based severity scaler for the career axis. (BAV of the transiting
    planet in its sign would sharpen this further but is not on the payload;
    SAV of 10/6/11/2/8/12 is the faithful subset available today.)"""
    sav = getattr(payload, "sav_points_houses", {}) or {}

    def _sav(h: int) -> float:
        return float(sav.get(str(h), sav.get(f"H{h}", 0.0)) or 0.0)

    if not sav:
        return {"multiplier": 1.0, "computable": False}
    tenth = _sav(10)
    eleventh = _sav(11)
    # Baseline house average ≈ 28. Below → fragile, above → resilient.
    sev = 1.0
    if tenth and tenth < 26:
        sev += 0.20
    if eleventh and eleventh >= 32:
        sev -= 0.20                              # strong gain house → recovery buffer
    sev = max(0.7, min(1.3, sev))
    return {"multiplier": round(sev, 3), "sav_h10": tenth, "sav_h11": eleventh,
            "computable": True}


# ───────────────────────────────────────────────────────────────────────────
# G8 — Jaimini status-risk (A10 / AmK)
# ───────────────────────────────────────────────────────────────────────────
def jaimini_status_risk(payload: Any) -> Dict[str, Any]:
    """Status/image loss: malefics or nodes on A10 (Karma Pada), afflicted
    Amatyakaraka, or afflicted lord of 8th/12th from A10."""
    a10 = getattr(payload, "a10_sign", "") or ""
    signs = getattr(payload, "planet_signs", {}) or {}
    digs = getattr(payload, "true_planet_dignities", None) or getattr(payload, "planet_dignities", {}) or {}
    amk = getattr(payload, "amatyakaraka", "") or ""

    reasons: List[str] = []
    if a10 and a10 in _SIGN_IDX:
        # malefic / node tenanting A10
        for planet, sign in signs.items():
            if sign == a10 and planet in _MALEFICS:
                reasons.append(f"{planet}_ON_A10")
        # lord of 8th / 12th from A10 afflicted
        idx = _SIGN_IDX[a10]
        for off, tag in ((7, "8TH_FROM_A10"), (11, "12TH_FROM_A10")):
            sgn = _SIGN_ORDER[(idx + off) % 12]
            lord = _SIGN_LORD.get(sgn, "")
            if lord and str(digs.get(lord, "")).upper() in _AFFLICTED_DIGNITIES:
                reasons.append(f"{tag}_LORD_AFFLICTED")
    if amk and str(digs.get(amk, "")).upper() in _AFFLICTED_DIGNITIES:
        reasons.append("AMATYAKARAKA_AFFLICTED")

    return {"status_risk": bool(reasons), "reasons": sorted(set(reasons)),
            "computable": bool(a10 or amk)}


# ───────────────────────────────────────────────────────────────────────────
# G9 — Varshaphala annual pressure (lightweight, Muntha-based)
# ───────────────────────────────────────────────────────────────────────────
def varshaphala_year_pressure(payload: Any, age: Optional[float] = None) -> Dict[str, Any]:
    """Muntha house for the current solar year. Muntha in 6/8/12 = pressure
    year, in a kendra/trikona = supportive. Delegates to jyotish/varshaphala.py's
    full solar-return chart (Sahams + Mudda dasha included, see
    `full_varshaphala` in the returned dict) whenever it's computable; falls
    back to a lagna-only Muntha estimate (no Sahams/Mudda) when the full
    ephemeris-backed computation isn't available (e.g. Skyfield/DE421 not
    installed, or a transient ephemeris failure -- see
    varshaphala.py::compute_varshaphala's own try/except guards)."""
    try:
        from datetime import date as _date
        from .varshaphala import compute_varshaphala
        full = compute_varshaphala(payload, _date.today().year)
        if str(full.get("status", "")).startswith("COMPUTED"):
            return {"verdict": full["verdict"], "computable": True,
                    "muntha_house": full["muntha"]["house"], "full_varshaphala": full}
    except Exception:
        pass
    lagna = getattr(payload, "lagna_sign", "") or ""
    if age is None:
        age = float(getattr(payload, "current_age", 0.0) or 0.0)
    if lagna not in _SIGN_IDX or age <= 0:
        return {"verdict": "neutral", "computable": False}
    muntha_house = (int(age) % 12) + 1          # Muntha advances 1 house/year from lagna
    if muntha_house in (6, 8, 12):
        verdict = "pressure"
    elif muntha_house in (1, 4, 5, 7, 9, 10):
        verdict = "supportive"
    else:
        verdict = "neutral"
    return {"verdict": verdict, "muntha_house": muntha_house, "computable": True}


# ───────────────────────────────────────────────────────────────────────────
# G11 — multi-layer confirmation ledger (5-of-7 gate)
# ───────────────────────────────────────────────────────────────────────────
_REQUIRED_LAYERS = ("dba_loss_signature", "kp_protection_fails", "d10_afflicted")


def jobloss_confirmation_ledger(
    period_lords: Dict[str, str],
    payload: Any,
    flags: List[str],
    known_events_present: bool = False,
    retro_validated: Optional[bool] = None,
) -> Dict[str, Any]:
    """Collect one boolean per independent layer and map the tally to a label.

    Framework rule: >=5 confirmations (with the 3 required layers true) = high
    job-loss risk; 3-4 = job-change/restructuring risk; <=2 = pressure only.
    """
    balance = compute_jobloss_balance(period_lords, payload)
    kp = kp_job_promise(payload)
    d10 = d10_career_affliction(period_lords, payload)
    transits = transit_career_triggers(payload, flags)
    jup = jupiter_protects(payload)
    varsha = varshaphala_year_pressure(payload)
    jaimini = jaimini_status_risk(payload)

    layers: Dict[str, Optional[bool]] = {
        "dba_loss_signature": balance["net"] > 0.10 and balance["loss_overpowers"],
        "kp_protection_fails": kp["protection_fails"],
        "d10_afflicted": d10["afflicted"] and not d10["protects"],
        "transit_trigger": transits["present"],
        "jupiter_not_protecting": not jup["protects"],
        "varshaphala_pressure": varsha["verdict"] == "pressure",
        "jaimini_status_risk": jaimini["status_risk"],
    }
    # Retro-validation replaces jaimini as the 7th layer when past events exist.
    if known_events_present and retro_validated is not None:
        layers["retro_validated"] = bool(retro_validated)

    votes = sum(1 for v in layers.values() if v is True)
    required_met = all(layers.get(k) is True for k in _REQUIRED_LAYERS)

    if required_met and votes >= 5:
        label = "high_job_loss_risk"
    elif votes >= 3:
        label = "job_change_or_restructuring_risk"
    else:
        label = "pressure_only"

    from jyotish.validation_contract import UNIVERSAL_DISCLAIMER, evidence_status
    return {
        "label": label,
        "votes": votes,
        "required_met": required_met,
        "layers": layers,
        "balance": balance,
        "kp": kp,
        "d10": d10,
        "transits": transits,
        "jupiter": jup,
        "varshaphala": varsha,
        "jaimini": jaimini,
        "av_severity": av_severity(payload),
        "validation_status": evidence_status(inputs_complete=True, computed=True),
        "score_semantics": "RULE_VOTE_NOT_EMPIRICAL_PROBABILITY",
        "disclaimer": UNIVERSAL_DISCLAIMER,
    }


# ───────────────────────────────────────────────────────────────────────────
# G1 — adverse-event classifier (public entry point)
# ───────────────────────────────────────────────────────────────────────────
def classify_adverse_event(
    scores: Dict[str, Any],
    flags: List[str],
    payload: Any,
    active_h: Set[int],
    coarse_adverse: bool = False,
    known_events_present: bool = False,
    retro_validated: Optional[bool] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Decide the adverse career event, or return (None, ledger) to defer.

    Returns a concrete event only when the evidence justifies it:
      * label == high                 -> JOB_LOSS / FORCED_EXIT / BURNOUT_EXIT
      * coarse_adverse and label==mid -> ROLE_RESTRUCTURING / JOB_CHANGE
    Otherwise returns None so the caller can fall through (RISK_PERIOD or a
    positive event). This conservative gate keeps clean/positive periods —
    which never reach a high label — completely unaffected.
    """
    period_lords = {
        "md": scores.get("_md_lord", ""),
        "ad": scores.get("_ad_lord", ""),
        "pd": getattr(payload, "pratyantar_dasha_lord", "") or "",
    }
    ledger = jobloss_confirmation_ledger(
        period_lords, payload, flags,
        known_events_present=known_events_present,
        retro_validated=retro_validated,
    )
    label = ledger["label"]
    active_h = set(active_h or set())
    lords = {v for v in period_lords.values() if v}

    # Burnout signature: 6/8/12 emphasis with Moon/Saturn/Ketu in the mix.
    burnout_axis = bool(active_h & {6, 8, 12})
    burnout_planets = bool(lords & _BURNOUT_PLANETS)
    burnout_flag = any("SADE_SATI" in f or "STRESS" in f or "BURDEN" in f for f in (flags or []))

    if label == "high_job_loss_risk":
        # G12: Jupiter still protecting continuity -> forced change, not unemployment.
        if ledger["jupiter"]["protects"] or ledger["d10"]["protects"]:
            return ("FORCED_EXIT", ledger)
        if burnout_axis and burnout_planets and burnout_flag:
            return ("BURNOUT_EXIT", ledger)
        return ("JOB_LOSS", ledger)

    if coarse_adverse and label == "job_change_or_restructuring_risk":
        # 6/10 active with an 8th-house shock, same-employer -> restructuring.
        if 8 in active_h and bool(active_h & {6, 10}):
            return ("ROLE_RESTRUCTURING", ledger)
        return ("JOB_CHANGE", ledger)

    return (None, ledger)


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTION-GRADE MULTI-EVENT SCORING (Enhancement Plan Phase 1, P0)
# ---------------------------------------------------------------------------
# Turns the qualitative loss/protection read into a declarative multi-event
# 0-100 scoring matrix + deterministic classifier + evidence ledger + numeric
# guardrails. Runs entirely over data already on the payload.
# ═══════════════════════════════════════════════════════════════════════════
import math as _math

# Declarative Career Event Scoring Matrix. Positive weights push the event's
# score up when the operating DBA lords signify that house; negative weights
# (protection / gain houses) push it down. Calibrated from the pasted design.
EVENT_HOUSE_WEIGHTS: Dict[str, Dict[int, float]] = {
    "job_loss": {
        5: 1.20, 8: 1.35, 9: 1.00, 12: 1.40,
        2: -1.20, 6: -1.35, 10: -1.25, 11: -1.40,
    },
    "job_change": {
        3: 1.25, 10: 1.00, 11: 1.10, 12: 0.85, 2: 0.60, 6: 0.80,
    },
    "role_restructuring": {
        6: 1.00, 8: 1.10, 10: 1.00, 12: 0.60, 11: -0.70,
    },
    "career_plateau": {
        10: 0.70, 6: 0.80, 8: 0.60, 12: 0.50, 11: -1.20,
    },
    "continuity": {
        2: 1.20, 6: 1.25, 10: 1.10, 11: 1.40,
        5: -0.80, 8: -0.90, 12: -1.00,
    },
    "recovery": {
        2: 1.20, 6: 1.25, 10: 1.10, 11: 1.40,
        5: -0.80, 8: -0.90, 12: -1.00,
    },
}

# Logistic squash scale: raw weighted sums for a strong single-theme chart land
# around ±4-6, so a scale of 3.0 maps neutral->50, strong->~80, protected->~18.
_SCORE_SCALE = 3.0


def _squash_0_100(raw: float, scale: float = _SCORE_SCALE) -> float:
    """Bounded logistic map raw signed sum -> 0..100 (neutral raw 0 -> 50)."""
    try:
        return round(100.0 / (1.0 + _math.exp(-raw / scale)), 1)
    except OverflowError:
        return 0.0 if raw < 0 else 100.0


def period_house_vector(period_lords: Dict[str, str], payload: Any) -> Dict[int, float]:
    """Normalized house-signification vector for the operating DBA lords.

    For every house 1..12, sum each lord's KP-hierarchy signification strength
    (occupancy>star>sub>owner) weighted by dasha role (MD>AD>PD).
    """
    vec: Dict[int, float] = {}
    for role, lord in period_lords.items():
        if not lord:
            continue
        rw = _ROLE_WEIGHTS.get(role, 0.5)
        for h in range(1, 13):
            s = significator_strength(lord, {h}, payload)
            if s:
                vec[h] = vec.get(h, 0.0) + s * rw
    return vec


def planet_signification_vector(planet: str, payload: Any) -> Dict[str, Any]:
    """Per-planet normalized house vector + dominant theme (design artifact #4)."""
    signifies: Dict[int, float] = {}
    for h in range(1, 13):
        s = significator_strength(planet, {h}, payload)
        if s:
            signifies[h] = round(s, 3)
    loss = sum(v for h, v in signifies.items() if h in LOSS_HOUSES)
    protect = sum(v for h, v in signifies.items() if h in PROTECT_HOUSES)
    if loss > protect * 1.15:
        theme = "loss_or_exit_pressure"
    elif protect > loss * 1.15:
        theme = "continuity_or_gain"
    else:
        theme = "mixed"
    return {"planet": planet, "signifies": signifies, "dominant_theme": theme}


def compute_event_scores(period_lords: Dict[str, str], payload: Any,
                         jupiter_protect: bool = False) -> Dict[str, float]:
    """Every career event as a comparable 0-100 score from the weight matrix."""
    vec = period_house_vector(period_lords, payload)
    scores: Dict[str, float] = {}
    for event, weights in EVENT_HOUSE_WEIGHTS.items():
        raw = sum(w * vec.get(h, 0.0) for h, w in weights.items())
        scores[event] = _squash_0_100(raw)
    # Recovery gets a Jupiter-protection uplift (design: Jupiter opens next door).
    if jupiter_protect:
        scores["recovery"] = round(min(100.0, scores["recovery"] + 12.0), 1)
    return scores


def _layer_sub_scores(period_lords: Dict[str, str], payload: Any,
                      ledger: Dict[str, Any]) -> Dict[str, float]:
    """Per-layer 0-100 sub-scores the guardrail and the D10 object require."""
    bal = ledger["balance"]
    kp = ledger["kp"]
    d10 = ledger["d10"]

    # KP loss: how far the continuity cusps tilt to loss over protection.
    kp_loss = _squash_0_100(kp["loss_score"] - kp["protect_score"], scale=1.5)
    # Dasha loss: the balance net already in [-1,1]; stretch to 0-100.
    dasha_loss = round(max(0.0, min(100.0, (bal["net"] + 1.0) * 50.0)), 1)
    # D10 break vs restructuring vs stability from the affliction booleans.
    d10_break = 0.0
    if d10.get("activates_8_12"):
        d10_break += 55.0
    if d10.get("tenth_lord_afflicted"):
        d10_break += 25.0
    if d10.get("lagna_lord_afflicted"):
        d10_break += 20.0
    d10_break = round(min(100.0, d10_break), 1)
    d10_restructuring = round(min(100.0,
        (60.0 if d10.get("activates_6") else 0.0)
        + (25.0 if d10.get("tenth_lord_afflicted") else 0.0)
        + (15.0 if d10.get("activates_8_12") else 0.0)), 1)
    d10_stability = round(max(0.0, 100.0 - d10_break) * (1.15 if d10.get("protects") else 1.0), 1)
    d10_stability = min(100.0, d10_stability)
    return {
        "kp_loss_score": kp_loss,
        "dasha_loss_score": dasha_loss,
        "d10_break_score": d10_break,
        "d10_restructuring_score": d10_restructuring,
        "d10_stability_score": d10_stability,
    }


def severity_level(loss_score: float, confirmation_count: int) -> str:
    """Named severity from the loss score reinforced by layer agreement."""
    if loss_score >= 75 and confirmation_count >= 5:
        return "severe"
    if loss_score >= 65 and confirmation_count >= 4:
        return "high"
    if loss_score >= 55 or confirmation_count >= 3:
        return "moderate"
    return "mild"


def recovery_window(scores: Dict[str, float]) -> Dict[str, Any]:
    """Whether a new-opportunity/recovery window is present after disturbance."""
    rec = scores.get("recovery", 0.0)
    return {"present": rec >= 60.0, "recovery_score": rec}


_CONFIDENCE_BANDS = {
    0: "pressure_only", 1: "pressure_only", 2: "pressure_only",
    3: "watch_period", 4: "moderate_risk",
    5: "high_risk", 6: "very_high_risk", 7: "very_high_risk",
}


def can_predict_job_loss(report: Dict[str, Any]) -> bool:
    """Explicit numeric guardrail (design #9). Job loss may only be asserted
    when independent layers AND the hard sub-score thresholds all pass."""
    return (
        report.get("confirmation_count", 0) >= 5
        and report.get("kp_loss_score", 0) >= 70
        and report.get("dasha_loss_score", 0) >= 65
        and report.get("d10_break_score", 0) >= 60
        and report.get("continuity_score", 100) < 50
    )


def build_evidence_ledger(scores: Dict[str, float], vec: Dict[int, float],
                          ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-event `{rule, source, weight, impact}` explanation entries."""
    out: List[Dict[str, Any]] = []
    for event, weights in EVENT_HOUSE_WEIGHTS.items():
        for h, w in weights.items():
            contrib = w * vec.get(h, 0.0)
            if abs(contrib) < 0.05:
                continue
            out.append({
                "event": event,
                "rule": f"H{h} signification",
                "source": "DBA significators (KP hierarchy)",
                "weight": round(w, 2),
                "impact": round(contrib, 2),
            })
    # Layer-level evidence from the confirmation ledger.
    for layer, val in (ledger.get("layers") or {}).items():
        if val:
            out.append({"event": "confirmation", "rule": layer,
                        "source": "confirmation_ledger", "weight": 1.0, "impact": "+1 vote"})
    out.sort(key=lambda e: -abs(e["impact"]) if isinstance(e["impact"], (int, float)) else 0)
    return out


def _classify_from_scores(scores: Dict[str, float], report: Dict[str, Any],
                          ledger: Dict[str, Any]) -> str:
    """Deterministic event label over explicit 0-100 scores (design #3)."""
    loss = scores["job_loss"]; change = scores["job_change"]
    restr = scores["role_restructuring"]; plateau = scores["career_plateau"]
    cont = scores["continuity"]; rec = scores["recovery"]

    if can_predict_job_loss(report):
        if rec >= 60:
            return "Temporary Disruption Followed by Recovery"
        if ledger["jupiter"]["protects"] or ledger["d10"]["protects"]:
            return "Forced Role Change"
        return "Job Loss / Break"
    if change >= 70 and cont >= 55:
        return "Job Change With Continuity"
    if restr >= 65 and cont >= 50:
        return "Forced Role Restructuring"
    if cont >= 70 and loss < 50:
        return "Job Continues Despite Pressure"
    if plateau >= 60 and change < 60 and loss < 55:
        return "Career Plateau"
    if loss >= 60 and rec >= 60:
        return "Temporary Disruption Followed by Recovery"
    return "Career Pressure / Watch Period"


def career_risk_report(scores_ctx: Dict[str, Any], flags: List[str], payload: Any,
                       active_h: Optional[Set[int]] = None,
                       known_events_present: bool = False,
                       retro_validated: Optional[bool] = None) -> Dict[str, Any]:
    """Aggregator: full multi-event career-risk object for one period.

    Ties together the event-score matrix, the confirmation ledger (confidence),
    per-layer sub-scores, severity, recovery, the numeric guardrail, and an
    evidence ledger — the single artifact the report/API/UI layers consume.
    """
    period_lords = {
        "md": scores_ctx.get("_md_lord", ""),
        "ad": scores_ctx.get("_ad_lord", ""),
        "pd": getattr(payload, "pratyantar_dasha_lord", "") or "",
    }
    ledger = jobloss_confirmation_ledger(
        period_lords, payload, flags,
        known_events_present=known_events_present, retro_validated=retro_validated,
    )
    jupiter_protect = ledger["jupiter"]["protects"]
    event_scores = compute_event_scores(period_lords, payload, jupiter_protect=jupiter_protect)
    sub = _layer_sub_scores(period_lords, payload, ledger)
    vec = period_house_vector(period_lords, payload)

    confirmation_count = ledger["votes"]
    confidence_band = _CONFIDENCE_BANDS.get(confirmation_count, "very_high_risk")

    report = {
        # per-event scores (0-100)
        "job_loss_score": event_scores["job_loss"],
        "job_change_score": event_scores["job_change"],
        "role_restructuring_score": event_scores["role_restructuring"],
        "career_plateau_score": event_scores["career_plateau"],
        "continuity_score": event_scores["continuity"],
        "recovery_score": event_scores["recovery"],
        # per-layer sub-scores
        **sub,
        # confidence / meta
        "confirmation_count": confirmation_count,
        "confidence_band": confidence_band,
        "ledger_label": ledger["label"],
    }
    report["severity"] = severity_level(event_scores["job_loss"], confirmation_count)
    report["recovery_window"] = recovery_window(event_scores)
    report["can_call_job_loss"] = can_predict_job_loss(report)
    report["final_event_type"] = _classify_from_scores(event_scores, report, ledger)
    report["evidence"] = build_evidence_ledger(event_scores, vec, ledger)
    report["av_severity_multiplier"] = ledger["av_severity"]["multiplier"]
    report["layers"] = ledger["layers"]
    return report

# End of production-grade multi-event scoring (Enhancement Plan Phase 1).
