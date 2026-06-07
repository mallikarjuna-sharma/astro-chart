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
