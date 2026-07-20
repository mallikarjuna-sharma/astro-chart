"""Canonical Tajika annual-chart confirmation layer.

Computes the solar return, annual Placidus chart, Muntha, selected career
Sahamas, a documented Varshesha candidate decision, and Mudda dashas. This
is confirmation evidence and never a primary career or job-loss verdict.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from jyotish.ephemeris import (
    get_house_cusps_placidus, get_planet_longitude,
    get_planet_longitudes, get_planet_speeds, get_sunrise_jd, get_sunset_jd,
    tt_jd_to_local_datetime,
)
from jyotish.llm_policy import AYANAMSHA
from jyotish.validation_contract import evidence_status

VERSION = "varshaphala-tajika.v1"
SIGNS = ("Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces")
LORD = {"Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon","Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars","Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter"}
ORDER = ("Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury")
YEARS = {"Ketu":7,"Venus":20,"Sun":6,"Moon":10,"Mars":7,"Rahu":18,"Jupiter":16,"Saturn":19,"Mercury":17}
_RETURN_CACHE: dict[tuple, datetime | None] = {}

def _parse_birth(payload: Any) -> datetime | None:
    raw = f"{getattr(payload,'dob','')} {getattr(payload,'tob','00:00:00')}".strip()
    for fmt in ("%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M","%d/%m/%Y %H:%M:%S"):
        try: return datetime.strptime(raw, fmt)
        except ValueError: pass
    return None

def _angle(a: float, b: float) -> float:
    return ((a-b+180.0)%360.0)-180.0

def _solar_return(payload: Any, year: int) -> datetime | None:
    birth = _parse_birth(payload); natal = (getattr(payload,"planet_longitudes",{}) or {}).get("Sun")
    if birth is None or natal is None: return None
    lat=float(getattr(payload,"latitude",0) or 0); lon=float(getattr(payload,"longitude",0) or 0)
    tz=getattr(payload,"timezone_offset_hours",None)
    cache_key = (birth.isoformat(), round(float(natal), 8), year, round(lat, 6), round(lon, 6), tz, AYANAMSHA)
    if cache_key in _RETURN_CACHE:
        return _RETURN_CACHE[cache_key]
    try:
        center=birth.replace(year=year)
    except ValueError:  # 29-Feb birth in a non-leap target year
        center=birth.replace(year=year, day=28)

    def error(t: datetime) -> float | None:
        value = get_planet_longitude("Sun", t, lat, lon, AYANAMSHA, tz)
        return None if value is None else abs(_angle(value, float(natal)))

    # The Sun is monotonic across this four-day interval. Golden-section
    # minimisation reaches sub-second precision in 48 iterations, versus the
    # old 598 calls that computed all nine grahas on every sample.
    left, right = center-timedelta(days=2), center+timedelta(days=2)
    phi = (5.0 ** 0.5 - 1.0) / 2.0
    c = right - (right-left)*phi; d = left + (right-left)*phi
    ec, ed = error(c), error(d)
    if ec is None or ed is None:
        _RETURN_CACHE[cache_key] = None
        return None
    for _ in range(48):
        if ec <= ed:
            right, d, ed = d, c, ec
            c = right - (right-left)*phi; ec = error(c)
            if ec is None:
                _RETURN_CACHE[cache_key] = None
                return None
        else:
            left, c, ec = c, d, ed
            d = left + (right-left)*phi; ed = error(d)
            if ed is None:
                _RETURN_CACHE[cache_key] = None
                return None
    result = left + (right-left)/2
    _RETURN_CACHE[cache_key] = result
    return result

def _house(lon: float, asc: float) -> int:
    return ((int(lon%360//30)-int(asc%360//30))%12)+1

def _saham(asc: float, minuend: float, subtrahend: float) -> float:
    return (asc + minuend - subtrahend) % 360.0


def _tajika_aspects(planets: dict[str, float], speeds: dict[str, float], orb: float = 6.0) -> list[dict]:
    """Return applying/separating Tajika aspects from actual annual positions."""
    aspects = []
    names = {0: "conjunction", 60: "sextile", 90: "square", 120: "trine", 180: "opposition"}
    names_list = list(planets)
    for i, left in enumerate(names_list):
        for right in names_list[i + 1:]:
            separation = abs(_angle(planets[left], planets[right]))
            target = min(names, key=lambda angle: abs(separation - angle))
            distance = abs(separation - target)
            if distance > orb:
                continue
            future_sep = abs(_angle(planets[left] + speeds.get(left, 0.0),
                                    planets[right] + speeds.get(right, 0.0)))
            future_distance = abs(future_sep - target)
            applying = future_distance < distance
            aspects.append({
                "planets": [left, right], "aspect": names[target], "angle": target,
                "orb": round(distance, 4), "motion": "APPLYING" if applying else "SEPARATING",
                "tajika_yoga": "ITTHASALA" if applying else "ISRAFA",
            })
    return aspects


def _panchavargiya_screen(planets: dict[str, float], asc: float, speeds: dict[str, float]) -> dict[str, dict]:
    """Transparent five-factor annual strength screen.

    This exposes all components and is deliberately labelled a screen pending
    independent fixtures; it is never presented as a validated classical total.
    """
    exalt = {"Sun":"Aries","Moon":"Taurus","Mars":"Capricorn","Mercury":"Virgo",
             "Jupiter":"Cancer","Venus":"Pisces","Saturn":"Libra"}
    own = {"Sun":{"Leo"},"Moon":{"Cancer"},"Mars":{"Aries","Scorpio"},
           "Mercury":{"Gemini","Virgo"},"Jupiter":{"Sagittarius","Pisces"},
           "Venus":{"Taurus","Libra"},"Saturn":{"Capricorn","Aquarius"}}
    out = {}
    for planet, lon in planets.items():
        sign = SIGNS[int(lon % 360 // 30)]
        house = _house(lon, asc)
        kshetra = 5 if sign in own.get(planet, set()) else 0
        uchcha = 5 if exalt.get(planet) == sign else 0
        kendra = 5 if house in (1, 4, 7, 10) else 2.5 if house in (5, 9) else 0
        direct = 5 if speeds.get(planet, 0) >= 0 else 0
        visible = 5 if house not in (6, 8, 12) else 0
        out[planet] = {"kshetra":kshetra,"uchcha":uchcha,"kendra_trikona":kendra,
                       "direct_motion":direct,"non_dusthana":visible,
                       "total":round(kshetra+uchcha+kendra+direct+visible, 2),
                       "status":"ENGINEERED_SCREEN_NOT_CLASSICAL_PANCHAVARGIYA_TOTAL"}
    return out

def _mudda(return_dt: datetime, completed_years: int, moon_lon: float) -> list[dict]:
    nak=int(moon_lon/(360/27))+1; first=(completed_years+nak-2)%9
    cursor=return_dt; rows=[]
    for i in range(9):
        lord=ORDER[(first+i)%9]; days=YEARS[lord]*3
        end=cursor+timedelta(days=days)
        rows.append({"lord":lord,"start":cursor.isoformat(),"end":end.isoformat(),"days":days})
        cursor=end
    return rows

def compute_varshaphala(payload: Any, target_year: int) -> dict:
    birth=_parse_birth(payload)
    try:
        ret=_solar_return(payload,target_year)
    except Exception as exc:
        return {"contract_version":VERSION,"status":"NOT_COMPUTED",
                "reason":"SOLAR_RETURN_EPHEMERIS_FAILURE","detail":str(exc)[:200]}
    if birth is None or ret is None:
        return {"contract_version":VERSION,"status":"NOT_COMPUTED","reason":"BIRTH_OR_EPHEMERIS_DATA_MISSING"}
    lat=float(getattr(payload,"latitude",0) or 0); lon=float(getattr(payload,"longitude",0) or 0); tz=getattr(payload,"timezone_offset_hours",None)
    # BUGFIX (2026-07, crash report): _solar_return above is already guarded
    # against ephemeris/jplephem failures (e.g. DE421 Chebyshev-segment
    # errors), but these three follow-up calls previously were not -- any
    # transient skyfield/jplephem error here (same underlying library, same
    # failure class) propagated uncaught all the way through job_loss.py ->
    # timeline.py -> engine.py and crashed the entire run_engine() call, even
    # though Varshaphala is explicitly documented as CONFIRMATION_ONLY and
    # must never be able to take down the primary pipeline.
    try:
        planets=get_planet_longitudes(ret,lat,lon,AYANAMSHA,tz); speeds=get_planet_speeds(ret,lat,lon,AYANAMSHA,tz)
        cusps=get_house_cusps_placidus(ret,lat,lon,AYANAMSHA,tz)
    except Exception as exc:
        return {"contract_version":VERSION,"status":"NOT_COMPUTED",
                "reason":"ANNUAL_CHART_EPHEMERIS_FAILURE","detail":str(exc)[:200]}
    if len(cusps)!=12 or len(planets)<9:
        return {"contract_version":VERSION,"status":"NOT_COMPUTED","reason":"ANNUAL_CHART_INCOMPLETE"}
    asc=cusps[1]; age=target_year-birth.year; h11=cusps[11]
    # BUGFIX: Muntha must be reckoned from the NATAL Lagna advanced by one
    # sign per completed year (standard Tajika doctrine -- undisputed across
    # schools: Muntha progresses one rasi per varsha starting from the birth
    # Ascendant, not from the annual/Varshaphala chart's own ascendant). The
    # previous code advanced from `asc` (the *annual* solar-return
    # ascendant), which contradicts the classical definition: Muntha is an
    # independent confirming factor computed from the birth chart, not a
    # derivative of the just-erected annual chart. Use the natal Lagna
    # longitude (lagna_sign + lagna_degree on the payload) as the reference.
    natal_lagna_sign = getattr(payload, "lagna_sign", "") or ""
    natal_lagna_degree = float(getattr(payload, "lagna_degree", 0.0) or 0.0)
    if natal_lagna_sign in SIGNS:
        natal_asc = SIGNS.index(natal_lagna_sign) * 30.0 + natal_lagna_degree
    else:
        natal_asc = asc  # fallback: no natal Lagna available, degrade to annual asc
    muntha=(natal_asc+30*(age%12))%360
    h11_lord=LORD[SIGNS[int(h11//30)]]
    is_day = True
    if tz is not None:
        rise_jd = get_sunrise_jd(ret.date(), lat, lon, float(tz))
        set_jd = get_sunset_jd(ret.date(), lat, lon, float(tz))
        if rise_jd is not None and set_jd is not None:
            rise = tt_jd_to_local_datetime(rise_jd, float(tz))
            setting = tt_jd_to_local_datetime(set_jd, float(tz))
            is_day = rise <= ret < setting
    fortune=_saham(asc,planets["Moon"],planets["Sun"]) if is_day else _saham(asc,planets["Sun"],planets["Moon"])
    sahams={"fortune":fortune,"occupation":_saham(asc,planets["Mars"],planets["Mercury"]),
            "acquisition":_saham(asc,h11,planets[h11_lord])}
    candidates={LORD[SIGNS[int(asc//30)]],LORD.get(getattr(payload,"lagna_sign",""),""),LORD[SIGNS[int(planets["Sun"]//30)]]}
    candidates.discard("")
    # Transparent strength proxy pending independent Panchavargiya golden data.
    varshesha=max(candidates,key=lambda p: abs(speeds.get(p,0.0)),default="")
    pressure=sum(_house(x,asc) in (6,8,12) for x in (muntha,sahams["occupation"],sahams["acquisition"]))
    tajika_aspects = _tajika_aspects(planets, speeds)
    panchavargiya = _panchavargiya_screen(planets, asc, speeds)
    return {"contract_version":VERSION,"status":"COMPUTED_PARTIAL_TAJIKA","role":"CONFIRMATION_ONLY",
            "validation_status": evidence_status(inputs_complete=True, computed=True),
            "completeness": {"solar_return":True,"muntha":True,"selected_sahams":True,"mudda":True,
                             "tajika_aspects":True,"tajika_yogas":True,"panchavargiya_bala":False,
                             "varshesha_exact":False},
            "solar_return":ret.isoformat(),"annual_ascendant":round(asc,6),"planets":planets,"cusps":cusps,
            "muntha":{"longitude":round(muntha,6),"house":_house(muntha,asc)},
            "sahams":{k:{"longitude":round(v,6),"house":_house(v,asc)} for k,v in sahams.items()},
            "varshesha":varshesha,"varshesha_method":"DECLARED_CANDIDATES_STRENGTH_PROXY_NOT_VALIDATED",
            "tajika_aspects":tajika_aspects,
            "tajika_yogas":[a for a in tajika_aspects if a["tajika_yoga"] in ("ITTHASALA","ISRAFA")],
            "panchavargiya_strength_screen":panchavargiya,
            "mudda_dashas":_mudda(ret,age,float((getattr(payload,"planet_longitudes",{}) or {}).get("Moon",0))),
            "verdict":"pressure" if pressure>=2 else "supportive" if pressure==0 else "neutral",
            "calculation_identity":{"ayanamsha":AYANAMSHA,"house_system":"Placidus","node_type":"true"}}
