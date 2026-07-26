"""Normalize pyhora_calculations JSON — legacy flat D1 fields and unified divisional_charts."""
from __future__ import annotations

from typing import Any, Mapping

DIVISIONAL_CHART_META: dict[int, tuple[str, str]] = {
    1: ("D1_rashi", "Rashi (D1)"),
    2: ("D2_hora", "Hora (D2)"),
    3: ("D3_drekkana", "Drekkana (D3)"),
    4: ("D4_chaturthamsa", "Chaturthamsa (D4)"),
    5: ("D5_panchamsa", "Panchamsa (D5)"),
    6: ("D6_shashthamsa", "Shashthamsa (D6)"),
    7: ("D7_saptamsa", "Saptamsa (D7)"),
    8: ("D8_ashtamsa", "Ashtamsa (D8)"),
    9: ("D9_navamsha", "Navamsha (D9)"),
    10: ("D10_dashamsha", "Dashamsha (D10)"),
    16: ("D16_shodasamsa", "Shodasamsa (D16)"),
    24: ("D24_siddhamsam", "Siddhamsa (D24)"),
    60: ("D60_shashtiamsam", "Shashtiamsa (D60)"),
    81: ("D81_ashtottariamsa", "Ashtottariamsa (D81)"),
}

CONSOLIDATED_DIVISIONAL_FACTORS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 24, 60, 81)

DIVISIONAL_CHART_KEYS = tuple(meta[0] for meta in DIVISIONAL_CHART_META.values())

CHART_KEY_TO_FACTOR: dict[str, int] = {
    key: factor for factor, (key, _name) in DIVISIONAL_CHART_META.items()
}

_LEGACY_PYH_TOP_LEVEL_KEYS = frozenset({"planets_d1", "d1_lagna", "d1_lagna_degree"})

_META_KEYS = frozenset({"factor", "name", "lagna", "lagna_degree", "planets"})


def _divisional_block(pyh: Mapping[str, Any], key: str) -> dict[str, Any]:
    div = pyh.get("divisional_charts") or {}
    chart = div.get(key)
    return chart if isinstance(chart, dict) else {}


def is_full_divisional_chart(chart: Mapping[str, Any] | None) -> bool:
    return bool(chart and isinstance(chart.get("planets"), dict))


def chart_to_signs(chart: Mapping[str, Any] | None) -> dict[str, str]:
    """Flat {Lagna, Sun, …} sign map from full or legacy divisional chart."""
    if not chart:
        return {}
    if is_full_divisional_chart(chart):
        out = {
            str(planet): str(pdata.get("sign", ""))
            for planet, pdata in chart["planets"].items()
            if isinstance(pdata, Mapping) and pdata.get("sign")
        }
        lagna = chart.get("lagna")
        if lagna:
            out["Lagna"] = str(lagna)
        return out
    return {
        str(body): str(sign)
        for body, sign in chart.items()
        if body not in _META_KEYS and sign
    }


def get_d1_chart(pyh: Mapping[str, Any]) -> dict[str, Any]:
    d1 = _divisional_block(pyh, "D1_rashi")
    if is_full_divisional_chart(d1):
        return dict(d1)
    return {
        "factor": 1,
        "name": "Rashi (D1)",
        "lagna": pyh.get("d1_lagna", ""),
        "lagna_degree": pyh.get("d1_lagna_degree", 15.0),
        "planets": dict(pyh.get("planets_d1") or {}),
    }


def get_planets_d1(pyh: Mapping[str, Any]) -> dict[str, Any]:
    return dict(get_d1_chart(pyh).get("planets") or {})


def get_lagna_sign(pyh: Mapping[str, Any]) -> str:
    d1 = get_d1_chart(pyh)
    return str(d1.get("lagna") or pyh.get("d1_lagna") or "")


def get_lagna_degree(pyh: Mapping[str, Any]) -> float:
    d1 = get_d1_chart(pyh)
    deg = d1.get("lagna_degree", pyh.get("d1_lagna_degree", 15.0))
    try:
        return float(deg)
    except (TypeError, ValueError):
        return 15.0


def divisional_signs(pyh: Mapping[str, Any], key: str) -> dict[str, str]:
    return chart_to_signs(_divisional_block(pyh, key))


def flat_divisional_charts(pyh: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Legacy flat sign maps for engine payload consumers."""
    out: dict[str, dict[str, str]] = {}
    for key in DIVISIONAL_CHART_KEYS:
        signs = divisional_signs(pyh, key)
        if signs:
            out[key] = signs
    return out


def _upgrade_flat_divisional_chart(key: str, chart: Mapping[str, Any]) -> dict[str, Any]:
    """Convert legacy {Lagna, Sun, …} sign maps into unified divisional chart blocks."""
    if is_full_divisional_chart(chart):
        return dict(chart)
    factor = CHART_KEY_TO_FACTOR.get(key, 0)
    _chart_key, name = DIVISIONAL_CHART_META.get(factor, (key, key))
    lagna = str(chart.get("Lagna") or chart.get("lagna") or "")
    planets: dict[str, Any] = {}
    for body, sign in chart.items():
        if body in _META_KEYS or body in ("Lagna", "lagna") or not sign:
            continue
        planets[str(body)] = {
            "sign": str(sign),
            "degree": 0.0,
            "is_retrograde": False,
        }
    return {
        "factor": factor,
        "name": name,
        "lagna": lagna,
        "lagna_degree": float(chart.get("lagna_degree", 0.0) or 0.0),
        "planets": planets,
    }


def normalize_pyhora_calculations(pyh: Mapping[str, Any]) -> dict[str, Any]:
    """Ensure all varga data lives under divisional_charts; drop legacy duplicates."""
    if not pyh:
        return {}
    out = dict(pyh)
    div: dict[str, Any] = dict(out.get("divisional_charts") or {})

    d1 = get_d1_chart(out)
    if is_full_divisional_chart(d1):
        div["D1_rashi"] = d1

    for key in DIVISIONAL_CHART_KEYS:
        chart = div.get(key)
        if not chart:
            continue
        div[key] = _upgrade_flat_divisional_chart(key, chart)

    out["divisional_charts"] = div
    for legacy_key in _LEGACY_PYH_TOP_LEVEL_KEYS:
        out.pop(legacy_key, None)
    return out


def normalize_consolidated(data: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a consolidated export so chart data is only under divisional_charts."""
    if not data:
        return {}
    out = dict(data)
    pyh = out.get("pyhora_calculations")
    if isinstance(pyh, Mapping):
        out["pyhora_calculations"] = normalize_pyhora_calculations(pyh)
    return out
