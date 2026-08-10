"""Extended PyJHora computations: panchanga, ashtakavarga, shadbala, jaimini,
vimshottari, KP, and (static) planetary transits.

Each public `compute_*` function takes a `BirthChartBody` and returns a plain
dict that the frontend renders. Functions are defensive: a failure in one does
not affect the others (the API layer wraps each in its own endpoint).
"""
from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Any

import swisseph as swe

from jhora import const, utils
from jhora.horoscope.chart import ashtakavarga, charts, house, strength
from jhora.horoscope.dhasa.graha import vimsottari
from jhora.horoscope.dhasa.raasi import chara
from jhora.horoscope.match import compatibility
from jhora.panchanga import drik

from api.jhora_bootstrap import init_jhora
from api.schemas.chart import BirthChartBody
from jyotish.pyhora_schema import (
    CONSOLIDATED_DIVISIONAL_FACTORS,
    DIVISIONAL_CHART_META,
    normalize_consolidated,
)

_PLANET_NAMES = {
    0: "Sun", 1: "Moon", 2: "Mars", 3: "Mercury", 4: "Jupiter",
    5: "Venus", 6: "Saturn", 7: "Rahu", 8: "Ketu",
}
# The 7 planets used by shadbala (Sun..Saturn) in library column order.
_SHADBALA_PLANETS = [0, 1, 2, 3, 4, 5, 6]

_TITHI_BASE = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
    "Trayodashi", "Chaturdashi",
]
_YOGA_NAMES = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
    "Sukarman", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
    "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva",
    "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti",
]
_KARANA_MOVABLE = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]


def _tithi_name(idx: int) -> str:
    if idx < 1 or idx > 30:
        return f"Tithi {idx}"
    if idx == 15:
        return "Purnima (Shukla)"
    if idx == 30:
        return "Amavasya (Krishna)"
    if idx <= 15:
        return f"{_TITHI_BASE[idx - 1]} (Shukla)"
    return f"{_TITHI_BASE[idx - 16]} (Krishna)"


def _yoga_name(idx: int) -> str:
    if 1 <= idx <= 27:
        return _YOGA_NAMES[idx - 1]
    return f"Yoga {idx}"


def _karana_name(idx: int) -> str:
    if idx == 1:
        return "Kimstughna"
    if idx == 58:
        return "Shakuni"
    if idx == 59:
        return "Chatushpada"
    if idx == 60:
        return "Naga"
    if 2 <= idx <= 57:
        return _KARANA_MOVABLE[(idx - 2) % 7]
    return f"Karana {idx}"


def _nak_name(nak_index_1_to_27: int) -> str:
    if 1 <= nak_index_1_to_27 <= len(compatibility.nakshatra_list):
        return compatibility.nakshatra_list[nak_index_1_to_27 - 1]
    return f"Nak {nak_index_1_to_27}"


def _rasi_name(idx0: int) -> str:
    return const.rasi_names_en[idx0 % 12]


def _planet_name(pid: Any) -> str:
    if isinstance(pid, int):
        return _PLANET_NAMES.get(pid, f"Planet {pid}")
    return str(pid)


def _rasi_lord_name(rasi0: int) -> str:
    try:
        return _PLANET_NAMES.get(int(const.house_owners[rasi0 % 12]), "")
    except Exception:
        return ""


def _jd_to_date(jd: float) -> tuple[int, int, int]:
    y, m, d, _ = utils.jd_to_gregorian(jd)
    return int(y), int(m), int(d)


def _jd_to_date_str(jd: float) -> str:
    y, m, d = _jd_to_date(jd)
    return f"{y:04d}-{m:02d}-{d:02d}"


def _date_tuple_str(t: Any) -> str:
    if isinstance(t, (list, tuple)) and len(t) >= 3:
        return f"{int(t[0]):04d}-{int(t[1]):02d}-{int(t[2]):02d}"
    return str(t)


