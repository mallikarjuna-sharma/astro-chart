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
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "v11.3-llm"

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
    dob: str = ""
    tob: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    timezone_offset_hours: Optional[float] = None
    external_llm_consent: bool = False
    redact_debug_output: bool = True
    data_retention_policy: str = "SESSION_ONLY"
    # Initialized once by run_engine(); all precision-sensitive modules consume
    # this immutable object rather than choosing local calculation conventions.
    calculation_policy: Any = None
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
    # 2026-07-08: real per-planet Bhinnashtakavarga (BAV), computed in-house
    # (jyotish/ashtakavarga.py) from natal planet signs + lagna, since pyhora's
    # raw output only ever carried the combined SAV total (sav_points_houses
    # above) with no per-planet breakdown. {planet: {house_str "1".."12": bindu}}.
    # Consumed by boosts.py's R3-13 _bav_individual_boost (previously always
    # inert because bav_scores was never populated — see md/DEEP_AUDIT_GAPS_2026-07.md).
    bav_points: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    d10_house_occupancy: Dict[str, List[str]] = Field(default_factory=dict)
    # 2026-07 astrologer's audit: full six-fold Shadbala (Sthana/Dig/Kala/
    # Cheshta/Naisargika/Drishti Bala), computed from first principles by
    # jyotish/shadbala.py::compute_shadbala_all(), instead of only the
    # upstream single-number `shadbala_virupas` ingestion (see `shadbala`
    # field below). ADDITIVE -- no existing scoring code reads this yet;
    # exposed so it can be validated against real charts before any caller
    # switches over to trust it as the primary strength signal.
    shadbala_computed: Dict[str, Any] = Field(default_factory=dict)

    # ── Planetary state ───────────────────────────────────────────────────────
    combust_planets: List[str] = Field(default_factory=list)
    cazimi_planets: List[str] = Field(default_factory=list)   # v8.7 ASTRO-2
    risk_appetite: str = "MODERATE"
    kp_significators: Dict[str, Dict] = Field(default_factory=dict)
    kp_cusps: Dict[str, Dict] = Field(default_factory=dict)
    planet_dignities: Dict[str, str] = Field(default_factory=dict)
    # Gap fix (2026-07-05 audit): planet_dignities gets overwritten to literal "OWN"
    # for planets in a Parivartana (mutual sign exchange) — see engine_io.py's
    # "Apply Parivartana Dignity Upgrade" step. That overwrite is needed upstream
    # for scoring continuity (dignity multiplier lookups), but it destroys the
    # true natal dignity for display purposes, producing reports that say e.g.
    # "Lagna Lord Mercury — OWN" when Mercury is actually debilitated in Pisces
    # and only strengthened via exchange with Jupiter. true_planet_dignities
    # preserves the pre-overwrite value, and parivartana_pairs records which
    # planets are in exchange with which, so display code can render an
    # accurate label (e.g. "Mercury — DEBILITATED (Parivartana exchange w/ Jupiter)").
    true_planet_dignities: Dict[str, str] = Field(default_factory=dict)
    parivartana_pairs: Dict[str, str] = Field(default_factory=dict)
    d24_planet_dignities: Dict[str, str] = Field(default_factory=dict)
    planet_retrograde: Dict[str, bool] = Field(default_factory=dict)
    retrograde_planets: Set[str] = Field(default_factory=set)   # C-2: set of currently retrograde planets
    detected_yogas: List[str] = Field(default_factory=list)

    # ── Lord / special points ─────────────────────────────────────────────────
    h5_lord: str = ""
    amk_house: int = 0
    upapada_lagna: str = ""
    h10_lord_planet: str = ""
    d9_planet_dignities: Dict[str, str] = Field(default_factory=dict)
    # Gap 0.3 fix: D10 dignities were read by knrao/parashara/dashamsha but never
    # declared or populated. Populated in engine._run_normalization_stage.
    d10_planet_dignities: Dict[str, str] = Field(default_factory=dict)

    # ── Gap 0.4 fix: birth-time quality + absolute longitudes ────────────────
    # birth_time_precision: "exact" | "approximate" | "unknown" — gates KP sublord
    # confidence (kp.py Q4/T3-C). Supplied by chart JSON when available.
    birth_time_precision: str = "unknown"
    # Minutes of birth-time uncertainty — gates timeline FIX-1 KP/D10 degradation.
    birth_time_uncertainty_minutes: int = 0
    # Absolute sidereal longitudes {planet: 0-360} — computed from planets_d1
    # sign+degree in engine_io (enables real Gandanta detection in timeline.py).
    planet_longitudes: Dict[str, float] = Field(default_factory=dict)
    # 2026-07-08 ephemeris fix (jyotish/ephemeris.py): genuine Swiss-Ephemeris
    # sidereal longitudes {planet: 0-360}, computed directly from birth
    # datetime+lat/lon (KP/Krishnamurti ayanamsa, TRUE_NODE) — independent
    # cross-check of the pyhora-supplied planets_d1 sign/degree values above.
    planet_natal_degrees: Dict[str, float] = Field(default_factory=dict)
    # Same, for "today" (system_config.current_date) — real ephemeris
    # replacement for the previously-empty planet_transit_degrees field.
    planet_transit_degrees: Dict[str, float] = Field(default_factory=dict)
    # Birth tithi number 1-30 — computed from Sun/Moon longitudes in engine_io
    # (enables the P2 Panchanga tithi-lord signal in engine.py).
    birth_tithi_num: int = 0
    # D24 whole-sign house occupancy {house_str: [planets]} — computed in engine_io
    # (enables timeline d24_skill_bonus).
    d24_house_occupancy: Dict[str, List[str]] = Field(default_factory=dict)

    # ── Primary D1 / divisional charts ───────────────────────────────────────
    planets_d1: Dict[str, Dict] = Field(default_factory=dict)
    divisional_charts: Dict[str, Dict] = Field(default_factory=dict)
    nakshatra_data: Dict[str, Any] = Field(default_factory=dict)   # str or dict per planet
    d9_lagna_sign: str = ""

    # ── D10 Dashamsha (career chart) ──────────────────────────────────────────
    # d10_house_occupancy already declared above; add lagna and house lords here.
    d10_lagna_sign: str = ""                                         # e.g. "Gemini"
    d10_house_lords: Dict[str, str] = Field(default_factory=dict)   # {"1":"Mars","10":"Saturn",...}
    d10_planet_sign: Dict[str, str] = Field(default_factory=dict)   # C-2: {planet: D10 sign}

    # ── D24 Siddhamsha (education chart) — E-1 EduAlign ─────────────────────
    d24_lagna_sign: str = ""                                          # e.g. "Virgo"
    d24_house_lords: Dict[str, str] = Field(default_factory=dict)    # {"1":"Mercury","10":"Jupiter",...}

    # ── Karakamsha ────────────────────────────────────────────────────────────
    karakamsha_sign: str = ""   # C-3: sign of the karakamsha (D9 position of AK)

    # ── Special Lagnas (computed from birth time + sunrise) ───────────────────
    hora_lagna_sign:  str = ""   # Hora Lagna (wealth/income timing — advances 1 sign/hr)
    ghati_lagna_sign: str = ""   # Ghati Lagna (power/authority — advances 1 sign/24 min)
    sree_lagna_sign:  str = ""   # Sree Lagna (Lakshmi/prosperity)
    # GAP-FIX (2026-07): Bhava Lagna and Bhrigu Bindu, previously entirely
    # absent (no field, no computation) -- see ephemeris.get_bhava_lagna /
    # get_bhrigu_bindu and engine_io.py's wiring.
    bhava_lagna_sign:   str = ""   # Bhava Lagna (general vocational/status lagna)
    bhrigu_bindu_sign:  str = ""   # Bhrigu Bindu (Rahu-Moon midpoint, destiny-turning-point)

    # ── KP star/sub lord chain for Lagna and Moon (bonus wiring, 2026-07-08) ──
    # Computed via ephemeris.compute_kp_sublords() on the real absolute sidereal
    # longitude of Lagna / Moon — same generic function already used for the
    # KP cusp chain above, just applied to two additional longitudes.
    lagna_star_lord: str = ""
    lagna_sub_lord:  str = ""
    moon_star_lord:  str = ""
    moon_sub_lord:   str = ""

    # ── Extended Divisional Chart Dignities (optional) ────────────────────────
    d3_planet_dignities:  Dict[str, str] = Field(default_factory=dict)  # Drekkana (skills)
    d20_planet_dignities: Dict[str, str] = Field(default_factory=dict)  # Vimshamsha (spiritual)
    d30_planet_dignities: Dict[str, str] = Field(default_factory=dict)  # Trimsamsha (obstacles)

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

    # Structured alias of all 7 Chara Karakas keyed by their standard
    # abbreviation (AK/AmK/BK/MK/PK/GK/DK), sourced directly from pyhora's
    # kn_rao_jaimini_data.chara_karakas block. This is purely additive: the
    # flat atmakaraka/amatyakaraka/matrikaraka/bhatrikaraka/putrakaraka/
    # gnatikaraka/darakaraka fields above remain the source of truth for
    # existing callers; this dict lets new code look karakas up generically
    # (e.g. payload.chara_karakas["AK"]) without breaking anything.
    chara_karakas: Dict[str, str] = Field(default_factory=dict)

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

    # ── 2026-07-08 7-item lookup/derivation gap fixes ────────────────────────
    # Gap 1: weekday ruler of the birth date (Sunday=Sun .. Saturday=Saturn).
    day_lord: str = ""
    # Gap 2: nakshatra-lord (Vimshottari 27-nakshatra cyclic lookup) for the
    # Moon's own nakshatra, and for every planet's nakshatra (planet_nakshatras
    # already populated elsewhere; this is the lord derived from that value).
    moon_nakshatra_lord: str = ""
    planet_nakshatra_lord: Dict[str, str] = Field(default_factory=dict)
    # Gap 3: Moon's nakshatra pada (1-4), derived from absolute longitude —
    # moon_nakshatra_pada (declared above) was previously stuck at a
    # sign-degree-only calc; this numeric alias is guaranteed non-zero
    # whenever moon_nakshatra_pada itself is populated. Kept as a separate
    # field name (not a rename) so existing consumers of moon_nakshatra_pada
    # are unaffected.
    moon_nakshatra_pada_num: int = 0
    # Gap 4: D27 (Nakshatramsha) dignity-based per-planet strength score,
    # 0-1, same convention as the existing D10/D9 strength scoring.
    d27_planet_strengths: Dict[str, float] = Field(default_factory=dict)
    d27_planet_dignities: Dict[str, str] = Field(default_factory=dict)
    # Gap 5: consolidated per-planet dignity across D9/D10/D24/D27.
    varga_dignities: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    # Gap 6: Prastarashtakavarga — full unreduced 8-source x 12-house grid
    # per reference planet (see jyotish/ashtakavarga.py::compute_pav_data
    # for the documented output shape).
    pav_data: Dict[str, Dict[str, Dict[str, int]]] = Field(default_factory=dict)
