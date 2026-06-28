"""JyotishAI — Payload model and engine metadata.

Migrated from @dataclass to pydantic.BaseModel (Gap 2) to provide:
  - Runtime type coercion at construction time
  - IDE-level type safety and autocomplete
  - model_config extra='allow' so engine.py can attach computed attrs
    (peak_dasha_lord, peak_dasha_window, planet_modifier_flags) without
    registering them as formal schema fields.
"""
import logging
import os as _os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "v11.0-llm"

_log_level = getattr(logging, _os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=_log_level, format="%(levelname)s: %(message)s")
logger = logging.getLogger("jyotish_engine_v11_0")
logger.setLevel(_log_level)


class NatalPayloadV2(BaseModel):
    """Validated birth-chart payload consumed by run_engine().

    All fields default to empty/zero so partial construction works in tests.
    The four mandatory chart fields (planets_d1, kp_significators, kp_cusps,
    dasha_sequence) are validated for non-emptiness at run_engine() entry via
    _validate_payload_schema(), NOT here — this keeps test fixtures lightweight.

    extra='allow' lets engine.py attach ephemeral computed attributes such as
    peak_dasha_lord, peak_dasha_window, and planet_modifier_flags without
    requiring formal schema definitions for each.
    """

    model_config = ConfigDict(
        extra="allow",                # engine attaches computed attrs at runtime
        arbitrary_types_allowed=True, # future-proof for non-Pydantic type hints
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    name: str = "Unknown"
    lagna_sign: str = ""
    lagna_lord: str = ""
    h10_lord: str = ""
    atmakaraka: str = ""
    amatyakaraka: str = ""
    karakamsha: str = ""

    # ── Strength tables ───────────────────────────────────────────────────────
    planet_strength: Dict[str, float] = Field(default_factory=dict)
    shadbala: Dict[str, float] = Field(default_factory=dict)
    eff_strengths: Dict[str, float] = Field(default_factory=dict)   # shadbala/min_sv ratio; 1.0=minimum, >1=stronger
    trait_level: Dict[str, float] = Field(default_factory=dict)

    # ── Divisional-chart strength scalars ─────────────────────────────────────
    kp_h10: float = 0.5
    d10_strength: float = 0.5
    d24_strength: float = 0.5
    d9_strength: float = 0.5
    d60_strength: float = 0.5

    # ── House / node positions ────────────────────────────────────────────────
    ketu_house: int = 0
    rahu_house: int = 0
    planet_house: Dict[str, int] = Field(default_factory=dict)
    house_lords: Dict[str, str] = Field(default_factory=dict)

    # ── Yoga / dasha ──────────────────────────────────────────────────────────
    yogas_present: List[str] = Field(default_factory=list)
    dasha_sequence: List[Dict] = Field(default_factory=list)

    # ── Socio-educational context ─────────────────────────────────────────────
    family_income_tier: str = "middle"
    school_board: str = "CBSE"
    current_age: float = 0.0
    sun_moon_degrees_apart: float = 0.0

    # ── Transit / pratyantar ─────────────────────────────────────────────────
    transit_house_positions: Dict[str, int] = Field(default_factory=dict)
    pratyantar_dasha_lord: str = ""
    prd_lord_houses: List[int] = Field(default_factory=list)

    # ── Divisional-chart data ─────────────────────────────────────────────────
    divisional_planet_strength: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    sav_points_houses: Dict[str, int] = Field(default_factory=dict)
    d10_house_occupancy: Dict[str, List[str]] = Field(default_factory=dict)

    # ── Planetary state ───────────────────────────────────────────────────────
    combust_planets: List[str] = Field(default_factory=list)
    cazimi_planets: List[str] = Field(default_factory=list)   # v8.7 ASTRO-2
    risk_appetite: str = "MODERATE"
    kp_significators: Dict[str, Dict] = Field(default_factory=dict)
    kp_cusps: Dict[str, Dict] = Field(default_factory=dict)
    planet_dignities: Dict[str, str] = Field(default_factory=dict)
    d24_planet_dignities: Dict[str, str] = Field(default_factory=dict)
    planet_retrograde: Dict[str, bool] = Field(default_factory=dict)
    detected_yogas: List[str] = Field(default_factory=list)

    # ── Lord / special points ─────────────────────────────────────────────────
    h5_lord: str = ""
    amk_house: int = 0
    upapada_lagna: str = ""
    h10_lord_planet: str = ""
    d9_planet_dignities: Dict[str, str] = Field(default_factory=dict)

    # ── Primary D1 / divisional charts ───────────────────────────────────────
    planets_d1: Dict[str, Dict] = Field(default_factory=dict)
    divisional_charts: Dict[str, Dict] = Field(default_factory=dict)
    nakshatra_data: Dict[str, Any] = Field(default_factory=dict)   # str or dict per planet
    d9_lagna_sign: str = ""

    # ── D10 Dashamsha (career chart) ──────────────────────────────────────────
    # d10_house_occupancy already declared above; add lagna and house lords here.
    d10_lagna_sign: str = ""                                         # e.g. "Gemini"
    d10_house_lords: Dict[str, str] = Field(default_factory=dict)   # {"1":"Mars","10":"Saturn",...}

    # ── Nakshatra / Arudha / Karma Pada ──────────────────────────────────────
    moon_nakshatra: str = ""       # e.g. "Rohini"
    moon_nakshatra_pada: int = 0   # 1-4 (nakshatra quarter/pada of Moon)
    lagna_nakshatra: str = ""      # Nakshatra of the ascendant (lagna)
    arudha_lagna: str = ""         # A1 sign — Arudha Pada of H1
    a10_sign: str = ""             # Karma Pada (A10) — Arudha Pada of H10

    # ── Chara Karakas (remaining 5 — AK and AmK are above) ───────────────────
    matrikaraka: str = ""          # MK
    bhatrikaraka: str = ""         # BK
    putrakaraka: str = ""          # PK
    gnatikaraka: str = ""          # GnK
    darakaraka: str = ""           # DK

    # ── Planet-level sign and nakshatra maps ─────────────────────────────────
    planet_signs: Dict[str, str] = Field(default_factory=dict)       # {planet: D1 sign}
    planet_nakshatras: Dict[str, str] = Field(default_factory=dict)  # {planet: nakshatra name}

    # ── D10 Devata Diagnostics (4 career archetypes) ─────────────────────────
    # unemployed / salary_stagnant / promotion_blocked / sudden_halt
    # Each value: {archetype, pivot_planet, pivot_sign_d10, key_sign, key_lord, devata, insight}
    d10_devata_diagnostics: Dict[str, Any] = Field(default_factory=dict)

    # ── Full Vimshottari Dasha sequence (raw, with dates + Antardashas) ──────
    # The simplified dasha_sequence field above only has {lord, start_age, end_age}.
    # This field stores the complete raw sequence from pyhora_calculations so the
    # validation LLM can match actual career events to precise MD/AD date windows.
    vimshottari_dasha_full: List[Dict] = Field(default_factory=list)
    karakamsha_occupants: List[str] = Field(default_factory=list)
    neecha_bhanga_planets: List[str] = Field(default_factory=list)

    # ── User preferences / profile ────────────────────────────────────────────
    gender: str = ""
    interested_in: List[str] = Field(default_factory=list)
    already_excel_at: List[str] = Field(default_factory=list)
    brahma_lord: str = ""
    maheshwara_lord: str = ""
    birth_place: str = ""
    dob: str = ""
    GEMINI_API_KEY: str = ""

    # ── Career context (professionals only) ──────────────────────────────────
    career_context: dict = Field(default_factory=dict)
    career_timeline: list = Field(default_factory=list)
    kn_rao_jaimini: dict = Field(default_factory=dict)
    llm_context: dict = Field(default_factory=dict)
    llm_selection_rationale: str = Field(default="")
    micro_timing: dict = Field(default_factory=dict)
    corporate_entrepreneurial: dict = Field(default_factory=dict)
    geo_suitability: dict = Field(default_factory=dict)
    field_insights: dict = Field(default_factory=dict)
    academic_path: dict = Field(default_factory=dict)
    institutional_tier: dict = Field(default_factory=dict)
    career_phase: str = "auto"