def _prepare(body: BirthChartBody) -> dict[str, Any]:
    init_jhora()
    const.set_node_mode(bool(body.use_true_nodes))
    place = drik.Place(
        body.place_label, body.latitude, body.longitude, body.timezone_offset_hours
    )
    jd = utils.julian_day_number(
        (body.year, body.month, body.day), (body.hour, body.minute, body.second)
    )
    mode = (body.ayanamsa or const._DEFAULT_AYANAMSA_MODE).upper()
    drik.set_ayanamsa_mode(mode)
    dob = drik.Date(body.year, body.month, body.day)
    tob = (body.hour, body.minute, body.second)
    pp = charts.rasi_chart(jd, place)
    return {"jd": jd, "place": place, "dob": dob, "tob": tob, "pp": pp, "mode": mode}


def _base_meta(body: BirthChartBody, ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "place_label": body.place_label,
        "birth_local": (
            f"{body.year:04d}-{body.month:02d}-{body.day:02d} "
            f"{body.hour:02d}:{body.minute:02d}:{body.second:02d}"
        ),
        "ayanamsa_mode": ctx["mode"],
    }


# ---------------------------------------------------------------------------
# Panchanga at birth
# ---------------------------------------------------------------------------
def compute_panchanga(body: BirthChartBody) -> dict[str, Any]:
    ctx = _prepare(body)
    jd, place = ctx["jd"], ctx["place"]

    tithi = drik.tithi(jd, place)
    nak = drik.nakshatra(jd, place)
    yogam = drik.yogam(jd, place)
    karana = drik.karana(jd, place)
    raasi = drik.raasi(jd, place)

    moon_rasi0 = int(raasi[0]) - 1 if raasi and raasi[0] else 0
    nak_idx = int(nak[0]) if nak else 0
    nak_pada = int(nak[1]) if nak and len(nak) > 1 else 0

    items = [
        {"label": "Tithi", "value": _tithi_name(int(tithi[0])) if tithi else ""},
        {"label": "Nakshatra", "value": f"{_nak_name(nak_idx)} (Pada {nak_pada})"},
        {"label": "Yoga", "value": _yoga_name(int(yogam[0])) if yogam else ""},
        {"label": "Karana", "value": _karana_name(int(karana[0])) if karana else ""},
        {"label": "Moon Rasi", "value": _rasi_name(moon_rasi0)},
        {"label": "Rasi Lord", "value": _rasi_lord_name(moon_rasi0)},
    ]
    return {"items": items, "meta": _base_meta(body, ctx)}


# ---------------------------------------------------------------------------
# Ashtakavarga: SAV (per house) + BAV (per planet contributor)
# ---------------------------------------------------------------------------
_BAV_CONTRIBUTORS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Lagna"]


def compute_ashtakavarga(body: BirthChartBody) -> dict[str, Any]:
    ctx = _prepare(body)
    pp = ctx["pp"]
    h2p = utils.get_house_planet_list_from_planet_positions(pp)
    result = ashtakavarga.get_ashtaka_varga(h2p)
    bav_rows = result[0]  # 8 contributors x 12 houses
    sav = result[1]       # 12 totals

    sav_table = [
        {"house": f"H{i + 1}", "rasi": _rasi_name(i), "points": int(sav[i])}
        for i in range(12)
    ]
    bav_by_house = [
        {
            "contributor": _BAV_CONTRIBUTORS[r] if r < len(_BAV_CONTRIBUTORS) else f"C{r}",
            "houses": [int(v) for v in bav_rows[r]],
            "total": int(sum(bav_rows[r])),
        }
        for r in range(len(bav_rows))
    ]
    return {
        "sav": sav_table,
        "sav_total": int(sum(sav)),
        "bav": bav_by_house,
        "meta": _base_meta(body, ctx),
    }


# ---------------------------------------------------------------------------
# Shadbala (percentage of required strength)
# ---------------------------------------------------------------------------
def compute_shadbala(body: BirthChartBody) -> dict[str, Any]:
    ctx = _prepare(body)
    jd, place = ctx["jd"], ctx["place"]
    sb = strength.shad_bala(jd, place)
    # Row 7 = total in Rupas, Row 8 = ratio to required strength.
    rupas = sb[7]
    ratio = sb[8]
    rows = []
    for col, pid in enumerate(_SHADBALA_PLANETS):
        pct = round(float(ratio[col]) * 100.0, 1)
        rows.append(
            {
                "planet": _PLANET_NAMES[pid],
                "rupas": round(float(rupas[col]), 2),
                "percentage": pct,
            }
        )
    ranked = sorted(rows, key=lambda r: r["percentage"], reverse=True)
    strongest = ranked[0]["planet"] if ranked else ""
    weakest = ranked[-1]["planet"] if ranked else ""
    return {
        "rows": rows,
        "strongest": strongest,
        "weakest": weakest,
        "meta": _base_meta(body, ctx),
    }


