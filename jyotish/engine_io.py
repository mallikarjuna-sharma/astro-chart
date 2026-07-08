"""JyotishAI — JSON payload parser, course registry loader, aptitude scorer."""
import json, os
from datetime import datetime, date
from typing import Dict, List, Tuple, Set, Any, Optional

from .payload import NatalPayloadV2, logger
from .constants import DOMAIN_STRATEGIES, _SIGN_LORD
from .astro import (
    compute_dignity, _planet_abs_degree, _compute_whole_sign_houses,
    _detect_neecha_bhanga, _detect_yogas, _detect_planetary_war,
    _compute_eff_strengths, _is_vargottama, _detect_combust_planets, _calc_age,
    get_nakshatra_from_longitude,
)

from .constants import (
    _NODAL_DEFAULT_VIRUPAS, _PLANET_MIN_SHADBALA, _SIGN_NUM,
    _SIGN_LORD, _KARAKAMSHA_OCCUPANT_KW,
)
from .affinity import (
    BRANCH_PLANET_AFFINITY,
    SPACE_AEROSPACE_REGISTRY_EXTENSIONS,
    LIFE_SCIENCE_REGISTRY_EXTENSIONS,
)

_REGISTRY_ALIASES: Dict[str, Tuple[str, ...]] = {
    "astronautical_engineering": ("astronautics_engineering", "spacecraft_engineering"),
    "aerospace_engineering": ("aeronautical_engineering",),
    "space_systems_engineering": ("space_science_engineering", "space_systems"),
    "space_sciences_engineering": ("space_science_engineering",),
    "planetary_science": ("planetary_sciences", "planetary_studies"),
    "public_health": ("public_health_medicine", "community_medicine"),
    "psychiatry": ("psychiatric_medicine", "mental_health_psychiatry"),
    "medical_research": ("biomedical_research", "clinical_research"),
}


def _build_kp_significators(planet_house: Dict[str, int], kp_cusps: Dict[str, Dict]) -> Dict[str, Dict[str, List[int]]]:
    """Synthesize a minimal KP significator map when one is not supplied.

    Some generated stress-test payloads only provide cusp metadata. The engine
    still requires a non-empty kp_significators block, so we derive a stable
    fallback from the cusp lordships and the planets' whole-sign houses.
    """
    significators: Dict[str, Dict[str, List[int]]] = {}

    def _ensure(planet: str) -> Dict[str, List[int]]:
        if planet not in significators:
            significators[planet] = {
                "level_1": [],
                "level_2": [],
                "level_3": [],
                "level_4": [],
            }
        return significators[planet]

    for planet, house in planet_house.items():
        if planet and house:
            _ensure(planet)["level_1"].append(int(house))

    for cusp_key, cusp in (kp_cusps or {}).items():
        if not isinstance(cusp, dict):
            continue
        try:
            house_num = int(cusp_key[1:]) if cusp_key.startswith("H") else int(cusp_key)
        except (TypeError, ValueError):
            continue
        for key, level in (("sign_lord", "level_1"), ("star_lord", "level_2"), ("sub_lord", "level_3"), ("sub_sub_lord", "level_4")):
            planet = cusp.get(key, "")
            if planet:
                _ensure(planet)[level].append(house_num)

    return {planet: levels for planet, levels in significators.items() if any(levels.values())}


