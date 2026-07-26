"""JyotishAI — JSON payload parser, course registry loader, aptitude scorer."""
import functools
import json, os
from datetime import datetime, date
from typing import Dict, List, Tuple, Set, Any, Optional

from .payload import NatalPayloadV2, logger
from .constants import DOMAIN_STRATEGIES, _SIGN_LORD
from .astro import (
    compute_dignity, _planet_abs_degree, _compute_whole_sign_houses,
    _detect_neecha_bhanga, _detect_yogas, _detect_planetary_war,
    _compute_eff_strengths, _is_vargottama, _detect_combust_planets, _calc_age,
    get_nakshatra_from_longitude, compute_d10_chart,
)
from .d20_vimshamsha import compute_d20_chart  # Gap-G20 fix — see module docstring
from .ashtakavarga import compute_bav_points_str_keys, compute_pav_data  # Ported from V1.3 merge plan item 6
from .shadbala import compute_shadbala_all  # 2026-07 astrologer's audit: full six-fold Shadbala

from .constants import (
    _NODAL_DEFAULT_VIRUPAS, _PLANET_MIN_SHADBALA, _SIGN_NUM,
    _SIGN_LORD, _KARAKAMSHA_OCCUPANT_KW,
)
from .affinity import (
    BRANCH_PLANET_AFFINITY,
    SPACE_AEROSPACE_REGISTRY_EXTENSIONS,
    LIFE_SCIENCE_REGISTRY_EXTENSIONS,
)
from .pyhora_schema import (
    flat_divisional_charts,
    get_lagna_degree,
    get_lagna_sign,
    get_planets_d1,
    divisional_signs,
)

_ZODIAC_ORDER = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
]


def _SIGN_FROM_HOUSE(lagna_sign: str, house_num: int) -> str:
    """Return the zodiac sign occupying `house_num` from `lagna_sign` (whole-sign)."""
    if not lagna_sign or not house_num:
        return ""
    try:
        lagna_idx = _ZODIAC_ORDER.index(lagna_sign)
    except ValueError:
        return ""
    return _ZODIAC_ORDER[(lagna_idx + house_num - 1) % 12]


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