# ---------------------------------------------------------------------------
# Jaimini: chara karakas + karakamsa + arudha/upapada + chara dasha
# ---------------------------------------------------------------------------
_KARAKA_LABELS = [
    ("Atmakaraka (AK)", "atma_karaka"),
    ("Amatyakaraka (AmK)", "amatya_karaka"),
    ("Bhratrukaraka (BK)", "bhratri_karaka"),
    ("Matrukaraka (MK)", "maitri_karaka"),
    ("Pitrukaraka (PiK)", "pitri_karaka"),
    ("Putrakaraka (PuK)", "putra_karaka"),
    ("Gnatikaraka (GK)", "jnaati_karaka"),
    ("Darakaraka (DK)", "data_karaka"),
]


def compute_jaimini(body: BirthChartBody) -> dict[str, Any]:
    ctx = _prepare(body)
    jd, place, dob, tob, pp = ctx["jd"], ctx["place"], ctx["dob"], ctx["tob"], ctx["pp"]

    ck = house.chara_karakas(pp)  # list of planet indices in karaka order
    karakas = []
    for i, (label, _key) in enumerate(_KARAKA_LABELS):
        if i < len(ck):
            karakas.append({"karaka": label, "planet": _planet_name(ck[i])})

    # Karakamsa = navamsa (D9) sign of the Atmakaraka planet.
    karakamsa = ""
    try:
        ak_planet = ck[0]
        d9 = charts.divisional_chart(jd, place, divisional_chart_factor=9)
        for pid, (rasi_idx, _lon) in d9:
            if pid == ak_planet:
                karakamsa = _rasi_name(int(rasi_idx))
                break
    except Exception:
        karakamsa = ""

    # Arudha Lagna (AL) and Upapada Lagna (UL) from bhava arudhas.
    al = ul = ""
    try:
        from jhora.horoscope.chart import arudhas

        ba = arudhas.bhava_arudhas_from_planet_positions(pp)
        al = _rasi_name(int(ba[0]))
        ul = _rasi_name(int(ba[11]))
    except Exception:
        pass

    # Chara Dasha (maha rasi periods)
    chara_rows = []
    try:
        cd = chara.get_dhasa_antardhasa(dob, tob, place, dhasa_level_index=1)
        for entry in cd:
            rasi_tuple, start, dur = entry[0], entry[1], entry[2]
            rasi0 = int(rasi_tuple[0]) if isinstance(rasi_tuple, (list, tuple)) else int(rasi_tuple)
            start_year = int(start[0]) if isinstance(start, (list, tuple)) else None
            years = round(float(dur), 1)
            end_year = start_year + int(round(float(dur))) if start_year is not None else None
            chara_rows.append(
                {
                    "rasi": _rasi_name(rasi0),
                    "start": _date_tuple_str(start),
                    "start_year": start_year,
                    "end_year": end_year,
                    "years": years,
                }
            )
    except Exception as exc:
        chara_rows = []
        chara_error = str(exc)
    else:
        chara_error = None

    return {
        "karakas": karakas,
        "karakamsa": karakamsa,
        "arudha_lagna": al,
        "upapada_lagna": ul,
        "chara_dasha": chara_rows,
        "chara_dasha_error": chara_error,
        "meta": _base_meta(body, ctx),
    }