def parse_json_payload(data, student_name="Unknown", build_timeline: bool = False) -> NatalPayloadV2:
    pyh = data.get("pyhora_calculations", {})
    ctx = data.get("student_context", {})
    sys_cfg = data.get("system_config", {})
    if student_name in ("Unknown", "Student", ""):
        student_name = (
            ctx.get("student_name")
            or ctx.get("name")
            or ctx.get("Name")
            or (data.get("user_info") or {}).get("display_name")
            or data.get("profile_name")
            or student_name
        )
    
    lagna_sign = pyh.get("d1_lagna", "")
    lagna_deg  = pyh.get("d1_lagna_degree", 15.0) 
    planets_d1 = pyh.get("planets_d1", {})
    
    planet_retrograde = {p: bool(planets_d1[p].get("is_retrograde", False)) for p in planets_d1}
    
    sun_data = planets_d1.get("Sun", {})
    sun_abs = _planet_abs_degree(sun_data.get("sign","Aries"), sun_data.get("degree",0))
    combust_planets, cazimi_planets = _detect_combust_planets(planets_d1, sun_abs, planet_retrograde)
    
    # ASTRO-8: Dynamic Equal House Bhava Chalit
    # GAP-5: If system_config["house_system"] == "pyhora_provided", use pyhora's
    # planet_house_positions directly instead of recomputing Bhava Chalit.
    _house_system = sys_cfg.get("house_system", "bhava_chalit")
    if _house_system == "pyhora_provided":
        _raw_php = pyh.get("planet_house_positions", {})
        # Normalise: values may be ints or dicts {"house": N, ...}
        planet_house = {}
        for _p, _v in _raw_php.items():
            if isinstance(_v, dict):
                planet_house[_p] = int(_v.get("house", 0))
            else:
                try:
                    planet_house[_p] = int(_v)
                except (TypeError, ValueError):
                    planet_house[_p] = 0
        logger.info("GAP-5: Using pyhora_provided house positions (%d planets)", len(planet_house))
    else:
        planet_house = _compute_whole_sign_houses(planets_d1, lagna_sign)
    
    shadbala = {p: planets_d1[p]["shadbala_virupas"] for p in planets_d1 if "shadbala_virupas" in planets_d1[p]}
    for _node in ("Rahu","Ketu"):
        if _node in planets_d1 and _node not in shadbala:
            node_sign = planets_d1[_node].get("sign", "")
            dispositor = _SIGN_LORD.get(node_sign, "")
            # ASTRO-9 FIX: Apply 0.75 proxy discount when inheriting dispositor shadbala.
            # Nodes act THROUGH their dispositor, not AS the dispositor — direct inheritance
            # caused a double-echo when the dispositor was already a Yogakaraka: Rahu was
            # getting Saturn's full raw_ratio AND Saturn's Yogakaraka func_mod simultaneously.
            # The 0.75 factor breaks this echo chain while preserving the dispositor linkage.
            shadbala[_node] = shadbala.get(dispositor, _NODAL_DEFAULT_VIRUPAS) * 0.75
    # C5: Derive eff_strengths from shadbala (shadbala/min_required ratio, capped at 2.5).
    # 1.0 = meets minimum, >1.0 = stronger, <1.0 = weaker. Used by all method scorers
    # and cluster bonuses; fixes the empty-eff_strengths bug where all cluster bonuses = 0.
    _eff_strengths_from_shadbala: Dict[str, float] = {
        _p: round(min(float(_sv) / _PLANET_MIN_SHADBALA.get(_p, 300.0), 2.5), 4)
        for _p, _sv in shadbala.items()
    }
            
    kp_cusps = pyh.get("kp_cusp_data", {})
    jaimini = pyh.get("kn_rao_jaimini_data", {})
    karakas = jaimini.get("chara_karakas", {})
    div_charts = pyh.get("divisional_charts", {})
    d10 = div_charts.get("D10_dashamsha", {})
    d9 = div_charts.get("D9_navamsha", {})
    d24 = div_charts.get("D24_siddhamsam", {})
    
    moon_data = planets_d1.get("Moon", {})
    sun_moon_diff = abs(_planet_abs_degree(moon_data.get("sign","Aries"), moon_data.get("degree",0)) - sun_abs)
    if sun_moon_diff > 180: sun_moon_diff = 360 - sun_moon_diff
    
    d9_planet_dignities = {p: compute_dignity(p, s) for p, s in d9.items() if p != "Lagna"}
    
    planet_dignities = {p: compute_dignity(p, planets_d1[p]["sign"]) for p in planets_d1 if "sign" in planets_d1[p]}
    d24_planet_dignities = {p: compute_dignity(p, s) for p, s in d24.items() if p != "Lagna"}

    house_lords_map = {str(i): kp_cusps.get(f"H{i}", {}).get("sign_lord", "") for i in range(1, 13)}
    detected_yogas = _detect_yogas(planets_d1, planet_house, planet_dignities, set(combust_planets), house_lords_map)
    
    # Apply Parivartana Dignity Upgrade BEFORE Neecha Bhanga
    for yoga in detected_yogas:
        if yoga.startswith("Parivartana_"):
            parts = yoga.split("_")
            if len(parts) == 3:
                planet_dignities[parts[1]] = "OWN"
                planet_dignities[parts[2]] = "OWN"

    # Gap-3 fix: pass Moon's house for Chandra Lagna kendra check
    _moon_h_for_nb = planet_house.get("Moon", 0)
    neecha_bhanga_set = _detect_neecha_bhanga(planet_dignities, planet_house, moon_house=_moon_h_for_nb)

    nakshatra_data = {}
    for p, details in planets_d1.items():
        if "nakshatra" in details:
            nakshatra_data[p] = details["nakshatra"]
        else:
            nakshatra_data[p] = get_nakshatra_from_longitude(_planet_abs_degree(details.get("sign","Aries"), details.get("degree",0)))

       
    
    # House occupancy for D10 consistency
    d10_house_occ = {}
    d10_lagna = d10.get("Lagna", lagna_sign)
    for p, s in d10.items():
        if p != "Lagna":
            h = ((_SIGN_NUM.get(s, 1) - _SIGN_NUM.get(d10_lagna, 1)) % 12) + 1
            d10_house_occ.setdefault(str(h), []).append(p)

    # ── D10 house lords (computed from D10 lagna via sign-lord mapping) ──────
    _D10_SIGN_NAMES = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
                       "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
    _d10_lagna_num = _SIGN_NUM.get(d10_lagna, 1)
    d10_house_lords_computed: Dict[str, str] = {}
    for _h in range(1, 13):
        _sign_idx = (_d10_lagna_num - 1 + _h - 1) % 12
        d10_house_lords_computed[str(_h)] = _SIGN_LORD.get(_D10_SIGN_NAMES[_sign_idx], "")

    # ── D10 Devata Diagnostics — four career-problem archetypes ─────────────
    # Each archetype maps to a specific D10 house/sign derivation:
    #   UNEMPLOYED       → 4th lord from Sun in D10       (career foundation)
    #   SALARY_STAGNANT  → 10th lord from Mercury in D10  (exchange/reward channel)
    #   PROMOTION_BLOCKED→ 10th lord from Jupiter in D10  (recognition/expansion)
    #   SUDDEN_HALT      → 8th lord from D10 Lagna        (hidden disruption)
    _PLANET_DEVATA: Dict[str, str] = {
        "Sun": "Shiva",  "Moon": "Parvati", "Mars": "Skanda",
        "Mercury": "Vishnu", "Jupiter": "Brahma", "Venus": "Lakshmi",
        "Saturn": "Shani", "Rahu": "Durga", "Ketu": "Ganesha",
    }
    def _nth_sign_d10(base: str, n: int) -> str:
        """Return the sign that is N-th from base (1-based Jyotish counting)."""
        _idx = _D10_SIGN_NAMES.index(base) if base in _D10_SIGN_NAMES else 0
        return _D10_SIGN_NAMES[(_idx + n - 1) % 12]

    d10_devata_diagnostics: Dict[str, Any] = {}
    _sun_d10s   = d10.get("Sun", "")
    _merc_d10s  = d10.get("Mercury", "")
    _jup_d10s   = d10.get("Jupiter", "")
    if _sun_d10s:
        _k = _nth_sign_d10(_sun_d10s, 4)
        _l = _SIGN_LORD.get(_k, "")
        d10_devata_diagnostics["unemployed"] = {
            "archetype": "UNEMPLOYED", "pivot_planet": "Sun",
            "pivot_sign_d10": _sun_d10s, "key_sign": _k, "key_lord": _l,
            "devata": _PLANET_DEVATA.get(_l, ""),
            "insight": "4th from Sun in D10 — foundation of career authority",
        }
    if _merc_d10s:
        _k = _nth_sign_d10(_merc_d10s, 10)
        _l = _SIGN_LORD.get(_k, "")
        d10_devata_diagnostics["salary_stagnant"] = {
            "archetype": "SALARY_STAGNANT", "pivot_planet": "Mercury",
            "pivot_sign_d10": _merc_d10s, "key_sign": _k, "key_lord": _l,
            "devata": _PLANET_DEVATA.get(_l, ""),
            "insight": "10th from Mercury in D10 — channel of career exchange and reward",
        }
    if _jup_d10s:
        _k = _nth_sign_d10(_jup_d10s, 10)
        _l = _SIGN_LORD.get(_k, "")
        d10_devata_diagnostics["promotion_blocked"] = {
            "archetype": "PROMOTION_BLOCKED", "pivot_planet": "Jupiter",
            "pivot_sign_d10": _jup_d10s, "key_sign": _k, "key_lord": _l,
            "devata": _PLANET_DEVATA.get(_l, ""),
            "insight": "10th from Jupiter in D10 — rightful recognition and expansion",
        }
    if d10_lagna:
        _k = _nth_sign_d10(d10_lagna, 8)
        _l = _SIGN_LORD.get(_k, "")
        d10_devata_diagnostics["sudden_halt"] = {
            "archetype": "SUDDEN_HALT", "pivot_planet": "D10_Lagna",
            "pivot_sign_d10": d10_lagna, "key_sign": _k, "key_lord": _l,
            "devata": _PLANET_DEVATA.get(_l, ""),
            "insight": "8th from D10 Lagna — hidden disruption, sudden career stop",
        }

    # ── Moon nakshatra string ─────────────────────────────────────────────────
    # nakshatra_data values may be a plain string ("Rohini") or a dict
    # {"nakshatra": "Rohini", "pada": 2, ...} depending on the JSON source.
    _moon_nak_raw = nakshatra_data.get("Moon", "")
    if isinstance(_moon_nak_raw, dict):
        _moon_nak_str = str(_moon_nak_raw.get("nakshatra") or _moon_nak_raw.get("name") or "")
    else:
        _moon_nak_str = str(_moon_nak_raw) if _moon_nak_raw else ""

    # ── Planet signs (D1) ────────────────────────────────────────────────────
    planet_signs_map: Dict[str, str] = {
        p: planets_d1[p].get("sign", "")
        for p in planets_d1
        if "sign" in planets_d1[p]
    }

    # ── Planet nakshatras (all planets, normalised to string) ────────────────
    planet_nakshatras_map: Dict[str, str] = {}
    for _pn, _nv in nakshatra_data.items():
        if isinstance(_nv, dict):
            planet_nakshatras_map[_pn] = str(_nv.get("nakshatra") or _nv.get("name") or "")
        else:
            planet_nakshatras_map[_pn] = str(_nv) if _nv else ""

    # ── Lagna nakshatra + Moon nakshatra pada ────────────────────────────────
    _lagna_abs_lon   = _planet_abs_degree(lagna_sign, lagna_deg)
    _lagna_nakshatra = get_nakshatra_from_longitude(_lagna_abs_lon)
    nakshatra_data["Lagna"] = _lagna_nakshatra   # so validator's nakshatra_data["Lagna"] resolves

    _moon_abs_lon = _planet_abs_degree(
        moon_data.get("sign", "Aries"), moon_data.get("degree", 0)
    )
    _nak_span   = 360.0 / 27
    _pada_span  = _nak_span / 4
    _moon_pada  = min(int((_moon_abs_lon % _nak_span) / _pada_span) + 1, 4)

    # ── Arudha Lagna (A1) and Karma Pada (A10) — Jaimini Arudha formula ─────
    # Arudha of house k: lord(k) sits in house h → count h steps more from h
    # → result house (2h - k - 1)%12 + 1; adjust if falls in k or 7th from k
    _SIGN_ORD12 = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
                   "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]

    def _arudha_sign(k: int) -> str:
        _lord = house_lords_map.get(str(k), "")
        if not _lord:
            return ""
        _h = planet_house.get(_lord, 0)
        if not _h:
            return ""
        _a = (2 * _h - k - 1) % 12 + 1
        _seventh = (k + 5) % 12 + 1           # 7th from k
        if _a == k or _a == _seventh:
            _a = (_a + 9) % 12 + 1            # shift 10 houses forward
        _lag_idx = _SIGN_ORD12.index(lagna_sign) if lagna_sign in _SIGN_ORD12 else 0
        return _SIGN_ORD12[(_lag_idx + _a - 1) % 12]

    _arudha_lagna_computed = _arudha_sign(1)
    _a10_sign_computed     = _arudha_sign(10)

    # ── Complete Vimshottari Dasha sequence — read from JSON, expand ADs ───────
    # The JSON's vimshottari_dasha_sequence already contains all 9 MDs from birth
    # (including pre-birth balance, e.g. Sun MD at age -3.6) with exact pyhora-
    # computed start_year / end_year / age_start / age_end boundaries.
    # We use these directly instead of recomputing from Moon longitude.
    # ADs are not in the JSON, so we expand them via standard Vimshottari ratios
    # applied to the JSON-provided MD boundaries.
    _VIMSHO_YEARS: Dict[str, float] = {
        "Sun": 6, "Moon": 10, "Mars": 7, "Rahu": 18, "Jupiter": 16,
        "Saturn": 19, "Mercury": 17, "Ketu": 7, "Venus": 20,
    }
    _VIMSHO_ORDER: List[str] = [
        "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury", "Ketu", "Venus",
    ]
    _VIMSHO_TOTAL: float = sum(_VIMSHO_YEARS.values())  # 120

    def _build_dasha_from_json(dasha_raw: List[Dict], dob_str: str):
        """Convert pyhora vimshottari_dasha_sequence to dated + age sequences.

        Returns (dated_seq, age_seq):
          dated_seq — [{planet, start_date, end_date, antardashas:[...]}]
          age_seq   — [{lord, start_age, end_age}]
        """
        from datetime import date as _dt, timedelta as _td
        _dob: Optional[_dt] = None
        for _fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                _dob = datetime.strptime(dob_str, _fmt).date()
                break
            except (ValueError, TypeError):
                pass
        if _dob is None or not dasha_raw:
            return [], []

        dated_seq: List[Dict] = []
        age_seq:   List[Dict] = []

        for _entry in dasha_raw:
            _planet    = _entry.get("md_planet") or _entry.get("planet") or ""
            _age_start = _entry.get("age_start")
            _age_end   = _entry.get("age_end")
            if not _planet or _age_start is None:
                continue

            _start_date = _dob + _td(days=int(round(float(_age_start) * 365.25)))
            if _age_end is not None:
                _end_date = _dob + _td(days=int(round(float(_age_end) * 365.25)))
            else:
                # Last MD: project forward using full duration
                _end_date = _start_date + _td(days=int(round(_VIMSHO_YEARS.get(_planet, 20) * 365.25)))

            _md_days  = max(1, (_end_date - _start_date).days)
            _start_pos = _VIMSHO_ORDER.index(_planet) if _planet in _VIMSHO_ORDER else 0

            # Expand 9 Antardashas + 9 Pratyantardashas per AD
            _ads: List[Dict] = []
            _ad_cur = _start_date
            for _j in range(9):
                _ad_lord = _VIMSHO_ORDER[(_start_pos + _j) % 9]
                _ad_days = max(1, int(round(_md_days * _VIMSHO_YEARS[_ad_lord] / _VIMSHO_TOTAL)))
                _ad_end  = min(_ad_cur + _td(days=_ad_days), _end_date)

                # Expand 9 Pratyantardashas within this AD
                _pds: List[Dict] = []
                _pd_cur = _ad_cur
                _ad_pos = _VIMSHO_ORDER.index(_ad_lord) if _ad_lord in _VIMSHO_ORDER else 0
                for _k in range(9):
                    _pd_lord = _VIMSHO_ORDER[(_ad_pos + _k) % 9]
                    _pd_days = max(1, int(round(_ad_days * _VIMSHO_YEARS[_pd_lord] / _VIMSHO_TOTAL)))
                    _pd_end  = min(_pd_cur + _td(days=_pd_days), _ad_end)
                    _pds.append({
                        "planet":     _pd_lord,
                        "start_date": _pd_cur.isoformat(),
                        "end_date":   _pd_end.isoformat(),
                    })
                    _pd_cur = _pd_end
                    if _pd_cur >= _ad_end:
                        break

                _ads.append({
                    "planet":            _ad_lord,
                    "start_date":        _ad_cur.isoformat(),
                    "end_date":          _ad_end.isoformat(),
                    "pratyantardashas":  _pds,
                })
                _ad_cur = _ad_end
                if _ad_cur >= _end_date:
                    break

            dated_seq.append({
                "planet":      _planet,
                "start_date":  _start_date.isoformat(),
                "end_date":    _end_date.isoformat(),
                "antardashas": _ads,
            })
            age_seq.append({
                "lord":      _planet,
                "start_age": round(float(_age_start), 4),
                "end_age":   round(float(_age_end), 4) if _age_end is not None else None,
            })

        return dated_seq, age_seq

    _pyh_dasha_raw = pyh.get("vimshottari_dasha_sequence", [])
    _vimshottari_dated, _dasha_age_seq = _build_dasha_from_json(
        _pyh_dasha_raw, ctx.get("dob", "")
    )

    # FIX-14: Extract transit house positions if present in JSON.
    transit_hp: Dict[str, int] = {}
    for planet, house_n in pyh.get("transit_house_positions", {}).items():
        try:
            transit_hp[planet] = int(house_n)
        except (ValueError, TypeError):
            pass

    # FIX-14: Extract pratyantar / antardasha lord if present.
    prd_lord_raw  = pyh.get("pratyantar_dasha_lord", "") or pyh.get("antardasha_lord", "")
    prd_houses_raw: List[int] = []
    if prd_lord_raw:
        prd_houses_raw = [planet_house.get(prd_lord_raw, 0)]

    maheshwara_raw = jaimini.get("jaimini_special_lords", {}).get("maheshwara", "")

    # ── Career Timeline (only built when explicitly requested via build_timeline=True) ──
    _career_ctx: dict = {}
    _career_timeline: list = []
    _mt: dict = {}          # default; overwritten if micro-timing computation runs
    _llm_context: dict = {} # default; overwritten if Phase-0 enrichment runs
    try:
        from .timeline_inputs import parse_career_context, validate_career_context
        _career_ctx  = parse_career_context(data)
        if not build_timeline:
            # Skip the expensive timeline build — will be run on demand
            raise StopIteration("timeline skipped")
        _current_age = _calc_age(ctx.get("dob",""), sys_cfg.get("current_date",""))
        _valid, _err, _mode = validate_career_context(
            _career_ctx, _current_age, lagna_sign=lagna_sign,
        )
        if not _valid:
            _career_ctx["_block_reason"] = _err
        else:
            # Build a lightweight eff_strengths proxy from Shadbala for timeline scoring.
            # Full eff_strengths (with 12 modifiers) are computed in run_engine() and used
            # for field ranking; this proxy is sufficient for dasha-period career scoring.
            _eff_proxy: Dict[str, float] = {}
            for _p, _sv in shadbala.items():
                _min_sv = _PLANET_MIN_SHADBALA.get(_p, 300.0)
                _eff_proxy[_p] = round(min(_sv / _min_sv, 2.5), 4)

            # ── Phase 0: LLM pre-scoring context enrichment ──────────────────
            # One cheap LLM call (haiku/gpt-4o-mini) that:
            #   1. Interprets career_ctx against chart basics
            #   2. Returns intent_tags (for _classify_event tiebreaker)
            #   3. Returns weight_overrides (applied in _score_period)
            #   4. Returns career_theme_str (injected into every AD narrative prompt)
            # Falls back gracefully to {} if LLM unavailable.
            _llm_context: dict = {}
            try:
                from .llm_context_enricher import enrich_career_context, build_chart_basics
                # Build a temporary minimal payload-like object for chart_basics extraction.
                # We use the partial data already parsed above (karakas, kp_cusps, etc.)
                class _PartialPayload:
                    dasha_sequence   = _dasha_age_seq  # complete birth→120 sequence
                    current_age      = _calc_age(ctx.get("dob",""), sys_cfg.get("current_date",""))
                    atmakaraka       = karakas.get("AK", "")
                    amatyakaraka     = karakas.get("AmK", "")
                    lagna_sign       = lagna_sign
                    house_lords      = {str(i): kp_cusps.get(f"H{i}", {}).get("sign_lord", "")
                                        for i in range(1, 13)}
                    detected_yogas   = []  # yogas detected later in run_engine()
                    yogas_present    = []

                _chart_basics = build_chart_basics(_career_ctx, _PartialPayload())
                _llm_context  = enrich_career_context(_career_ctx, _chart_basics)
            except Exception as _ph0_err:
                import logging as _log0
                _log0.getLogger("jyotish_engine_v11_0").debug(
                    "Phase 0 enrichment skipped: %s", _ph0_err
                )

            from .timeline import build_career_timeline, TimelineChartInput
            _career_timeline = build_career_timeline(
                TimelineChartInput(
                    dob=ctx.get("dob", ""),
                    lagna_sign=lagna_sign,
                    dasha_sequence=_dasha_age_seq,  # complete birth‚120 sequence (not pyhora partial)
                    planet_house=planet_house,
                    house_lords={str(i): kp_cusps.get(f"H{i}", {}).get("sign_lord", "") for i in range(1, 13)},
                    kp_significators=pyh.get("kp_planetary_significators", {}),
                    kp_cusps=kp_cusps,
                    transit_house_positions=transit_hp,
                    atmakaraka=karakas.get("AK", ""),
                    amatyakaraka=karakas.get("AmK", ""),
                    kn_rao_jaimini=jaimini,
                    d10_house_occupancy=d10_house_occ,
                    d10_lagna_sign=d10_lagna,
                    d10_house_lords=d10_house_lords_computed,
                    sav_points_houses=pyh.get("ashtakavarga_sav", {}),
                ),
                _eff_proxy,
                _career_ctx,
                mode=_mode,
                llm_context=_llm_context,
            )
            # ── Module 2: Micro-Timing Dashboard ──────────────────────────────────────────────────
            try:
                from datetime import date as _date
                from .micro_timing import compute_all_micro_timing as _micro
                _today = _date.today()
                _today_ym = _today.isoformat()[:7]
                _active_ad_lord = ""
                _active_pd_lord = ""
                for _b in _career_timeline:
                    if _b.get("start_date","") <= _today_ym <= _b.get("end_date",""):
                        _active_ad_lord = _b.get("ad_lord", "")
                        _pds = _b.get("pratyantardashas", [])
                        for _pd in _pds:
                            if _pd.get("start_date","") <= _today_ym <= _pd.get("end_date",""):
                                _active_pd_lord = _pd.get("pd_lord", "")
                                break
                        if not _active_pd_lord and _pds:
                            _active_pd_lord = _pds[0].get("pd_lord", "")
                        break
                if not _active_ad_lord and _career_timeline:
                    _active_ad_lord = _career_timeline[0].get("ad_lord", "")
                    _active_pd_lord = (_career_timeline[0].get("pratyantardashas") or [{}])[0].get("pd_lord", "")
                _tl_house_lords = {str(i): kp_cusps.get(f"H{i}", {}).get("sign_lord", "") for i in range(1, 13)}
                _mt = _micro(
                    today           = _today,
                    lagna_sign      = lagna_sign,
                    planet_house    = planet_house,
                    house_lords     = _tl_house_lords,
                    active_ad_lord  = _active_ad_lord or "Saturn",
                    active_pd_lord  = _active_pd_lord or "Saturn",
                    timeline_blocks = _career_timeline,
                )
            except Exception as _mt_err:
                import logging as _log2
                _log2.getLogger("jyotish_engine_v11_0").warning(f"Micro-timing skipped: {_mt_err}")
                _mt = {}
    except StopIteration:
        pass   # build_timeline=False -- timeline intentionally skipped
    except Exception as _ct_err:
        import logging as _log
        _log.getLogger("jyotish_engine_v11_0").warning(f"Career context parse skipped: {_ct_err}")
        _mt = {}

    kp_significators = pyh.get("kp_planetary_significators", {}) or _build_kp_significators(planet_house, kp_cusps)

    return NatalPayloadV2(
        name=student_name, lagna_sign=lagna_sign, lagna_lord=_SIGN_LORD.get(lagna_sign,""),
        h10_lord=kp_cusps.get("H10",{}).get("sign_lord",""), atmakaraka=karakas.get("AK",""),
        amatyakaraka=karakas.get("AmK",""), karakamsha=jaimini.get("karakamsha_sign",""),
        planet_strength={p:round(v/600,4) for p,v in shadbala.items()}, shadbala=shadbala,
        eff_strengths=_eff_strengths_from_shadbala,
        planet_house=planet_house, house_lords={str(i): kp_cusps.get(f"H{i}",{}).get("sign_lord","") for i in range(1,13)},
        yogas_present=detected_yogas, dasha_sequence=_dasha_age_seq,
        current_age=_calc_age(ctx.get("dob",""), sys_cfg.get("current_date","")),
        sun_moon_degrees_apart=round(sun_moon_diff,4),
        sav_points_houses=pyh.get("ashtakavarga_sav",{}), combust_planets=combust_planets, cazimi_planets=cazimi_planets,
        kp_significators=kp_significators, kp_cusps=kp_cusps,
        planet_dignities=planet_dignities, d24_planet_dignities=d24_planet_dignities,
        planet_retrograde=planet_retrograde, detected_yogas=detected_yogas, h5_lord=kp_cusps.get("H5",{}).get("sign_lord",""),
        amk_house=planet_house.get(karakas.get("AmK",""), 0), upapada_lagna=jaimini.get("upapada_lagna_sign",""),
        h10_lord_planet=kp_cusps.get("H10",{}).get("sign_lord",""), d9_planet_dignities=d9_planet_dignities,
        planets_d1=planets_d1, divisional_charts=div_charts, nakshatra_data=nakshatra_data,
        d9_lagna_sign=d9.get("Lagna", ""), karakamsha_occupants=[p for p, s in d9.items() if p != "Lagna" and s == jaimini.get("karakamsha_sign","")],
        neecha_bhanga_planets=list(neecha_bhanga_set), gender=ctx.get("gender", ""),
        interested_in=ctx.get("student_preference", {}).get("interested_in", []),
        already_excel_at=ctx.get("student_preference", {}).get("already_excel_at", []),
        brahma_lord=jaimini.get("jaimini_special_lords", {}).get("brahma", ""),
        d10_house_occupancy=d10_house_occ,
        d10_lagna_sign=d10_lagna,
        d10_house_lords=d10_house_lords_computed,
        moon_nakshatra=_moon_nak_str,
        vimshottari_dasha_full=_vimshottari_dated,
        matrikaraka=karakas.get("MK", ""),
        bhatrikaraka=karakas.get("BK", ""),
        putrakaraka=karakas.get("PK", ""),
        gnatikaraka=karakas.get("GnK", "") or karakas.get("GK", ""),
        darakaraka=karakas.get("DK", ""),
        planet_signs=planet_signs_map,
        planet_nakshatras=planet_nakshatras_map,
        lagna_nakshatra=_lagna_nakshatra,
        moon_nakshatra_pada=_moon_pada,
        arudha_lagna=_arudha_lagna_computed,
        a10_sign=_a10_sign_computed,
        d10_devata_diagnostics=d10_devata_diagnostics,
        transit_house_positions=transit_hp,
        pratyantar_dasha_lord=prd_lord_raw,
        prd_lord_houses=prd_houses_raw,
        maheshwara_lord=maheshwara_raw,
        dob=ctx.get("dob",""),
        career_context=_career_ctx,
        career_timeline=_career_timeline,
        kn_rao_jaimini=jaimini,
        micro_timing=_mt,
        llm_context=_llm_context,
    )

