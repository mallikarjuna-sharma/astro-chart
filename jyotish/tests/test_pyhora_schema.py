from jyotish.pyhora_schema import (
    chart_to_signs,
    divisional_signs,
    flat_divisional_charts,
    get_lagna_degree,
    get_lagna_sign,
    get_planets_d1,
    normalize_consolidated,
    normalize_pyhora_calculations,
)

_LEGACY_PYH = {
    "d1_lagna": "Sagittarius",
    "d1_lagna_degree": 12.9571,
    "planets_d1": {
        "Sun": {"sign": "Virgo", "degree": 12.5, "is_retrograde": False},
        "Moon": {"sign": "Pisces", "degree": 15.7, "is_retrograde": False},
    },
    "divisional_charts": {
        "D9_navamsha": {"Lagna": "Cancer", "Sun": "Aries", "Moon": "Scorpio"},
        "D10_dashamsha": {"Lagna": "Aries", "Sun": "Virgo"},
    },
}

_UNIFIED_PYH = {
    "divisional_charts": {
        "D1_rashi": {
            "factor": 1,
            "name": "Rashi (D1)",
            "lagna": "Sagittarius",
            "lagna_degree": 12.9571,
            "planets": {
                "Sun": {"sign": "Virgo", "degree": 12.5, "is_retrograde": False, "shadbala_virupas": 495.13},
                "Moon": {"sign": "Pisces", "degree": 15.7, "is_retrograde": False},
            },
        },
        "D9_navamsha": {
            "factor": 9,
            "lagna": "Cancer",
            "lagna_degree": 4.2,
            "planets": {
                "Sun": {"sign": "Aries", "degree": 10.1, "is_retrograde": False},
                "Moon": {"sign": "Scorpio", "degree": 8.3, "is_retrograde": False},
            },
        },
        "D60_shashtiamsam": {
            "factor": 60,
            "lagna": "Gemini",
            "lagna_degree": 1.0,
            "planets": {"Sun": {"sign": "Leo", "degree": 5.0, "is_retrograde": False}},
        },
    },
}


def test_legacy_d1_extraction():
    assert get_lagna_sign(_LEGACY_PYH) == "Sagittarius"
    assert get_lagna_degree(_LEGACY_PYH) == 12.9571
    assert "Sun" in get_planets_d1(_LEGACY_PYH)


def test_unified_d1_extraction():
    assert get_lagna_sign(_UNIFIED_PYH) == "Sagittarius"
    assert get_planets_d1(_UNIFIED_PYH)["Sun"]["shadbala_virupas"] == 495.13


def test_unified_divisional_signs():
    d9 = divisional_signs(_UNIFIED_PYH, "D9_navamsha")
    assert d9["Lagna"] == "Cancer"
    assert d9["Sun"] == "Aries"
    assert d9["Moon"] == "Scorpio"


def test_legacy_divisional_signs():
    d9 = divisional_signs(_LEGACY_PYH, "D9_navamsha")
    assert d9["Lagna"] == "Cancer"


def test_flat_divisional_charts_includes_d60():
    flat = flat_divisional_charts(_UNIFIED_PYH)
    assert "D60_shashtiamsam" in flat
    assert flat["D60_shashtiamsam"]["Sun"] == "Leo"


def test_chart_to_signs_full():
    signs = chart_to_signs(_UNIFIED_PYH["divisional_charts"]["D9_navamsha"])
    assert signs["Lagna"] == "Cancer"
    assert signs["Moon"] == "Scorpio"


def test_normalize_pyhora_moves_legacy_d1_into_divisional_charts():
    normalized = normalize_pyhora_calculations(_LEGACY_PYH)
    assert "planets_d1" not in normalized
    assert "d1_lagna" not in normalized
    d1 = normalized["divisional_charts"]["D1_rashi"]
    assert d1["lagna"] == "Sagittarius"
    assert "Sun" in d1["planets"]


def test_normalize_upgrades_flat_divisional_sign_maps():
    normalized = normalize_pyhora_calculations(_LEGACY_PYH)
    d9 = normalized["divisional_charts"]["D9_navamsha"]
    assert d9["lagna"] == "Cancer"
    assert d9["planets"]["Sun"]["sign"] == "Aries"


def test_normalize_consolidated_wraps_pyhora_calculations():
    chart = {
        "student_context": {"dob": "2000-01-01"},
        "pyhora_calculations": _LEGACY_PYH,
    }
    out = normalize_consolidated(chart)
    assert "planets_d1" not in out["pyhora_calculations"]
    assert "D1_rashi" in out["pyhora_calculations"]["divisional_charts"]