# ---------------------------------------------------------------------------
# Vimshottari dasha: maha periods + current maha/antar
# ---------------------------------------------------------------------------
def compute_vimshottari(body: BirthChartBody) -> dict[str, Any]:
    ctx = _prepare(body)
    jd, place = ctx["jd"], ctx["place"]

    maha = vimsottari.vimsottari_mahadasa(jd, place)  # OrderedDict planet -> start jd
    items = sorted(maha.items(), key=lambda kv: kv[1])
    periods = []
    for i, (pid, start_jd) in enumerate(items):
        end_jd = items[i + 1][1] if i + 1 < len(items) else None
        periods.append(
            {
                "planet": _PLANET_NAMES.get(int(pid), str(pid)),
                "start": _jd_to_date_str(start_jd),
                "end": _jd_to_date_str(end_jd) if end_jd else "",
                "start_jd": start_jd,
                "end_jd": end_jd,
            }
        )

    today = date.today()
    now_jd = utils.julian_day_number((today.year, today.month, today.day), (12, 0, 0))

    current_maha = ""
    for p in periods:
        if p["start_jd"] <= now_jd and (p["end_jd"] is None or now_jd < p["end_jd"]):
            current_maha = p["planet"]
            break

    # Current antardasha from the full bhukthi list.
    current_antar = ""
    try:
        _, bhukthis = vimsottari.get_vimsottari_dhasa_bhukthi(jd, place)
        prev = None
        for entry in bhukthis:
            (ml, al), start, _dur = entry[0], entry[1], entry[2]
            s_jd = utils.julian_day_number(
                (int(start[0]), int(start[1]), int(start[2])), (12, 0, 0)
            )
            if s_jd <= now_jd:
                prev = (ml, al)
            else:
                break
        if prev is not None:
            current_maha = _PLANET_NAMES.get(int(prev[0]), str(prev[0]))
            current_antar = _PLANET_NAMES.get(int(prev[1]), str(prev[1]))
    except Exception:
        pass

    # Strip internal jd keys before returning.
    for p in periods:
        p.pop("start_jd", None)
        p.pop("end_jd", None)

    return {
        "periods": periods,
        "current_mahadasha": current_maha,
        "current_antardasha": current_antar,
        "meta": _base_meta(body, ctx),
    }


# ---------------------------------------------------------------------------
# KP lords (sign lord, star/nakshatra lord, sub lord, deeper subs)
# ---------------------------------------------------------------------------
def compute_kp(body: BirthChartBody) -> dict[str, Any]:
    ctx = _prepare(body)
    pp = ctx["pp"]
    kp = charts.get_KP_lords_from_planet_positions(pp)

    rows = []
    for pid, (h, lon) in pp:
        info = kp.get(pid)
        if not info:
            continue
        # info = [kp_number(1-249), star_lord, sub_lord, sub_sub_lord, ...].
        # The sign (rasi) lord is derived from the occupied sign.
        kp_number = int(info[0]) if len(info) > 0 else None
        lords = [_PLANET_NAMES.get(int(x), str(x)) for x in info[1:]]
        rows.append(
            {
                "body": _planet_name(pid),
                "rasi": _rasi_name(int(h)),
                "kp_number": kp_number,
                "sign_lord": _rasi_lord_name(int(h)),
                "star_lord": lords[0] if len(lords) > 0 else "",
                "sub_lord": lords[1] if len(lords) > 1 else "",
                "sub_sub_lord": lords[2] if len(lords) > 2 else "",
            }
        )
    return {"rows": rows, "meta": _base_meta(body, ctx)}


# ---------------------------------------------------------------------------
# Planetary transits 1960-2080 (Jupiter, Saturn, Rahu, Ketu) — STATIC.
# Independent of birth data. Cached in memory; optionally served from a
# precomputed JSON committed to the repo for instant first response.
# ---------------------------------------------------------------------------
# swisseph planet ids. Ketu is computed as Rahu (mean node) + 180 degrees.
_TRANSIT_PLANETS = [
    ("Jupiter", swe.JUPITER, 0.0),
    ("Saturn", swe.SATURN, 0.0),
    ("Rahu", swe.MEAN_NODE, 0.0),
    ("Ketu", swe.MEAN_NODE, 180.0),
]
_TRANSIT_START_YEAR = 1960
_TRANSIT_END_YEAR = 2080
_TRANSIT_STEP_DAYS = 5.0
_transit_lock = threading.Lock()
_transit_cache: dict[str, Any] | None = None


def _transit_json_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "transits_1960_2080.json"


def _sid_long(jd: float, swe_id: int, offset: float) -> float:
    return (drik.sidereal_longitude(jd, swe_id) + offset) % 360.0