def _edu_sav_mod(sav: Dict) -> float:
    # FIX-9: H10 raised (career house primary); H11 added (income/gains); H4 reduced.
    h4  = sav.get("H4",  28); h5  = sav.get("H5",  28)
    h9  = sav.get("H9",  28); h10 = sav.get("H10", 28); h11 = sav.get("H11", 28)
    weighted = 0.10*h4 + 0.25*h5 + 0.25*h9 + 0.30*h10 + 0.10*h11
    return 1.0 + (weighted - 28) / 100


def compute_aptitude_by_domain(
    domain: str,
    raw_shadbala: Dict[str, float],
    sav_points: Dict[str, float],
    eff_strengths: Optional[Dict[str, float]] = None,
    branch_affinity_weights: Optional[Dict[str, float]] = None,
    field_id: str = "",
    payload=None,
) -> Dict[str, Any]:
    """Compute domain aptitude using hardcoded BRANCH_PLANET_AFFINITY multi-karaka weights."""
    strat = DOMAIN_STRATEGIES.get(domain.lower(), {"w1": 0.40, "w2": 0.40, "min_score": 50})

    if field_id and field_id in BRANCH_PLANET_AFFINITY:
        top = sorted(BRANCH_PLANET_AFFINITY[field_id].items(), key=lambda x: -x[1])
        p1 = top[0][0]
        p2 = top[1][0] if len(top) > 1 else top[0][0]
    elif branch_affinity_weights:
        top = sorted(branch_affinity_weights.items(), key=lambda x: -x[1])
        p1 = top[0][0] if top else "Mercury"
        p2 = top[1][0] if len(top) > 1 else "Jupiter"
    else:
        p1, p2 = "Mercury", "Jupiter"

    if eff_strengths:
        p1_str = min(eff_strengths.get(p1, 0.0), 2.0)
        p2_str = min(eff_strengths.get(p2, 0.0), 2.0)
        # Substitute a stronger p3 if p2 is near-zero
        if p2_str < 0.15 and branch_affinity_weights and len(top) > 2:
            for candidate, _ in top[2:]:
                cand_str = min(eff_strengths.get(candidate, 0.0), 2.0)
                if cand_str >= 0.20:
                    p2, p2_str = candidate, cand_str
                    break
    else:
        _min_sv = _PLANET_MIN_SHADBALA
        p1_str = min(raw_shadbala.get(p1, 0) / max(_min_sv.get(p1, 300), 1), 2.0)
        p2_str = min(raw_shadbala.get(p2, 0) / max(_min_sv.get(p2, 300), 1), 2.0)

    composite = (strat["w1"] * p1_str + strat["w2"] * p2_str) * 100

    # SAV modifier for education houses
    sav_mod = _edu_sav_mod(sav_points) if sav_points else 1.0
    composite *= sav_mod

    threshold = strat.get("min_score", 50)

    return {
        "composite_score":   round(composite, 4),
        "threshold_required": threshold,
        "meets_threshold":   composite >= threshold,
        "primary_karaka":    p1,
        "secondary_karaka":  p2,
        "p1_strength":       round(p1_str, 4),
        "p2_strength":       round(p2_str, 4),
        "sav_modifier":      round(sav_mod, 4),
        "domain":            domain,
    }


def _load_course_registry() -> Dict[str, Any]:
    """Load the India course registry JSON bundled with the package.

    Registries ship with an envelope ``{"_registry_meta": ..., "branches": {...},
    "version": ..., "total_branches": N}``. Callers expect a flat mapping of
    ``field_id -> field_meta``, so when the ``branches`` key is present we unwrap it.
    Falls back to the raw dict for legacy registries that already have a flat shape.
    """
    import pathlib, json as _json
    _here = pathlib.Path(__file__).parent
    for _fname in ("india_course_registry_v11.json", "india_course_registry_no_planets.json"):
        _path = _here / _fname
        if _path.exists():
            try:
                _data = _json.loads(_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(_data, dict) and isinstance(_data.get("branches"), dict):
                return _data["branches"]
            return _data if isinstance(_data, dict) else {}
    return {}