def parse_json_payload(data, student_name="Unknown", build_timeline: bool = False, chart_path: str = "") -> NatalPayloadV2:
    pyh = data.get("pyhora_calculations", {})
    ctx = data.get("student_context", {})
    sys_cfg = data.get("system_config", {})
    _source_sha256 = __import__("hashlib").sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    if student_name in ("Unknown", "Student", ""):
        student_name = ctx.get("student_name") or ctx.get("name") or ctx.get("Name") or student_name

    # Data-consistency safeguard (2026-07-05): this pipeline reads a single
    # chart JSON file as its one source of truth for career_context.join_date
    # and system_config.current_date. Some charts also have a sibling
    # "*_career.json" legacy/reference snapshot (e.g. Charts/lakshman_career.json)
    # that is NOT read by any code path here -- but if that sibling file exists
    # and its join_date/current_date silently drift out of sync with this
    # (authoritative) file, that is a real data-quality bug waiting to surface
    # the next time someone assumes the sibling file is live. Warn loudly
    # (not silently) whenever such a sibling is found and disagrees, so this
    # class of bug can never recur unnoticed. Best-effort only: requires the
    # caller to pass chart_path; never raises, only logs.
    if chart_path:
        try:
            import os as _os_dcs
            import json as _json_dcs
            _sibling = chart_path.replace("_chart_details.json", "_career.json")
            if _sibling != chart_path and _os_dcs.path.exists(_sibling):
                with open(_sibling, "r", encoding="utf-8") as _sib_f:
                    _sib_data = _json_dcs.load(_sib_f)
                _sib_join = (_sib_data.get("career_context", {}) or {}).get("join_date")
                _sib_today = (_sib_data.get("system_config", {}) or {}).get("current_date")
                _live_join = (data.get("career_context", {}) or {}).get("join_date")
                _live_today = sys_cfg.get("current_date")
                if _sib_join and _live_join and _sib_join != _live_join:
                    logger.warning(
                        "DATA INCONSISTENCY: %s.career_context.join_date=%s disagrees with "
                        "authoritative %s.career_context.join_date=%s -- the sibling file is "
                        "not read by the pipeline but should be kept in sync to avoid confusion.",
                        _sibling, _sib_join, chart_path, _live_join,
                    )
                if _sib_today and _live_today and _sib_today != _live_today:
                    logger.warning(
                        "DATA INCONSISTENCY: %s.system_config.current_date=%s disagrees with "
                        "authoritative %s.system_config.current_date=%s -- the sibling file is "
                        "not read by the pipeline but should be kept in sync to avoid confusion.",
                        _sibling, _sib_today, chart_path, _live_today,
                    )
        except Exception:
            pass  # best-effort only -- never let this safeguard break the real parse

    lagna_sign = get_lagna_sign(pyh)
    lagna_deg  = get_lagna_degree(pyh)
    planets_d1 = get_planets_d1(pyh)
    
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
    div_charts = flat_divisional_charts(pyh)
    _d10_upstream = divisional_signs(pyh, "D10_dashamsha")
    # Audit-2026-07 fix: D10 was previously trusted verbatim from the upstream
    # pyhora JSON with no in-repo way to verify its odd/even sign-counting —
    # a critical gap since Dashamsha carries the largest single method weight
    # (24%) of the five field-determination systems. Now computed in-house
    # from D1 longitudes (compute_d10_chart, astro.py) whenever every planet
    # has a `degree` value; falls back to the upstream chart per-planet only
    # for entries the in-house computation couldn't derive (missing degree).
    d10_inhouse = compute_d10_chart(planets_d1, lagna_sign, lagna_deg) if planets_d1 else {}
    d10_raw = dict(_d10_upstream)
    d10_raw.update(d10_inhouse)  # in-house, verifiable computation takes precedence
    # Bugfix (2026-07): compute_d10_chart() returns {"planet": {"sign": "Aries"}, ...}
    # (dict-of-dict, matching the upstream pyhora shape it's meant to replace), but
    # several downstream consumers below (d10_house_occ, _sun_d10s/_merc_d10s/_jup_d10s,
    # and elsewhere) index `d10` expecting a plain sign STRING per planet -- e.g.
    # `_SIGN_NUM.get(s, 1)` where `s` was assumed to already be "Aries", not
    # {"sign": "Aries"}. Once compute_d10_chart started populating every planet
    # in-house (previously it silently fell back to upstream strings for missing-
    # degree entries), this mismatch surfaced as `TypeError: unhashable type: 'dict'`
    # in production. `_d10_upstream` itself may also arrive as either shape
    # depending on the pyhora source, so normalize once here to a single flat
    # {"planet": "SignName"} dict; every consumer below can now assume plain strings.
    def _d10_sign_str(v):
        if isinstance(v, dict):
            return v.get("sign", "")
        return v if isinstance(v, str) else ""
    d10 = {p: _d10_sign_str(v) for p, v in d10_raw.items()}
    d9 = divisional_signs(pyh, "D9_navamsha")
    d24 = divisional_signs(pyh, "D24_siddhamsam")
    # E-1: extract D24 lagna and compute house lords for EduAlign stream score
    _D24_SIGNS = [
        "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
        "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
    ]
    _D24_SIGN_LORD = {
        "Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon",
        "Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars",
        "Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter",
    }
    d24_lagna_sign = str(d24.get("Lagna", "")) or ""
    if d24_lagna_sign and d24_lagna_sign in _D24_SIGNS:
        _d24_lagna_idx = _D24_SIGNS.index(d24_lagna_sign)
        d24_house_lords_map = {
            str(h): _D24_SIGN_LORD.get(_D24_SIGNS[(_d24_lagna_idx + h - 1) % 12], "")
            for h in range(1, 13)
        }
    else:
        d24_house_lords_map = {}

    moon_data = planets_d1.get("Moon", {})
    sun_moon_diff = abs(_planet_abs_degree(moon_data.get("sign","Aries"), moon_data.get("degree",0)) - sun_abs)
    if sun_moon_diff > 180: sun_moon_diff = 360 - sun_moon_diff
    
    # Gap fix (audit): compute_dignity() only resolves Rahu/Ketu dignity via the
    # nodal-dispositor rule ("node adopts the dignity of the lord of the sign it
    # sits in") when it is given a `planets_d1`-shaped dict to look the dispositor
    # up in. The D9/D24 calls previously passed only (planet, sign) with no such
    # dict, so Rahu/Ketu dignity in every divisional chart silently fell through to
    # "" (neutral) -- since _EXALT_SIGN/_DEBIL_SIGN/_OWN_SIGN have no node entries
    # of their own -- regardless of how well- or poorly-placed the dispositor
    # actually was within that varga. This blinded every D9/D24 cross-check
    # (knrao.py's D9 first-class signal, jaimini.py's "AK in D24" check) for any
    # field whose dominant planet is Rahu/Ketu (several tech/modern fields carry
    # Rahu at 0.35-0.40 affinity weight). Fixed by building a synthetic
    # planets_d1-shaped dict from each varga's own sign data, so the dispositor is
    # resolved using its position WITHIN that divisional chart (the classically
    # correct scope), not left unresolved.
    d9_shaped = {p: {"sign": s} for p, s in d9.items() if p != "Lagna"}
    d9_planet_dignities = {
        p: compute_dignity(p, s, d9_shaped) for p, s in d9.items() if p != "Lagna"
    }

    # GAP-FIX (2026-07-18, 19-chart top-20 audit): d10_planet_dignities was
    # declared on NatalPayloadV2 (payload.py) and read by score_dashamsha()
    # (jyotish/field_methods/dashamsha.py -- d10_digs) for every D10 dignity-
    # gated bonus (D10 lagna/H10/H9 lord dignity, D10 Raj Yoga, D10 Yogakaraka,
    # etc.), and the shadbala-varga block below (~line 1076) even had a
    # defensive locals().get("d10_planet_dignities") fallback anticipating it
    # might be missing -- but it was never actually computed anywhere in this
    # file, unlike its D9/D20/D24 counterparts immediately above/below. It
    # silently stayed at Pydantic's empty-dict default for every chart run
    # through this pipeline, degrading every dignity-gated D10 signal (only
    # occupancy/karaka-based D10 bonuses still fired). Confirmed empirically:
    # dashamsha_score was exactly 0.0 for 10 of 20 top-ranked fields on one
    # real chart whose top fields happened to route mostly through the
    # dignity-gated bonuses. Computed here using the same audited pattern as
    # D9 immediately above (nodal dispositor resolved within D10 itself, not
    # left unresolved).
    d10_shaped = {p: {"sign": s} for p, s in d10.items() if p != "Lagna" and s}
    d10_planet_dignities = {
        p: compute_dignity(p, s, d10_shaped) for p, s in d10.items() if p != "Lagna" and s
    }

    planet_dignities = {
        p: compute_dignity(p, planets_d1[p]["sign"], planets_d1, planets_d1[p].get("degree"))
        for p in planets_d1 if "sign" in planets_d1[p]
    }
    d24_shaped = {p: {"sign": s} for p, s in d24.items() if p != "Lagna"}
    d24_planet_dignities = {
        p: compute_dignity(p, s, d24_shaped) for p, s in d24.items() if p != "Lagna"
    }

    # Gap-G20 fix (2026-07 ontology audit): D20 (Vimshamsha) is referenced by
    # `_d20_vimshamsha_spiritual_calling` in boosts.py but no upstream pyhora
    # export ever includes a "D20_vimshamsha" key in divisional_charts (only
    # D9/D10/D24 are supplied) — so d20_planet_dignities was always empty and
    # that boost never fired for any chart. Computed in-house from D1
    # longitudes (same audited pattern as compute_d10_chart), same as D10's
    # own in-house fallback above.
    d20 = div_charts.get("D20_vimshamsha", {}) or compute_d20_chart(planets_d1, lagna_sign, lagna_deg)
    d20_shaped = {p: {"sign": (s.get("sign") if isinstance(s, dict) else s)} for p, s in d20.items() if p != "Lagna"}
    d20_planet_dignities = {
        p: compute_dignity(p, sd["sign"], d20_shaped) for p, sd in d20_shaped.items() if sd.get("sign")
    }

    # User-reported gap fix (2026-07): house_lords_map was derived SOLELY from
    # kp_cusps[Hn].sign_lord — if KP cuspal computation left any house's
    # sign_lord empty (partial KP data, a missing cusp, etc.), that house's
    # lordship silently came out as "", and downstream code/LLM narrative
    # would report lordships as "not available" even though Lagna is known
    # and house lordship is 100% deterministic from it (house N's sign =
    # the sign N-1 positions after Lagna's sign; that sign's ruling planet
    # is its lord — no computation depends on KP or any other divisional
    # chart). Added `_derive_house_lordships_from_lagna()` as a guaranteed
    # fallback so lordship analysis is NEVER skipped when Lagna is known.
    def _derive_house_lordships_from_lagna(lagna_sign_name: str) -> Dict[str, str]:
        _sign_order = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
                        "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
        _lagna_num = _SIGN_NUM.get(lagna_sign_name, 0)
        if not _lagna_num:
            return {}
        out: Dict[str, str] = {}
        for _h in range(1, 13):
            _sign_idx = (_lagna_num - 1 + _h - 1) % 12
            out[str(_h)] = _SIGN_LORD.get(_sign_order[_sign_idx], "")
        return out

    house_lords_map = {str(i): kp_cusps.get(f"H{i}", {}).get("sign_lord", "") for i in range(1, 13)}
    if lagna_sign and not all(house_lords_map.get(str(i)) for i in range(1, 13)):
        _derived_hl = _derive_house_lordships_from_lagna(lagna_sign)
        for _h_str, _lord in _derived_hl.items():
            if not house_lords_map.get(_h_str):
                house_lords_map[_h_str] = _lord
    detected_yogas = _detect_yogas(planets_d1, planet_house, planet_dignities, set(combust_planets), house_lords_map)
    
    # Apply Parivartana Dignity Upgrade BEFORE Neecha Bhanga
    # Gap fix (2026-07-05 audit): this loop stomps planet_dignities to literal
    # "OWN" for any planet in a mutual sign exchange, which is needed downstream
    # for the dignity-multiplier scoring in boosts.py. But that overwrite silently
    # destroyed the true natal dignity (e.g. a debilitated planet strengthened by
    # exchange would display as "OWN", which is astrologically wrong and produced
    # self-contradicting report text like "Lagna Lord Mercury — OWN" while the
    # same report separately listed "Parivartana_Jupiter_Mercury" as an active
    # yoga). Preserve the true dignity + the exchange pairing before mutating, so
    # display code can render an accurate label instead of a bare "OWN".
    true_planet_dignities = dict(planet_dignities)
    parivartana_pairs: Dict[str, str] = {}
    for yoga in detected_yogas:
        if yoga.startswith("Parivartana_"):
            parts = yoga.split("_")
            if len(parts) == 3:
                planet_dignities[parts[1]] = "OWN"
                planet_dignities[parts[2]] = "OWN"
                parivartana_pairs[parts[1]] = parts[2]
                parivartana_pairs[parts[2]] = parts[1]

    # Gap-3 fix: pass Moon's house for Chandra Lagna kendra check
    #
    # Bug fix (2026-07, deep-audit): must use `true_planet_dignities` here, NOT
    # the mutated `planet_dignities` — the Parivartana loop above just
    # overwrote any exchanged planet's dignity to "OWN" (needed for scoring),
    # which erases the "DEBILITATED" flag `_detect_neecha_bhanga` looks for.
    # Concretely: a lagna-lord debilitated in the 10th house, in exchange with
    # the 10th lord sitting in a kendra, is exactly the classical Neecha
    # Bhanga (debilitation-cancellation) case — but with the mutated dict the
    # planet no longer reads as DEBILITATED at all, so it was silently
    # dropped from neecha_bhanga_set every time a Parivartana was also
    # present, which is precisely the case where Neecha Bhanga is most often
    # relevant (a debilitated planet's dispositor sitting in a kendra is a
    # common source of both the exchange AND the cancellation simultaneously).
    _moon_h_for_nb = planet_house.get("Moon", 0)
    neecha_bhanga_set = _detect_neecha_bhanga(true_planet_dignities, planet_house, moon_house=_moon_h_for_nb)

    # Gap fix (2026-07, deep-audit): Amala Yoga ("spotless reputation via a
    # benefic in the 10th") is detected in _detect_yogas() purely by house
    # placement + combustion, with no dignity check at all — so a benefic
    # that is actually DEBILITATED in the 10th (e.g. Mercury debilitated in
    # Pisces) still gets flagged "Amala_Mercury" alongside a separate
    # "DEBILITATED" dignity label elsewhere in the same report, an
    # unresolved contradiction. Classically, Amala Yoga requires the 10th
    # occupant to be genuinely benefic in condition, not just benefic by
    # nature — a debilitated placement only counts if Neecha Bhanga
    # (debilitation-cancellation) applies. Filter here rather than in
    # _detect_yogas itself because neecha_bhanga_set isn't available until
    # after that call (Parivartana detection, which the true-dignity lookup
    # depends on, happens inside it) — this is the earliest safe point.
    detected_yogas = [
        y for y in detected_yogas
        if not (
            y.startswith("Amala_")
            and true_planet_dignities.get(y.split("_", 1)[1], "") == "DEBILITATED"
            and y.split("_", 1)[1] not in neecha_bhanga_set
        )
    ]

    # Gap fix (2026-07-05): the debilitation check above filters Amala Yoga out
    # entirely when afflicted by debilitation, but classical Amala Yoga is also
    # voided/downgraded when a natural malefic (Rahu, Ketu, Saturn, Mars, or a
    # combust condition) simply CO-OCCUPIES the same house as the benefic — a
    # separate, more common affliction than debilitation. Previously this case
    # sailed through unfiltered: a chart with (say) Ketu in the same 10th house
    # as the Amala-forming benefic still asserted the full, unqualified
    # "spotless career" yoga while a separate part of the same report narrated
    # that same house's Ketu-driven detachment/volatility — a direct
    # self-contradiction. Rather than dropping the yoga outright (the benefic
    # placement is real), relabel it "Amala_<planet>_Partial_<afflictor(s)>" so
    # downstream label/explanation code (competency_ontology._yoga_label) can
    # qualify the language instead of asserting an unblemished result.
    _NATURAL_MALEFICS_EIO = ("Rahu", "Ketu", "Saturn", "Mars")

    def _relabel_afflicted_amala(y: str) -> str:
        if not y.startswith("Amala_"):
            return y
        _benefic = y.split("_", 1)[1]
        _benefic_house = planet_house.get(_benefic, 0)
        if not _benefic_house:
            return y
        _afflictors = [
            m for m in _NATURAL_MALEFICS_EIO
            if m != _benefic and planet_house.get(m, 0) == _benefic_house
        ]
        _afflictors += [c for c in combust_planets if c == _benefic]
        if _afflictors:
            return f"Amala_{_benefic}_Partial_{'_'.join(_afflictors)}"
        return y

    detected_yogas = [_relabel_afflicted_amala(y) for y in detected_yogas]

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

    # ── Gap 0.1 fix: canonical SAV keys ──────────────────────────────────────
    # pyhora emits {"H1": 26, ..., "H12": 27}; scorers historically looked up
    # "10"/10 and silently defaulted to 28. Normalize once at ingestion to plain
    # string digits ("1".."12"); all consumers now use this canonical form.
    def _normalize_sav_keys(raw: dict) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for _k, _v in (raw or {}).items():
            _ks = str(_k).strip().upper()
            if _ks.startswith("H"):
                _ks = _ks[1:]
            if _ks.isdigit() and 1 <= int(_ks) <= 12:
                try:
                    out[str(int(_ks))] = int(_v)
                except (TypeError, ValueError):
                    continue
        return out

    _sav_normalized = _normalize_sav_keys(pyh.get("ashtakavarga_sav", {}))

    # ── Gap 0.4 fix: derive absolute longitudes, tithi, D24 occupancy ────────
    # planet_longitudes: absolute sidereal longitude (0-360) from sign + degree.
    # Enables real Gandanta detection in timeline.py (previously dead — the
    # fallback used sign midpoints which are never inside a 3°20' junction).
    _planet_longitudes: Dict[str, float] = {}
    for _lp, _lpd in (planets_d1 or {}).items():
        _lsign = (_lpd or {}).get("sign", "") if isinstance(_lpd, dict) else ""
        try:
            _ldeg = float((_lpd or {}).get("degree", 0.0))
        except (TypeError, ValueError):
            _ldeg = 0.0
        if _lsign in _SIGN_NUM:
            _planet_longitudes[_lp] = round((_SIGN_NUM[_lsign] - 1) * 30.0 + _ldeg, 4)

    # GAP-FIX (2026-07): Special Lagnas -- Ghati/Sree/Hora/Bhava Lagna and
    # Bhrigu Bindu. The ephemeris.py functions for all of these already
    # existed (get_ghati_lagna/get_sree_lagna) or were added now
    # (get_hora_lagna/get_bhava_lagna/get_bhrigu_bindu), but NONE of them
    # were ever actually called from this parser -- confirmed by grep, the
    # corresponding payload fields (ghati_lagna_sign, sree_lagna_sign,
    # hora_lagna_sign) were always "" in every prior engine run, silently
    # zeroing out the _ghati_lagna_bonus/_sree_lagna_bonus scoring functions
    # in boosts.py that already existed and expected real values. This block
    # computes all five from the raw birth dob/tob/lat/lon (already present
    # in the input JSON's student_context, just unused for this purpose) and
    # degrades to "" gracefully (no exception) if ephemeris isn't available
    # (e.g. skyfield not installed) or birth data is incomplete.
    _ghati_lagna_sign = ""
    _sree_lagna_sign = ""
    _hora_lagna_sign = ""
    _bhava_lagna_sign = ""
    _bhrigu_bindu_sign = ""
    try:
        from . import ephemeris as _ephem
        _dob_str = str(ctx.get("dob", "") or "")
        _tob_str = str(ctx.get("tob", "") or "")
        _b_lat = ctx.get("lat")
        _b_lon = ctx.get("lon")
        if _ephem.is_available() and _dob_str and _tob_str and _b_lat is not None and _b_lon is not None:
            _dt_local = datetime.strptime(f"{_dob_str} {_tob_str}", "%Y-%m-%d %H:%M:%S")
            _b_lat_f, _b_lon_f = float(_b_lat), float(_b_lon)

            _gl = _ephem.get_ghati_lagna(_dt_local, _b_lat_f, _b_lon_f)
            if _gl:
                _ghati_lagna_sign = _gl.get("sign", "")

            _lagna_abs_lon_for_sree = None
            if lagna_sign in _SIGN_NUM:
                try:
                    _lagna_abs_lon_for_sree = (_SIGN_NUM[lagna_sign] - 1) * 30.0 + float(lagna_deg)
                except (TypeError, ValueError, NameError):
                    _lagna_abs_lon_for_sree = None
            if _lagna_abs_lon_for_sree is not None:
                _sl = _ephem.get_sree_lagna(_dt_local, _b_lat_f, _b_lon_f, _lagna_abs_lon_for_sree)
                if _sl:
                    _sree_lagna_sign = _sl.get("sign", "")

            _hl = _ephem.get_hora_lagna(_dt_local, _b_lat_f, _b_lon_f)
            if _hl:
                _hora_lagna_sign = _hl.get("sign", "")

            _bl = _ephem.get_bhava_lagna(_dt_local, _b_lat_f, _b_lon_f)
            if _bl:
                _bhava_lagna_sign = _bl.get("sign", "")

        # Bhrigu Bindu is pure longitude arithmetic (Rahu/Moon midpoint) --
        # unlike the four lagnas above it needs no ephemeris/sunrise lookup,
        # so it's computed whenever Rahu+Moon longitudes are known, even if
        # skyfield/is_available() is false.
        _rahu_lon = _planet_longitudes.get("Rahu")
        _moon_lon = _planet_longitudes.get("Moon")
        if _rahu_lon is not None and _moon_lon is not None:
            _bb = _ephem.get_bhrigu_bindu(_rahu_lon, _moon_lon)
            if _bb:
                _bhrigu_bindu_sign = _bb.get("sign", "")
    except Exception as _special_lagna_exc:
        logger.info(f"Special Lagna computation unavailable, skipping: {_special_lagna_exc}")

    # birth_tithi_num: tithi = 12° Sun-Moon elongation steps (1-30).
    # Enables the P2 Panchanga tithi-lord confirmation in engine.py.
    _birth_tithi_num = 0
    if "Sun" in _planet_longitudes and "Moon" in _planet_longitudes:
        _elong = (_planet_longitudes["Moon"] - _planet_longitudes["Sun"]) % 360.0
        _birth_tithi_num = int(_elong // 12.0) + 1

    # d24_house_occupancy: whole-sign houses from D24 lagna.
    # Enables timeline d24_skill_bonus (previously always 0).
    _d24_occ_map: Dict[str, List[str]] = {}
    if d24_lagna_sign and d24_lagna_sign in _SIGN_NUM:
        _l24_num = _SIGN_NUM[d24_lagna_sign]
        for _dp, _ds in d24.items():
            if _dp == "Lagna" or not isinstance(_ds, str) or _ds not in _SIGN_NUM:
                continue
            _dh = ((_SIGN_NUM[_ds] - _l24_num) % 12) + 1
            _d24_occ_map.setdefault(str(_dh), []).append(_dp)

    # birth-time quality passthrough (chart JSON may supply these).
    # BUGFIX (2026-07, birth-time-sensitivity audit): previously defaulted a
    # missing precision field to "exact", which silently understated
    # birth-time sensitivity for every chart that simply didn't supply the
    # field (as opposed to one that explicitly declared an exact time).
    # "unknown" is the honest default -- matches payload.py's own field
    # default and llm_policy.py's data_quality_gate.
    _birth_prec_raw = str(
        ctx.get("birth_time_precision", pyh.get("birth_time_precision", "unknown")) or "unknown"
    ).strip().lower()
    if _birth_prec_raw not in ("exact", "approximate", "unknown"):
        _birth_prec_raw = "unknown"
    try:
        _bt_uncertainty = int(
            ctx.get("birth_time_uncertainty_minutes",
                    pyh.get("birth_time_uncertainty_minutes", 0)) or 0
        )
    except (TypeError, ValueError):
        _bt_uncertainty = 0

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
    _annual_transit_outlook: list = []   # default; overwritten below if timeline build succeeds
    # _llm_context is set inside the build_timeline branch; initialise here so the
    # NatalPayloadV2 constructor at line ~644 always has a defined value regardless
    # of whether build_timeline=True or the career context is blocked.
    _llm_context: dict = {
        "weight_overrides": {}, "intent_tags": [], "sector_modifier": 0.0,
        "career_theme_str": "", "enrichment_ok": False,
    }
    try:
        from Job_Career.timeline_inputs import parse_career_context, validate_career_context, parse_iso_date
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
            # I-3: Safe defaults ensure timeline.py always has required keys
            _llm_context: dict = {
                "weight_overrides": {}, "intent_tags": [], "sector_modifier": 0.0,
                "career_theme_str": "", "enrichment_ok": False,
            }
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
                    house_lords      = {str(i): house_lords_map.get(str(i), "")
                                        for i in range(1, 13)}
                    detected_yogas   = []  # yogas detected later in run_engine()
                    yogas_present    = []

                _chart_basics = build_chart_basics(_career_ctx, _PartialPayload())
                _enriched     = enrich_career_context(_career_ctx, _chart_basics)
                if _enriched:
                    _llm_context = {**_llm_context, **_enriched, "enrichment_ok": True}
            except Exception as _ph0_err:
                import logging as _log0
                _log0.getLogger("jyotish_engine_v11_0").debug(
                    "Phase 0 enrichment skipped: %s", _ph0_err
                )

            from Job_Career.timeline import build_career_timeline, TimelineChartInput
            _career_timeline = build_career_timeline(
                TimelineChartInput(
                    dob=ctx.get("dob", ""),
                    lagna_sign=lagna_sign,
                    dasha_sequence=_vimshottari_dated or _dasha_age_seq,
                    planet_house=planet_house,
                    house_lords={str(i): house_lords_map.get(str(i), "") for i in range(1, 13)},
                    kp_significators=pyh.get("kp_planetary_significators", {}),
                    kp_cusps=kp_cusps,
                    transit_house_positions=transit_hp,
                    atmakaraka=karakas.get("AK", ""),
                    amatyakaraka=karakas.get("AmK", ""),
                    kn_rao_jaimini=jaimini,
                    d10_house_occupancy=d10_house_occ,
                    d10_lagna_sign=d10_lagna,
                    d10_house_lords=d10_house_lords_computed,
                    sav_points_houses=_sav_normalized,   # Gap 0.1: canonical "1".."12" keys
                    retrograde_planets=[p for p, retro in planet_retrograde.items() if retro],
                    planet_sign=planet_signs_map,
                    planet_signs=planet_signs_map,
                    planet_nakshatras=planet_nakshatras_map,
                    planet_longitudes=_planet_longitudes,
                    d24_house_occupancy=_d24_occ_map,
                    d9_planet_dignities=d9_planet_dignities,
                    moon_nakshatra=_moon_nak_str,
                ),
                _eff_proxy,
                _career_ctx,
                mode=_mode,
                llm_context=_llm_context,
            )

            # ── Year-by-year Jupiter/Saturn/Rahu-Ketu transit outlook ──────────
            # BUG FIX (2026-07-05): build_career_timeline() only attaches this to
            # career_ctx["_payload_ref"], which this pipeline never sets (micro-timing
            # below is likewise computed independently, not read back from the
            # timeline builder). Without this block, generate_career_timeline_report()
            # always saw an empty annual_transit_outlook and the new transit section
            # silently rendered nothing for `--mode career`.
            try:
                from Job_Career.timeline import build_annual_transit_outlook

                class _TransitChartShim:
                    """Minimal attribute-only stand-in — build_annual_transit_outlook
                    only reads .transit_house_positions / .retrograde_planets / .planet_house."""
                    pass

                _tc_shim = _TransitChartShim()
                _tc_shim.transit_house_positions = transit_hp
                _tc_shim.retrograde_planets = [p for p, retro in planet_retrograde.items() if retro]
                _tc_shim.planet_house = planet_house
                # Data-consistency fix (2026-07-05, user-reported): this previously
                # read `_career_ctx.get("current_date", "")` — a key that
                # `parse_career_context()` never populates from any known chart
                # JSON shape (verified against Charts/lakshman_chart_details.json
                # and Charts/lakshman_career.json — neither's career_context block
                # carries a current_date key). That made this always resolve to
                # None, silently falling back to whatever build_annual_transit_
                # outlook() itself defaults to. The one field that IS consistently
                # populated and used elsewhere as "today" for this same chart is
                # system_config.current_date (already used for current_age via
                # sys_cfg.get("current_date","") a few lines above) — use the same
                # single source of truth here so age calculation and the transit/
                # timeline "today" anchor never disagree within one run. Falls back
                # to the real system clock (not a second hardcoded date) if the
                # chart JSON supplies neither.
                from datetime import date as _date_ato
                _today_anchor = parse_iso_date(sys_cfg.get("current_date", "")) or _date_ato.today()
                _annual_transit_outlook = build_annual_transit_outlook(
                    chart=_tc_shim,
                    lagna_sign=lagna_sign,
                    today=_today_anchor,
                    years_ahead=4,
                    years_back=1,
                )
            except Exception as _ato_err:
                import logging as _log_ato
                _log_ato.getLogger("jyotish_engine_v11_0").debug(
                    "annual_transit_outlook skipped: %s", _ato_err
                )
                _annual_transit_outlook = []

            # ── Module 2: Micro-Timing Dashboard ──────────────────────────────────────────────────
            try:
                from datetime import date as _date
                from Job_Career.micro_timing import compute_all_micro_timing as _micro
                # Data-consistency fix (2026-07-05, user-reported): same dead-key
                # issue as the transit-outlook block above — `_career_ctx.get(
                # "current_date","")` is never populated by parse_career_context().
                # Use system_config.current_date (same source as current_age) so
                # every "today" anchor in one report run agrees; fall back to the
                # real system clock only if the chart JSON supplies neither.
                _today = parse_iso_date(sys_cfg.get("current_date", "")) or _date.today()
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
                # BUGFIX (2026-07-19): this was previously only assigned inside the
                # `if not _active_ad_lord` branch above, so whenever the active AD/PD
                # lord WAS found via the earlier scan of _career_timeline,
                # `_tl_house_lords` was never bound -- yet it's used unconditionally
                # below, raising "cannot access local variable '_tl_house_lords'" and
                # silently skipping micro-timing on every normal run. Compute it
                # unconditionally so it's always defined before use.
                _tl_house_lords = {str(i): house_lords_map.get(str(i), "") for i in range(1, 13)}
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
        import traceback as _tb_ct
        _ct_trace = _tb_ct.format_exc()
        _log.getLogger("jyotish_engine_v11_0").warning(f"Career context parse skipped: {_ct_err}")
        # DIAGNOSTIC (2026-07-05): the above logger.warning is easy to miss or lose
        # (stderr buffering / logging not configured to a visible handler in some
        # run contexts), and it was silently swallowing the real cause behind the
        # generic "[Career Timeline] No blocks generated" CLI message. Surface the
        # actual exception + traceback directly on the context dict so the CLI can
        # print it, and force a stderr print here as a second, unconditional path.
        _career_ctx["_block_reason"] = f"EXCEPTION: {_ct_err}"
        _career_ctx["_block_traceback"] = _ct_trace
        print(f"\n[Career Timeline] INTERNAL ERROR while building timeline: {_ct_err}")
        print(_ct_trace)
        _mt = {}

    kp_significators = pyh.get("kp_planetary_significators", {}) or _build_kp_significators(planet_house, kp_cusps)
    _student_pref = ctx.get("student_preference", {}) or {}
    _risk_appetite = str(
        ctx.get("risk_appetite")
        or _student_pref.get("risk_appetite")
        or "MODERATE"
    ).upper()
    if _risk_appetite not in {"LOW", "MODERATE", "HIGH"}:
        _risk_appetite = "MODERATE"

    # User-reported gap fix (2026-07): all of h10_lord/h5_lord/h10_lord_planet
    # and the payload's house_lords dict used to independently re-derive from
    # kp_cusps[Hn].sign_lord right here, bypassing the guaranteed
    # `house_lords_map` fallback computed above (which fills any gap via
    # `_derive_house_lordships_from_lagna`). That meant the fallback never
    # actually reached the payload object everything downstream reads —
    # fixed by reusing `house_lords_map` for all of these instead of
    # recomputing from kp_cusps a second time.
    # V1.3 merge plan item 6: Ashtakavarga was computed but never wired into
    # the payload — boosts.py:_bav_individual_boost expects bav_points in
    # exactly this str-keyed shape but previously always received {}.
    try:
        _bav_points = compute_bav_points_str_keys(planet_signs_map, lagna_sign)
        _pav_data = compute_pav_data(planet_signs_map, lagna_sign)
    except Exception:
        _bav_points = {}
        _pav_data = {}

    # 2026-07 astrologer's audit: compute full six-fold Shadbala from first
    # principles (jyotish/shadbala.py) instead of relying solely on the
    # upstream `shadbala_virupas` single-number ingestion below. ADDITIVE --
    # exposed as payload.shadbala_computed alongside the existing `shadbala`
    # field; no existing consumer is switched over automatically, so this can
    # be validated against real charts first (see shadbala.py module
    # docstring). Degrades gracefully: uses documented neutral defaults for
    # Kala Bala's day/night-dependent sub-components (Tribhaga, precise
    # Nathonnata) since this pipeline ingests pre-built chart JSON without a
    # live birth lat/lon/tz at this stage -- Sthana Bala, Dig Bala, Cheshta
    # Bala (from planet_retrograde), Naisargika Bala, Paksha Bala, Vara Bala,
    # and Yuddha Bala are all computed exactly; Ayana/Nathonnata/Tribhaga use
    # documented neutral fallbacks pending lat/lon/tz plumbing into this
    # layer (see shadbala.py's compute_kala_bala docstring for the exact gap).
    try:
        _varga_dignities_for_shadbala = {
            "D9": d9_planet_dignities or {},
            # GAP-FIX (2026-07-18): d10_planet_dignities is now always computed
            # above (was previously never defined, hence the old defensive
            # locals().get() lookup here) -- see its computation site for the
            # full explanation.
            "D10": d10_planet_dignities or {},
            "D20": d20_planet_dignities or {},
            "D24": d24_planet_dignities or {},
        }
        from . import ephemeris as _sb_ephem
        _dob = datetime.strptime(str(ctx.get("dob", ""))[:10], "%Y-%m-%d").date()
        _tob = str(ctx.get("tob", "00:00:00") or "00:00:00")
        if len(_tob) == 5: _tob += ":00"
        _birth_dt = datetime.strptime(f"{_dob.isoformat()} {_tob}", "%Y-%m-%d %H:%M:%S")
        _lat = float(ctx.get("lat", ctx.get("latitude")))
        _lon = float(ctx.get("lon", ctx.get("longitude")))
        _tz = float(ctx.get("timezone_offset_hours", round(_lon / 15.0)))
        _true_speeds = _sb_ephem.get_planet_speeds(_birth_dt, _lat, _lon, tz_offset_hours=_tz)
        _tropical_lons = _sb_ephem.get_tropical_planet_longitudes(_birth_dt, _lat, _lon, tz_offset_hours=_tz)
        _planet_lats = _sb_ephem.get_planet_latitudes(_birth_dt, _lat, _lon, tz_offset_hours=_tz)
        _house_cusps = _sb_ephem.get_house_cusps_placidus(_birth_dt, _lat, _lon, tz_offset_hours=_tz)
        _sunrise_jd = _sb_ephem.get_sunrise_jd(_dob, _lat, _lon, _tz)
        _sunset_jd = _sb_ephem.get_sunset_jd(_dob, _lat, _lon, _tz)
        _sunrise = _sb_ephem.tt_jd_to_local_datetime(_sunrise_jd, _tz) if _sunrise_jd else None
        _sunset = _sb_ephem.tt_jd_to_local_datetime(_sunset_jd, _tz) if _sunset_jd else None
        _is_day = bool(_sunrise and _sunset and _sunrise <= _birth_dt < _sunset)
        if _is_day:
            _span_start, _span_end = _sunrise, _sunset
        elif _sunset and _birth_dt >= _sunset:
            _next_rise_jd = _sb_ephem.get_sunrise_jd(_dob + __import__("datetime").timedelta(days=1), _lat, _lon, _tz)
            _span_start = _sunset
            _span_end = _sb_ephem.tt_jd_to_local_datetime(_next_rise_jd, _tz) if _next_rise_jd else None
        else:
            _prev_set_jd = _sb_ephem.get_sunset_jd(_dob - __import__("datetime").timedelta(days=1), _lat, _lon, _tz)
            _span_start = _sb_ephem.tt_jd_to_local_datetime(_prev_set_jd, _tz) if _prev_set_jd else None
            _span_end = _sunrise
        _hours_in_span = ((_birth_dt - _span_start).total_seconds() / 3600.0) if _span_start else None
        _span_hours = ((_span_end - _span_start).total_seconds() / 3600.0) if _span_start and _span_end else None
        _weekday = _dob.weekday()
        _shadbala_computed = compute_shadbala_all(
            planets_d1, planet_house,
            varga_dignities=_varga_dignities_for_shadbala,
            navamsa_signs={p: s for p, s in d9.items() if p != "Lagna"},
            planet_longitudes=_planet_longitudes,
            planet_speeds=_true_speeds,
            tropical_longitudes=_tropical_lons,
            planet_latitudes=_planet_lats,
            is_day_birth=_is_day,
            weekday=_weekday,
            hours_since_sunrise=_hours_in_span,
            day_length_hours=_span_hours,
            birth_date=_dob,
            house_cusps=_house_cusps,
        )
    except Exception as _shadbala_exc:
        # 2026-07-19 audit: this block computes shadbala for the *natal*
        # chart (payload.shadbala_computed) from ctx["dob"]/ctx["tob"], which
        # only exist for natal/career/edu-mode payloads. A Prashna-only JSON
        # (just a `prashna_details` block, no top-level dob) legitimately has
        # no natal dob here, so `ctx.get("dob", "")` is "" and the
        # `datetime.strptime("", "%Y-%m-%d")` above raises -- this is
        # expected, not a bug: Prashna casts and scores its own chart
        # entirely independently in Prashnam/prashna.py (moved from
        # jyotish/prashna.py, 2026-07-19), which never reads
        # payload.shadbala_computed (confirmed: no shadbala references in
        # prashna.py). Downgrade to a one-line debug note instead of a
        # WARNING so real shadbala failures on natal-mode payloads (where
        # dob IS present) are still visible, without alarming Prashna users.
        if not str(ctx.get("dob", "")).strip():
            logger.debug(
                "shadbala.compute_shadbala_all skipped: no top-level 'dob' in "
                "payload (expected for Prashna-only JSON; does not affect the "
                "Prashna chart, which is cast independently)."
            )
        else:
            logger.warning("shadbala.compute_shadbala_all failed: %s", _shadbala_exc)
        _shadbala_computed = {}

    # 2026-07 astrologer's audit: wire the computed six-fold Shadbala into
    # eff_strengths (previously done blind above, purely from the upstream
    # `shadbala_virupas` single number). `_PLANET_MIN_SHADBALA`'s values
    # (Sun 390, Moon 360, Mars 300, Mercury 420, ...) ARE the classical BPHS
    # minimum-shadbala requirements in shashtiamsas (60 * the traditional
    # "rupa" minimums: Sun 6.5, Moon 6.0, Mars 5.0, ...), i.e. the exact same
    # scale shadbala.py's `total_shashtiamsa` uses -- this is a direct,
    # unit-consistent swap, not a rescale.
    #
    # A COMPLETE classical-v2 result is authoritative for Sun..Saturn. Nodes
    # retain the existing dispositor proxy because BPHS excludes them from
    # Shadbala. Incomplete results never overwrite upstream chart values.
    _shadbala_planets = (_shadbala_computed or {}).get("planets", {})
    if _shadbala_planets and _shadbala_computed.get("calculation_status") == "COMPUTED_COMPLETE_INPUTS":
        for _p in list(_eff_strengths_from_shadbala.keys()):
            _computed_total = _shadbala_planets.get(_p, {}).get("total_shashtiamsa")
            if _computed_total is None:
                continue
            _min_req = _PLANET_MIN_SHADBALA.get(_p, 300.0)
            _computed_ratio = min(float(_computed_total) / _min_req, 2.5)
            shadbala[_p] = round(float(_computed_total), 4)
            _eff_strengths_from_shadbala[_p] = round(_computed_ratio, 4)

    _payload = NatalPayloadV2(**{
        "name": student_name,
        # Prashna (horary) block: carries the querent's *current* location
        # (current_place/latitude_cp/longitude_cp) separately from the natal
        # birth details (dob/tob/pob/lat/lon) already parsed above. Passed
        # through untouched via extra="allow" so prashna_from_payload() can
        # read it directly off the payload.
        "prashna_details": data.get("prashna_details", {}),
        "bav_points": _bav_points,
        "pav_data": _pav_data,
        "shadbala_computed": _shadbala_computed,
        "lagna_sign": lagna_sign,
        "lagna_lord": _SIGN_LORD.get(lagna_sign, ""),
        "h10_lord": house_lords_map.get("10", ""),
        "atmakaraka": karakas.get("AK", ""),
        "amatyakaraka": karakas.get("AmK", ""),
        "karakamsha": jaimini.get("karakamsha_sign", ""),
        "planet_strength": {p: round(v / 600, 4) for p, v in shadbala.items()},
        "shadbala": shadbala,
        "eff_strengths": _eff_strengths_from_shadbala,
        "planet_house": planet_house,
        "house_lords": {str(i): house_lords_map.get(str(i), "") for i in range(1, 13)},
        "yogas_present": detected_yogas,
        "dasha_sequence": _dasha_age_seq,
        "current_age": _calc_age(ctx.get("dob", ""), sys_cfg.get("current_date", "")),
        "sun_moon_degrees_apart": round(sun_moon_diff, 4),
        "sav_points_houses": _sav_normalized,
        "combust_planets": combust_planets,
        "cazimi_planets": cazimi_planets,
        "kp_significators": kp_significators,
        "kp_cusps": kp_cusps,
        "planet_dignities": planet_dignities,
        "true_planet_dignities": true_planet_dignities,
        "d24_planet_dignities": d24_planet_dignities,
        "d20_planet_dignities": d20_planet_dignities,
        "planet_retrograde": planet_retrograde,
        "detected_yogas": detected_yogas,
        "h5_lord": house_lords_map.get("5", ""),
        "amk_house": planet_house.get(karakas.get("AmK", ""), 0),
        "upapada_lagna": jaimini.get("upapada_lagna_sign", ""),
        "h10_lord_planet": house_lords_map.get("10", ""),
        "d9_planet_dignities": d9_planet_dignities,
        "d10_planet_dignities": d10_planet_dignities,
        "planets_d1": planets_d1,
        "divisional_charts": div_charts,
        "nakshatra_data": nakshatra_data,
        "d9_lagna_sign": d9.get("Lagna", ""),
        "karakamsha_occupants": [
            p for p, s in d9.items()
            if p != "Lagna" and s == jaimini.get("karakamsha_sign", "")
        ],
        "neecha_bhanga_planets": list(neecha_bhanga_set),
        "gender": ctx.get("gender", ""),
        # GAP-FIX (2026-07): Special Lagnas, previously always "" (never
        # computed) -- see the computation block above.
        "ghati_lagna_sign": _ghati_lagna_sign,
        "sree_lagna_sign": _sree_lagna_sign,
        "hora_lagna_sign": _hora_lagna_sign,
        "bhava_lagna_sign": _bhava_lagna_sign,
        "bhrigu_bindu_sign": _bhrigu_bindu_sign,
        "interested_in": _student_pref.get("interested_in", []),
        "already_excel_at": _student_pref.get("already_excel_at", []),
        "risk_appetite": _risk_appetite,
        "brahma_lord": jaimini.get("jaimini_special_lords", {}).get("brahma", ""),
        "d10_house_occupancy": d10_house_occ,
        "d10_lagna_sign": d10_lagna,
        "d10_house_lords": d10_house_lords_computed,
        "moon_nakshatra": _moon_nak_str,
        "vimshottari_dasha_full": _vimshottari_dated,
        "matrikaraka": karakas.get("MK", ""),
        "bhatrikaraka": karakas.get("BK", ""),
        "putrakaraka": karakas.get("PK", ""),
        "gnatikaraka": karakas.get("GnK", "") or karakas.get("GK", ""),
        "darakaraka": karakas.get("DK", ""),
        "planet_signs": planet_signs_map,
        "planet_nakshatras": planet_nakshatras_map,
        "lagna_nakshatra": _lagna_nakshatra,
        "moon_nakshatra_pada": _moon_pada,
        "arudha_lagna": _arudha_lagna_computed,
        "a10_sign": _a10_sign_computed,
        "d10_devata_diagnostics": d10_devata_diagnostics,
        "transit_house_positions": transit_hp,
        "pratyantar_dasha_lord": prd_lord_raw,
        "prd_lord_houses": prd_houses_raw,
        "maheshwara_lord": maheshwara_raw,
        "dob": ctx.get("dob", ""),
        "tob": ctx.get("tob", ""),
        "latitude": float(ctx.get("lat", 0.0) or 0.0),
        "longitude": float(ctx.get("lon", 0.0) or 0.0),
        "timezone_offset_hours": ctx.get("timezone_offset_hours"),
        "external_llm_consent": bool(ctx.get("external_llm_consent", False)),
        "redact_debug_output": bool(ctx.get("redact_debug_output", True)),
        "data_retention_policy": str(ctx.get("data_retention_policy", "SESSION_ONLY")),
        "career_context": _career_ctx,
        "career_timeline": _career_timeline,
        "kn_rao_jaimini": jaimini,
        "micro_timing": _mt,
        "annual_transit_outlook": _annual_transit_outlook,
        "llm_context": _llm_context,
        "rahu_house": planet_house.get("Rahu", planet_house.get("rahu", 0)),
        "ketu_house": planet_house.get("Ketu", planet_house.get("ketu", 0)),
        "retrograde_planets": {p for p, retro in planet_retrograde.items() if retro},
        "karakamsha_sign": _SIGN_FROM_HOUSE(lagna_sign, jaimini.get("karakamsha_house", 0)),
        "d10_planet_sign": {p: s for p, s in d10.items() if p != "Lagna" and isinstance(s, str)},
        "d24_lagna_sign": d24_lagna_sign,
        "d24_house_lords": d24_house_lords_map,
        "birth_place": ctx.get("birth_place", ctx.get("city", "")),
        "planet_longitudes": _planet_longitudes,
        "birth_tithi_num": _birth_tithi_num,
        "d24_house_occupancy": _d24_occ_map,
        "birth_time_precision": _birth_prec_raw,
        "birth_time_uncertainty_minutes": _bt_uncertainty,
        "lagna_degree": lagna_deg,
        "house_system": _house_system,
        "calculation_identity": {
            "ayanamsa": sys_cfg.get("ayanamsa", ""),
            "node_type": sys_cfg.get("node_type", ""),
            "karaka_system": sys_cfg.get("karaka_system", ""),
            "house_system": _house_system,
        },
        "source_identity": {"source_sha256": _source_sha256, "chart_path": chart_path or "NOT_SUPPLIED"},
    })

    # Prashna (question-based) auto-answer: if the career context supplies an
    # explicit question, run it through the Prashna engine and attach the
    # result to the payload for downstream reporting.
    _career_q = _career_ctx.get("career_question", "") or _career_ctx.get("prashna_question", "")
    _career_cat = _career_ctx.get("prashna_category", "career_employment")
    if _career_q:
        # Prashna wiring moved out of engine_io.py; see Field_Determination's
        # dedicated Prashna module for the active integration point.
        # from .prashna_engine import prashna_from_payload as _pfp
        # _prashna_resp = _pfp(_payload, category=_career_cat, question=_career_q)
        # _payload.prashna_result = _prashna_resp
        pass

    return _payload


def _edu_sav_mod(sav: Dict[str, float]) -> float:
    """Ashtakavarga-derived modifier for education/aptitude scoring.

    Weighted blend of H4 (comforts/foundation), H5 (intelligence/education),
    H9 (fortune/higher learning), H10 (career/status), H11 (gains) SAV bindu
    counts, normalized around the classical ~28-bindu average.
    """
    h4 = sav.get("H4", 28)
    h5 = sav.get("H5", 28)
    h9 = sav.get("H9", 28)
    h10 = sav.get("H10", 28)
    h11 = sav.get("H11", 28)
    weighted = 0.1 * h4 + 0.25 * h5 + 0.25 * h9 + 0.3 * h10 + 0.1 * h11
    return 1 + (weighted - 28) / 100


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
    strat = DOMAIN_STRATEGIES.get(domain.lower(), {"w1": 0.4, "w2": 0.4, "min_score": 50})

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
        p1_str = eff_strengths.get(p1, 1)
        p2_str = eff_strengths.get(p2, 1)
    else:
        _min1 = _PLANET_MIN_SHADBALA.get(p1, 300)
        _min2 = _PLANET_MIN_SHADBALA.get(p2, 300)
        p1_str = min(raw_shadbala.get(p1, _min1) / _min1, 2.5)
        p2_str = min(raw_shadbala.get(p2, _min2) / _min2, 2.5)

    sav_mod = _edu_sav_mod(sav_points)
    primary_aptitude = round(p1_str * 50 * sav_mod, 4)
    secondary_aptitude = round(p2_str * 50 * sav_mod, 4)
    composite_score = strat["w1"] * primary_aptitude + strat["w2"] * secondary_aptitude
    threshold_required = strat.get("min_score", 50)
    meets_threshold = composite_score >= threshold_required

    return {
        "primary_aptitude": primary_aptitude,
        "secondary_aptitude": secondary_aptitude,
        "composite_score": composite_score,
        "threshold_required": threshold_required,
        "meets_threshold": meets_threshold,
        "p1": p1,
        "p2": p2,
    }


@functools.lru_cache(maxsize=1)
def _load_course_registry() -> Dict[str, Dict]:
    """Load course registry.

    Production behavior:
    - Prefer v12.
    - If REQUIRE_REGISTRY_V12=1, fail hard when v12 is missing/invalid.
    - Fallback to v11 only when migration mode allows it.

    BUGFIX (2026-07, user report): this was previously re-read/re-validated
    from disk on every call -- both the two module-level call sites
    (engine.py, llm.py, each executed once at import) AND two runtime call
    sites inside every single run_engine() / report-generation call
    (engine.py::_attach_registry_before_return, career_field_report_v2.py),
    so a single script invocation loaded and logged the same 199-branch
    registry 3-4 times. The registry is static for the process lifetime
    (read-only reference data, never mutated at runtime), so lru_cache(1)
    makes every call after the first a free in-memory hit -- same object
    returned each time, not a fresh copy, matching how the module-level
    `_COURSE_REGISTRY` globals already assumed a single shared instance.
    """
    require_v12 = os.getenv("REQUIRE_REGISTRY_V12", "1").strip() == "1"

    try:
        from .registry_loader_v12 import load_course_registry_v12
        branches = load_course_registry_v12(prefer_v12=True, validate=True)
        if not branches:
            raise RuntimeError("v12 course registry loaded empty")

        logger.info(
            "Loaded v12 course registry with %d branches; sample_keys=%s",
            len(branches),
            sorted(next(iter(branches.values())).keys())[:20] if branches else [],
        )
        return branches

    except Exception as exc:
        if require_v12:
            raise RuntimeError(
                "v12 registry is required but could not be loaded. "
                "Ensure jyotish/india_course_registry_v12.json and "
                "jyotish/registry_loader_v12.py are present and valid."
            ) from exc

        logger.warning("v12 registry loader failed, falling back to v11 legacy loader: %s", exc)

    _dir = os.path.dirname(os.path.abspath(__file__))
    _path = os.path.join(_dir, "india_course_registry_v11.json")
    with open(_path, "rb") as _f:
        _raw = _f.read().replace(b"\x00", b"").replace(b"\r", b"")

    _data = json.loads(_raw)
    branches = _data.get("branches", {})
    if not branches:
        raise RuntimeError(f"Course registry loaded empty: {_path}")

    for _ext in (SPACE_AEROSPACE_REGISTRY_EXTENSIONS, LIFE_SCIENCE_REGISTRY_EXTENSIONS):
        for _fid, _emeta in _ext.items():
            if _fid in branches:
                for _k, _v in _emeta.items():
                    branches[_fid].setdefault(_k, _v)
            else:
                branches[_fid] = dict(_emeta)

    logger.info(
        "Loaded legacy v11 course registry with %d branches because REQUIRE_REGISTRY_V12=0",
        len(branches),
    )
    return branches