def _compute_transits_uncached() -> dict[str, Any]:
    """Detect sign-ingress dates by sampling sidereal longitude and bisecting boundaries.

    Works uniformly for direct (Jupiter, Saturn) and retrograde (Rahu, Ketu) bodies.
    """
    init_jhora()
    const.set_node_mode(False)
    drik.set_ayanamsa_mode(const._DEFAULT_AYANAMSA_MODE.upper())
    start_jd = utils.julian_day_number((_TRANSIT_START_YEAR, 1, 1), (0, 0, 0))
    end_jd = utils.julian_day_number((_TRANSIT_END_YEAR, 12, 31), (23, 59, 0))

    by_planet: dict[str, list[dict[str, Any]]] = {}
    for pname, swe_id, offset in _TRANSIT_PLANETS:
        events: list[dict[str, Any]] = []
        prev_jd = start_jd
        prev_sign = int(_sid_long(prev_jd, swe_id, offset) // 30) % 12
        cur = start_jd + _TRANSIT_STEP_DAYS
        while cur <= end_jd:
            sign = int(_sid_long(cur, swe_id, offset) // 30) % 12
            if sign != prev_sign:
                lo, hi = prev_jd, cur
                for _ in range(40):  # bisect to ~minutes precision
                    mid = (lo + hi) / 2.0
                    if int(_sid_long(mid, swe_id, offset) // 30) % 12 == prev_sign:
                        lo = mid
                    else:
                        hi = mid
                lon_at = _sid_long(hi, swe_id, offset)
                nak_idx, pada, _ = drik.nakshatra_pada(lon_at)
                events.append(
                    {
                        "jd": hi,
                        "rasi": _rasi_name(int(lon_at // 30) % 12),
                        "nakshatra": _nak_name(int(nak_idx)),
                        "pada": int(pada),
                    }
                )
                prev_sign = sign
            prev_jd = cur
            cur += _TRANSIT_STEP_DAYS

        for i, ev in enumerate(events):
            ev["start_date"] = _jd_to_date_str(ev["jd"])
            ev["end_date"] = _jd_to_date_str(events[i + 1]["jd"]) if i + 1 < len(events) else ""
            ev.pop("jd", None)
        by_planet[pname] = events

    return {
        "from_year": _TRANSIT_START_YEAR,
        "to_year": _TRANSIT_END_YEAR,
        "ayanamsa_mode": const._DEFAULT_AYANAMSA_MODE.upper(),
        "planets": by_planet,
    }


def compute_transits() -> dict[str, Any]:
    global _transit_cache
    if _transit_cache is not None:
        return _transit_cache
    with _transit_lock:
        if _transit_cache is not None:
            return _transit_cache
        path = _transit_json_path()
        if path.is_file():
            try:
                _transit_cache = json.loads(path.read_text())
                return _transit_cache
            except Exception:
                pass
        _transit_cache = _compute_transits_uncached()
        return _transit_cache


# ---------------------------------------------------------------------------
# Consolidated KP-oriented export JSON (single object, copy-friendly).
# Forces the configuration declared in `system_config`: KP (Krishnamurti)
# ayanamsa, True nodes, 7-karaka (KN Rao) Jaimini scheme.
# ---------------------------------------------------------------------------
# swisseph ids for the nine grahas (Rahu/Ketu resolved at runtime per node mode).
_SWE_ID = {0: swe.SUN, 1: swe.MOON, 2: swe.MARS, 3: swe.MERCURY,
           4: swe.JUPITER, 5: swe.VENUS, 6: swe.SATURN}
# Sign rulerships (0=Aries .. 11=Pisces) -> owning planet, and the inverse.
_SIGN_LORD = [2, 5, 3, 1, 0, 3, 5, 2, 4, 6, 6, 4]
_OWNED_SIGNS = {0: [4], 1: [3], 2: [0, 7], 3: [2, 5], 4: [8, 11], 5: [1, 6], 6: [9, 10]}
# 7-karaka (KN Rao) labels in descending-longitude order.
_KARAKA7 = ["AK", "AmK", "BK", "MK", "PK", "GK", "DK"]


def _prepare_kp(body: BirthChartBody) -> dict[str, Any]:
    """Like `_prepare` but pinned to KP ayanamsa + true nodes for the export payload."""
    init_jhora()
    const.set_node_mode(True)  # node_type "True"
    place = drik.Place(body.place_label, body.latitude, body.longitude, body.timezone_offset_hours)
    jd = utils.julian_day_number(
        (body.year, body.month, body.day), (body.hour, body.minute, body.second)
    )
    mode = (body.ayanamsa or "KP").upper()
    drik.set_ayanamsa_mode(mode)
    pp = charts.rasi_chart(jd, place)
    return {"jd": jd, "place": place, "pp": pp}


def _sign_and_deg(rasi_idx: int, lon_in_rasi: float) -> tuple[str, float]:
    return _rasi_name(int(rasi_idx)), round(float(lon_in_rasi), 4)


def _planet_full_lon(pp: list, pid: int) -> float:
    for p, (h, lon) in pp:
        if p == pid:
            return int(h) * 30.0 + float(lon)
    return 0.0


def _house_num(sign0: int, lagna_sign0: int) -> int:
    return ((int(sign0) - int(lagna_sign0)) % 12) + 1


_DIVISIONAL_META = DIVISIONAL_CHART_META


def _build_d1_chart(
    pp: list,
    jd: float,
    place: Any,
    retro: set[int],
    virupas: list,
    jd_ut: float,
) -> dict[str, Any]:
    lagna_rasi = next((int(h) for p, (h, _l) in pp if p == "L"), 0)
    lagna_deg = next((float(l) for p, (h, l) in pp if p == "L"), 0.0)
    node_for_ketu = swe.TRUE_NODE
    planets: dict[str, Any] = {}
    for pid in range(0, 9):
        sign = None
        deg = 0.0
        for p, (h, lon) in pp:
            if p == pid:
                sign, deg = _sign_and_deg(h, lon)
                break
        if sign is None:
            continue
        if pid <= 6:
            swe_id, off = _SWE_ID[pid], 0.0
        elif pid == 7:
            swe_id, off = swe.TRUE_NODE, 0.0
        else:
            swe_id, off = node_for_ketu, 180.0
        try:
            res = swe.calc_ut(jd_ut, swe_id)[0]
            lat = round(float(res[1]), 4)
        except Exception:
            lat = 0.0
        entry: dict[str, Any] = {
            "sign": sign,
            "degree": deg,
            "is_retrograde": pid in retro,
            "latitude": lat,
        }
        if pid <= 6:
            entry["shadbala_virupas"] = round(float(virupas[pid]), 2)
        planets[_PLANET_NAMES[pid]] = entry
    key, name = _DIVISIONAL_META[1]
    return {
        "factor": 1,
        "name": name,
        "lagna": _rasi_name(lagna_rasi),
        "lagna_degree": round(lagna_deg, 4),
        "planets": planets,
    }


def _build_divisional_chart(jd: float, place: Any, factor: int, retro: set[int]) -> dict[str, Any]:
    positions = charts.divisional_chart(jd, place, divisional_chart_factor=factor)
    lagna_sign = ""
    lagna_degree = 0.0
    planets: dict[str, Any] = {}
    for pid, (rasi_idx, lon) in positions:
        sign, deg = _sign_and_deg(int(rasi_idx), float(lon))
        if pid == "L":
            lagna_sign = sign
            lagna_degree = deg
            continue
        key = _PLANET_NAMES.get(pid)
        if not key:
            continue
        planets[key] = {
            "sign": sign,
            "degree": deg,
            "is_retrograde": pid in retro,
        }
    _key, name = _DIVISIONAL_META[factor]
    return {
        "factor": factor,
        "name": name,
        "lagna": lagna_sign,
        "lagna_degree": lagna_degree,
        "planets": planets,
    }


def _decimal_year(jd: float) -> float:
    y, m, d = _jd_to_date(jd)
    year_start = utils.julian_day_number((y, 1, 1), (0, 0, 0))
    return round(y + (jd - year_start) / 365.25, 2)


def _chara_karakas_7(pp: list) -> dict[str, str]:
    """KN Rao 7-karaka scheme: Sun..Saturn sorted by longitude-in-sign (desc)."""
    rows = []
    for pid in range(0, 7):
        for p, (h, lon) in pp:
            if p == pid:
                rows.append((pid, float(lon)))
                break
    rows.sort(key=lambda r: r[1], reverse=True)
    return {_KARAKA7[i]: _PLANET_NAMES[pid] for i, (pid, _l) in enumerate(rows) if i < 7}


def _kp_significators(pp: list, kp: dict, bhava_houses: dict, lagna_sign0: int) -> dict[str, dict]:
    """Standard KP 4-level planet->house significators.

    L1: house occupied by the planet's star (nakshatra) lord.
    L2: house occupied by the planet itself.
    L3: houses owned by the planet's star lord.
    L4: houses owned by the planet itself.
    (Rahu/Ketu own no sign, so L4 uses the lord of the sign they occupy.)
    """
    def occ_house(pid: int) -> list[int]:
        h = bhava_houses.get(pid)
        return [int(h)] if h is not None else []

    def owned_houses(pid: int) -> list[int]:
        signs = _OWNED_SIGNS.get(pid, [])
        return sorted({_house_num(s, lagna_sign0) for s in signs})

    # planet -> occupied sign (for node dispositor)
    occ_sign = {p: int(h) for p, (h, _l) in pp if isinstance(p, int)}

    out: dict[str, dict] = {}
    for pid in range(0, 9):
        info = kp.get(pid)
        star_lord = int(info[1]) if info and len(info) > 1 else None
        l1 = occ_house(star_lord) if star_lord is not None else []
        l2 = occ_house(pid)
        l3 = owned_houses(star_lord) if star_lord is not None else []
        if pid in (7, 8):  # nodes: own no sign -> use dispositor of occupied sign
            disp = _SIGN_LORD[occ_sign.get(pid, 0)]
            l4 = owned_houses(disp)
        else:
            l4 = owned_houses(pid)
        out[_PLANET_NAMES[pid]] = {
            "level_1": l1, "level_2": l2, "level_3": l3, "level_4": l4,
        }
    return out


def compute_consolidated(body: BirthChartBody, student_context: dict | None = None) -> dict[str, Any]:
    ctx = _prepare_kp(body)
    jd, place, pp = ctx["jd"], ctx["place"], ctx["pp"]
    sc = student_context or {}
    pref = sc.get("student_preference") or {}

    lagna_rasi = next((int(h) for p, (h, _l) in pp if p == "L"), 0)
    lagna_deg = next((float(l) for p, (h, l) in pp if p == "L"), 0.0)

    retro = set(int(x) for x in drik.planets_in_retrograde(jd, place))
    sb = strength.shad_bala(jd, place)
    virupas = sb[6]
    jd_ut = jd - place.timezone / 24.0

    d1_chart = _build_d1_chart(pp, jd, place, retro, virupas, jd_ut)
    divisional_charts: dict[str, Any] = {}
    for factor in CONSOLIDATED_DIVISIONAL_FACTORS:
        chart_key, _name = _DIVISIONAL_META[factor]
        if factor == 1:
            divisional_charts[chart_key] = d1_chart
        else:
            divisional_charts[chart_key] = _build_divisional_chart(jd, place, factor, retro)

    # KP cusp data (H1..H12 in bhava order)
    bhava = charts.bhava_chart(jd, place)
    kp_cusp: dict[str, Any] = {}
    for i, entry in enumerate(bhava, start=1):
        rasi_idx = int(entry[0])
        cusp_lon = float(entry[1][1])  # bhava madhya
        lords = utils.kp_lords_for_longitude(0, cusp_lon).get(0, [])
        kp_cusp[f"H{i}"] = {
            "sign": _rasi_name(rasi_idx),
            "degree": round(cusp_lon % 30.0, 4),
            "sign_lord": _PLANET_NAMES.get(int(_SIGN_LORD[rasi_idx]), ""),
            "star_lord": _PLANET_NAMES.get(int(lords[1]), "") if len(lords) > 1 else "",
            "sub_lord": _PLANET_NAMES.get(int(lords[2]), "") if len(lords) > 2 else "",
            "sub_sub_lord": _PLANET_NAMES.get(int(lords[3]), "") if len(lords) > 3 else "",
        }

    # KP planetary significators
    kp_planet = charts.get_KP_lords_from_planet_positions(pp)
    bhava_houses = charts.bhava_houses(jd, place)
    significators = _kp_significators(pp, kp_planet, bhava_houses, lagna_rasi)

    # Jaimini (7-karaka), karakamsa, upapada, special lords
    karakas7 = _chara_karakas_7(pp)
    ak_name = karakas7.get("AK")
    ak_pid = next((k for k, v in _PLANET_NAMES.items() if v == ak_name), 0)
    d9 = charts.divisional_chart(jd, place, divisional_chart_factor=9)
    karakamsha_sign = next((_rasi_name(int(r)) for p, (r, _l) in d9 if p == ak_pid), "")
    try:
        from jhora.horoscope.chart import arudhas
        ba = arudhas.bhava_arudhas_from_planet_positions(pp)
        upapada_sign = _rasi_name(int(ba[11]))
    except Exception:
        upapada_sign = ""
    try:
        brahma_pid = int(house.brahma(pp))
    except Exception:
        brahma_pid = None
    try:
        mahesh_pid = int(house.maheshwara_from_planet_positions(pp))
    except Exception:
        mahesh_pid = None
    try:
        rudra_res = house.rudra(pp)
        rudra_pid = int(rudra_res[0]) if isinstance(rudra_res, (list, tuple)) else int(rudra_res)
    except Exception:
        rudra_pid = None

    # Ashtakavarga SAV by house (rotated from lagna)
    h2p = utils.get_house_planet_list_from_planet_positions(pp)
    sav_by_rasi = ashtakavarga.get_ashtaka_varga(h2p)[1]
    sav = {f"H{n}": int(sav_by_rasi[(lagna_rasi + n - 1) % 12]) for n in range(1, 13)}

    # Vimshottari maha sequence with decimal years + ages
    maha = vimsottari.vimsottari_mahadasa(jd, place)
    items = sorted(maha.items(), key=lambda kv: kv[1])
    dasha_seq = []
    for i, (pid, start_jd) in enumerate(items):
        end_jd = items[i + 1][1] if i + 1 < len(items) else start_jd + 0.0
        dasha_seq.append({
            "md_planet": _PLANET_NAMES.get(int(pid), str(pid)),
            "start_year": _decimal_year(start_jd),
            "end_year": _decimal_year(end_jd) if i + 1 < len(items) else None,
            "age_start": round((start_jd - jd) / 365.25, 1),
            "age_end": round((end_jd - jd) / 365.25, 1) if i + 1 < len(items) else None,
        })

    return normalize_consolidated({
        "system_config": {
            "ayanamsa": "KP_Krishnamurti",
            "node_type": "True",
            "karaka_system": 7,
            "birth_time_uncertainty_minutes": 0.0,
            "current_date": date.today().isoformat(),
        },
        "student_context": {
            "dob": f"{body.year:04d}-{body.month:02d}-{body.day:02d}",
            "tob": f"{body.hour:02d}:{body.minute:02d}:{body.second:02d}",
            "pob": sc.get("pob") or body.place_label,
            "lat": round(float(body.latitude), 4),
            "lon": round(float(body.longitude), 4),
            "gender": sc.get("gender") or "O",
            "education_system": sc.get("education_system") or "India_CBSE",
            "student_preference": {
                "interested_in": pref.get("interested_in") or [],
                "already_excel_at": pref.get("already_excel_at") or [],
                "financial_constraints": bool(pref.get("financial_constraints", False)),
                "risk_appetite": pref.get("risk_appetite") or "MODERATE",
            },
        },
        "pyhora_calculations": {
            "divisional_charts": divisional_charts,
            "kp_cusp_data": kp_cusp,
            "kp_planetary_significators": significators,
            "kn_rao_jaimini_data": {
                "chara_karakas": karakas7,
                "karakamsha_sign": karakamsha_sign,
                "upapada_lagna_sign": upapada_sign,
                "jaimini_special_lords": {
                    "brahma": _PLANET_NAMES.get(brahma_pid, "") if brahma_pid is not None else "",
                    "maheshwara": _PLANET_NAMES.get(mahesh_pid, "") if mahesh_pid is not None else "",
                    "rudra": _PLANET_NAMES.get(rudra_pid, "") if rudra_pid is not None else "",
                },
            },
            "ashtakavarga_sav": sav,
            "vimshottari_dasha_sequence": dasha_seq,
        },
    })
