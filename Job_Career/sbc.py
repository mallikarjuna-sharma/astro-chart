"""
jyotish/sbc.py — Sarvatobhadra Chakra Manifestation Engine

ARCHITECTURE:
    D1/D9/D10/KP → Deterministic → LLM Ranking → SBC Layer → Final Career Probability

The SBC does NOT determine WHAT career. It answers:
  - Will the career manifest?          (natal SMI baseline)
  - How easily?                        (obstruction / protection ratio)
  - When?                              (transit activation windows)
  - What obstacles?                    (vedha sources)

OUTPUT:
    SMI (Sarvatobhadra Manifestation Index) per career field, range 0–100.
    Final score = career_score × (SMI / 100)

COMPONENTS:
    C1 — Natal Nakshatra Strength     (weight 0.35): Moon / Lagna / AK / 10th-lord nakshatras
    C2 — Career Nakshatra Resonance   (weight 0.40): field domain naks vs natal key-point naks
    C3 — Vedha Obstruction            (weight 0.25): natal malefic vedha on career nakshatras
    C4 — Transit Activation           (additive bonus, optional): current-sky planet nak hits
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── 27 Nakshatras (Abhijit excluded — not used in career SBC) ───────────────
NAKSHATRAS: List[str] = [
    "Ashwini",        "Bharani",         "Krittika",
    "Rohini",         "Mrigashira",      "Ardra",
    "Punarvasu",      "Pushya",          "Ashlesha",
    "Magha",          "Purva Phalguni",  "Uttara Phalguni",
    "Hasta",          "Chitra",          "Svati",
    "Vishakha",       "Anuradha",        "Jyeshta",
    "Moola",          "Purva Ashadha",   "Uttara Ashadha",
    "Shravana",       "Dhanishta",       "Shatabhisha",
    "Purva Bhadra",   "Uttara Bhadra",   "Revati",
]
_NAK_IDX: Dict[str, int] = {n: i for i, n in enumerate(NAKSHATRAS)}
_NAK_SPAN: float = 360.0 / 27  # 13°20'

_SIGN_ORDER: List[str] = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


def nakshatra_from_longitude(longitude: float) -> str:
    """Convert absolute ecliptic longitude (0–360°) → nakshatra name."""
    idx = int((longitude % 360) / _NAK_SPAN) % 27
    return NAKSHATRAS[idx]


def nakshatra_from_planet_d1(planet_data: Dict) -> str:
    """Derive nakshatra from planets_d1 entry {sign, degree, ...}."""
    sign = planet_data.get("sign", "Aries")
    degree_in_sign = float(planet_data.get("degree", 0) or 0)
    sign_idx = _SIGN_ORDER.index(sign) if sign in _SIGN_ORDER else 0
    longitude = sign_idx * 30.0 + degree_in_sign
    return nakshatra_from_longitude(longitude)


def nakshatra_from_sign_degree(sign: str, degree: float) -> str:
    sign_idx = _SIGN_ORDER.index(sign) if sign in _SIGN_ORDER else 0
    return nakshatra_from_longitude(sign_idx * 30.0 + degree)


# ─── Planet natures for obstruction vs protection scoring ────────────────────
_MALEFICS  = {"Saturn", "Mars", "Sun", "Rahu", "Ketu"}
_BENEFICS  = {"Jupiter", "Venus", "Mercury", "Moon"}
# Rahu/Ketu cast special vedha — included as malefics here


def _planet_nature(planet: str) -> str:
    if planet in _MALEFICS:  return "malefic"
    if planet in _BENEFICS:  return "benefic"
    return "neutral"


# ─── Classical SBC Vedha Pairs ────────────────────────────────────────────────
# Each tuple: (source_nak, target_nak, vedha_type)
# A planet in source_nak casts vedha (obstruction) on target_nak — bidirectional.
# Types:
#   "direct"   — full-strength opposition across the chakra centre (strength 1.00)
#   "diagonal" — 45° diagonal vedha                                 (strength 0.75)
#   "side"     — 90° side vedha                                     (strength 0.50)
#
# Sources: Uttara Kalamrita, Sarvatobhadra Chakra (Saravali tradition).
_VEDHA_PAIRS_RAW: List[Tuple[str, str, str]] = [
    # Direct (samana) vedha — nakshatras directly facing across the SBC centre
    ("Ashwini",        "Jyeshta",          "direct"),
    ("Bharani",        "Anuradha",         "direct"),
    ("Krittika",       "Vishakha",         "direct"),
    ("Rohini",         "Svati",            "direct"),
    ("Mrigashira",     "Chitra",           "direct"),
    ("Ardra",          "Hasta",            "direct"),
    ("Punarvasu",      "Uttara Phalguni",  "direct"),
    ("Pushya",         "Purva Phalguni",   "direct"),
    ("Ashlesha",       "Magha",            "direct"),
    ("Moola",          "Revati",           "direct"),
    ("Purva Ashadha",  "Uttara Bhadra",    "direct"),
    ("Uttara Ashadha", "Purva Bhadra",     "direct"),
    ("Shravana",       "Dhanishta",        "direct"),  # same-row pair
    # Diagonal vedha — nakshatras at 45° in the SBC grid
    ("Ashwini",        "Anuradha",         "diagonal"),
    ("Bharani",        "Jyeshta",          "diagonal"),
    ("Krittika",       "Svati",            "diagonal"),
    ("Rohini",         "Vishakha",         "diagonal"),
    ("Ardra",          "Purva Phalguni",   "diagonal"),
    ("Punarvasu",      "Hasta",            "diagonal"),
    ("Pushya",         "Chitra",           "diagonal"),
    ("Ashlesha",       "Uttara Phalguni",  "diagonal"),
    ("Moola",          "Purva Bhadra",     "diagonal"),
    ("Purva Ashadha",  "Purva Bhadra",     "diagonal"),
    ("Shatabhisha",    "Punarvasu",        "diagonal"),
    ("Uttara Bhadra",  "Uttara Ashadha",   "diagonal"),
    # Side vedha — nakshatras at 90° (cross-row connections)
    ("Ashwini",        "Svati",            "side"),
    ("Rohini",         "Jyeshta",          "side"),
    ("Krittika",       "Anuradha",         "side"),
    ("Bharani",        "Vishakha",         "side"),
    ("Punarvasu",      "Chitra",           "side"),
    ("Pushya",         "Hasta",            "side"),
    ("Moola",          "Uttara Bhadra",    "side"),
    ("Shravana",       "Shatabhisha",      "side"),
]

_VEDHA_STRENGTH_MAP: Dict[str, float] = {
    "direct": 1.00, "diagonal": 0.75, "side": 0.50
}

# Build bidirectional vedha lookup: {nak → [(target_nak, strength)]}
VEDHA_MAP: Dict[str, List[Tuple[str, float]]] = {n: [] for n in NAKSHATRAS}
for _s, _t, _typ in _VEDHA_PAIRS_RAW:
    _str_val = _VEDHA_STRENGTH_MAP[_typ]
    VEDHA_MAP[_s].append((_t, _str_val))
    VEDHA_MAP[_t].append((_s, _str_val))   # bidirectional


def get_vedha_strength(source_nak: str, target_nak: str) -> float:
    """Return vedha strength from source_nak to target_nak (0 if none)."""
    for tgt, strength in VEDHA_MAP.get(source_nak, []):
        if tgt == target_nak:
            return strength
    return 0.0


# ─── Dynamic Vedha maps (FIX 2): motion-state-dependent vedha direction ─────
# In SBC the direction a planet casts vedha depends on its astronomical speed:
#   Normal speed → Sammukha (Frontal) vedha: standard VEDHA_MAP above
#   Retrograde (Vakri) → Dakshina (Backward/Right) vedha: target shifts -1
#   Atichara (accelerated) → Vama (Forward/Left) vedha: target shifts +1
def _build_shifted_vedha_map(shift: int) -> Dict[str, List[Tuple[str, float]]]:
    shifted: Dict[str, List[Tuple[str, float]]] = {n: [] for n in NAKSHATRAS}
    for _s, _t, _typ in _VEDHA_PAIRS_RAW:
        _str_v = _VEDHA_STRENGTH_MAP[_typ]
        _t_idx = _NAK_IDX.get(_t, 0)
        _shifted_t = NAKSHATRAS[(_t_idx + shift) % 27]
        shifted[_s].append((_shifted_t, _str_v))
        shifted[_shifted_t].append((_s, _str_v))
    return shifted

# Retrograde planet (Vakri): casts Dakshina (right/backward) vedha
_DAKSHINA_VEDHA_MAP: Dict[str, List[Tuple[str, float]]] = _build_shifted_vedha_map(-1)
# Atichara planet (accelerated): casts Vama (left/forward) vedha
_VAMA_VEDHA_MAP:     Dict[str, List[Tuple[str, float]]] = _build_shifted_vedha_map(+1)

# Maximum daily motion thresholds for atichara detection
_ATICHARA_THRESHOLD: Dict[str, float] = {
    'Sun': 1.017, 'Moon': 13.183, 'Mars': 0.767, 'Mercury': 2.167,
    'Jupiter': 0.250, 'Venus': 1.267, 'Saturn': 0.133,
}


def _select_vedha_map(is_retrograde: bool,
                      is_atichara: bool) -> Dict[str, List[Tuple[str, float]]]:
    """Return the correct vedha map based on planet motion state."""
    if is_retrograde: return _DAKSHINA_VEDHA_MAP
    if is_atichara:   return _VAMA_VEDHA_MAP
    return VEDHA_MAP


def _check_atichara(planet: str, daily_motion: Optional[float]) -> bool:
    """True if planet's daily motion exceeds atichara threshold."""
    if daily_motion is None: return False
    return abs(daily_motion) > _ATICHARA_THRESHOLD.get(planet, 99.0)



# ─── Trikona (trinal) protection relationships ────────────────────────────────
# Nakshatras 9 apart (120° = same navamsha sign group) mutually support each other.
def _trikona_naks(nak: str) -> List[str]:
    idx = _NAK_IDX.get(nak, -1)
    if idx < 0: return []
    return [NAKSHATRAS[(idx + 9) % 27], NAKSHATRAS[(idx + 18) % 27]]


# ─── Career Domain → Nakshatra + Planet Activators ───────────────────────────
# For each domain: favorable nakshatras for manifestation of that career type.
# Planets: the "career activators" whose transit through career naks fires SMI.
CAREER_DOMAIN_NAKSHATRAS: Dict[str, Dict[str, List[str]]] = {
    "medicine": {
        "planets":     ["Sun", "Moon", "Mars", "Jupiter"],
        "nakshatras":  ["Ashwini", "Hasta", "Pushya", "Shatabhisha",
                        "Uttara Phalguni", "Ashlesha", "Punarvasu"],
    },
    "engineering": {
        "planets":     ["Mars", "Saturn", "Mercury"],
        "nakshatras":  ["Krittika", "Chitra", "Dhanishta", "Vishakha",
                        "Mrigashira", "Hasta", "Uttara Ashadha"],
    },
    "technology": {
        "planets":     ["Mercury", "Rahu", "Saturn"],
        "nakshatras":  ["Ashlesha", "Jyeshta", "Revati", "Ardra",
                        "Shatabhisha", "Shravana", "Punarvasu"],
    },
    "science": {
        "planets":     ["Saturn", "Ketu", "Mercury", "Rahu"],
        "nakshatras":  ["Moola", "Jyeshta", "Shatabhisha", "Ardra",
                        "Uttara Ashadha", "Purva Ashadha", "Revati"],
    },
    "law": {
        "planets":     ["Jupiter", "Saturn", "Mercury"],
        "nakshatras":  ["Punarvasu", "Vishakha", "Uttara Bhadra",
                        "Purva Bhadra", "Hasta", "Chitra"],
    },
    "commerce": {
        "planets":     ["Jupiter", "Venus", "Mercury", "Moon"],
        "nakshatras":  ["Rohini", "Purva Phalguni", "Uttara Phalguni",
                        "Hasta", "Revati", "Pushya"],
    },
    "management": {
        "planets":     ["Sun", "Jupiter", "Mercury"],
        "nakshatras":  ["Magha", "Uttara Phalguni", "Shravana",
                        "Dhanishta", "Punarvasu", "Vishakha"],
    },
    "arts": {
        "planets":     ["Venus", "Moon"],
        "nakshatras":  ["Purva Phalguni", "Bharani", "Rohini",
                        "Chitra", "Svati", "Mrigashira"],
    },
    "agriculture": {
        "planets":     ["Moon", "Mars", "Venus"],
        "nakshatras":  ["Rohini", "Mrigashira", "Hasta",
                        "Svati", "Revati", "Shravana"],
    },
    "defense": {
        "planets":     ["Mars", "Sun", "Ketu"],
        "nakshatras":  ["Krittika", "Vishakha", "Jyeshta",
                        "Moola", "Dhanishta", "Anuradha"],
    },
    "research": {
        "planets":     ["Ketu", "Rahu", "Saturn", "Jupiter"],
        "nakshatras":  ["Moola", "Jyeshta", "Shatabhisha",
                        "Ardra", "Purva Ashadha", "Uttara Bhadra"],
    },
    "education": {
        "planets":     ["Jupiter", "Mercury", "Moon"],
        "nakshatras":  ["Punarvasu", "Uttara Phalguni", "Shravana",
                        "Hasta", "Revati", "Pushya"],
    },
    "sports": {
        "planets":     ["Mars", "Sun"],
        "nakshatras":  ["Krittika", "Vishakha", "Jyeshta",
                        "Dhanishta", "Chitra", "Ashwini"],
    },
    "music": {
        "planets":     ["Venus", "Moon", "Mercury"],
        "nakshatras":  ["Purva Phalguni", "Rohini", "Svati",
                        "Bharani", "Mrigashira", "Revati"],
    },
    "psychology": {
        "planets":     ["Moon", "Ketu", "Mercury"],
        "nakshatras":  ["Ashlesha", "Jyeshta", "Uttara Bhadra",
                        "Shatabhisha", "Moola", "Purva Bhadra"],
    },
    "_default": {
        "planets":     ["Sun", "Jupiter", "Saturn"],
        "nakshatras":  ["Uttara Phalguni", "Shravana", "Uttara Ashadha"],
    },
}


# ─── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class SBCNode:
    """A nakshatra node in the Sarvatobhadra Chakra."""
    name:      str
    longitude: float          # absolute ecliptic longitude at node entry
    planet:    Optional[str] = None   # natal planet occupying this nakshatra


@dataclass
class VedhaLink:
    """A directed vedha (obstruction) from source to target nakshatra."""
    source:    str
    target:    str
    strength:  float   # 0.50 / 0.75 / 1.00
    planet:    str     # planet casting the vedha
    nature:    str     # "malefic" | "benefic" | "neutral"


@dataclass
class TransitActivation:
    """A transit-planet hit on a career nakshatra."""
    planet:         str
    transit_nak:    str
    career_nak:     str   # the career-domain nakshatra being hit
    hit_type:       str   # "direct_hit" | "vedha_hit" | "trikona_hit"
    score_delta:    float # positive = boost, negative = penalty


@dataclass
class SMIResult:
    """Full SMI breakdown for one career field."""
    field_id:            str
    domain:              str
    career_score:        float   # original engine score (20-100)
    smi:                 float   # Sarvatobhadra Manifestation Index (0-100)
    final_score:         float   # career_score × (smi / 100)
    c1_natal_strength:   float   # Component 1: 0-100
    c2_career_resonance: float   # Component 2: 0-100
    c3_vedha_obstruction:float   # Component 3: 0-100 (100 = no obstruction)
    transit_bonus:       float   # Component 4 additive delta
    key_protections:     List[str] = field(default_factory=list)
    key_obstructions:    List[str] = field(default_factory=list)
    transit_activations: List[TransitActivation] = field(default_factory=list)


# ─── Core Engine ──────────────────────────────────────────────────────────────
class SarvatobhadraEngine:
    """
    Post-ranking SBC manifestation layer.

    Usage:
        sbc = SarvatobhadraEngine(payload_data)
        results_with_smi = sbc.apply_to_ranking(ranked_career_results)
        # Each result now has: smi, final_score, sbc_detail keys added.
    """

    def __init__(self, payload_data: Any,
                 transit_planets: Optional[Dict[str, Dict]] = None):
        """
        Args:
            payload_data   : NatalPayloadV2 (or any object with the standard fields).
            transit_planets: Optional dict of {planet: {sign, degree}} for current sky.
                             If None, transit layer is skipped.
        """
        self.payload = payload_data
        self.transit_planets = transit_planets or {}

        # ── Extract natal data ────────────────────────────────────────────────
        self._planets_d1:  Dict = getattr(payload_data, "planets_d1", {})
        self._house_lords: Dict = getattr(payload_data, "house_lords", {})
        self._lagna_sign:  str  = getattr(payload_data, "lagna_sign", "Aries")
        self._lagna_deg:   float= float(getattr(payload_data, "lagna_degree", 0) or 0)
        self._ak:          str  = getattr(payload_data, "atmakaraka", "")
        self._amk:         str  = getattr(payload_data, "amatyakaraka", "")
        self._h10_lord:    str  = self._house_lords.get("10", "")

        # ── Precompute natal nakshatra positions ──────────────────────────────
        self._natal_naks:  Dict[str, str] = self._compute_natal_nakshatras()
        self._key_naks:    List[str]      = self._extract_key_nakshatras()
        # FIX 2B: extract natal retrograde flags — vedha direction depends on motion state
        self._natal_retro: Dict[str, bool] = {
            p: bool(d.get('retrograde', False))
            for p, d in self._planets_d1.items() if isinstance(d, dict)
        }
        self._natal_vedha: List[VedhaLink] = self._compute_natal_vedha()

        # ── Precompute transit nakshatra positions ────────────────────────────
        self._transit_naks: Dict[str, str] = self._compute_transit_nakshatras()

        logger.info("SBC: key natal nakshatras = %s", self._key_naks)
        logger.info("SBC: natal vedha links = %d", len(self._natal_vedha))

    # ── Public API ─────────────────────────────────────────────────────────────
    def compute_natal_strength(self) -> float:
        """
        C1: Natal Nakshatra Strength (0–100).

        Measures how protected vs obstructed the four key natal points are:
        Moon nakshatra, Lagna nakshatra, AK nakshatra, 10th-lord nakshatra.
        """
        return self._c1_natal_strength()

    def compute_vedha(self, career_nakshatras: List[str]) -> Tuple[float, List[str], List[str]]:
        """
        C3: Vedha obstruction of career nakshatras by natal malefics (0–100, 100=no obstruction).

        Returns (score_0_100, protection_labels, obstruction_labels).
        """
        return self._c3_vedha_obstruction(career_nakshatras)

    def compute_transit_activation(self, career_nakshatras: List[str],
                                   career_planets: List[str]) -> Tuple[float, List[TransitActivation]]:
        """
        C4: Transit planet hits on career nakshatras (additive delta, can be negative).

        Returns (delta, [TransitActivation, ...]).
        """
        return self._c4_transit_activation(career_nakshatras, career_planets)

    def compute_manifestation_index(self, domain: str) -> SMIResult:
        """
        Full SMI for one domain (0–100).

        SMI = 0.35×C1 + 0.40×C2 + 0.25×C3  (then clipped 0–100, transit adds ±Δ)
        """
        domain_data = CAREER_DOMAIN_NAKSHATRAS.get(domain,
                       CAREER_DOMAIN_NAKSHATRAS["_default"])
        career_naks  = domain_data["nakshatras"]
        career_planets = domain_data["planets"]

        c1 = self._c1_natal_strength()
        c2 = self._c2_career_resonance(career_naks)
        c3_score, protections, obstructions = self._c3_vedha_obstruction(career_naks)
        transit_delta, transit_acts = self._c4_transit_activation(career_naks, career_planets)

        smi_raw = 0.35 * c1 + 0.40 * c2 + 0.25 * c3_score
        smi     = round(max(0.0, min(100.0, smi_raw + transit_delta)), 1)

        return SMIResult(
            field_id="",          # filled in by caller
            domain=domain,
            career_score=0.0,     # filled in by caller
            smi=smi,
            final_score=0.0,      # filled in by caller
            c1_natal_strength=round(c1, 1),
            c2_career_resonance=round(c2, 1),
            c3_vedha_obstruction=round(c3_score, 1),
            transit_bonus=round(transit_delta, 1),
            key_protections=protections,
            key_obstructions=obstructions,
            transit_activations=transit_acts,
        )

    def apply_to_ranking(self, ranked_results: List[Dict]) -> List[Dict]:
        """
        Attach SMI as advisory timing metadata to the LLM-ranked career list.

        FIX 1 — CRITICAL ARCHITECTURAL CORRECTION:
        ═══════════════════════════════════════════
        The original design multiplied aptitude × (SMI/100), which CONFLATED:
          • Lifetime trait (aptitude)  — determined by D1/D9/D10/KP
          • Transient timing (SBC)     — determined by current planetary transits

        This is wrong.  A born engineer (aptitude 100) experiencing a temporary
        Saturn vedha (SMI 20) should NOT be told they scored 20 in engineering.
        They should be told: "Aptitude 100 — excellent fit. Timing 20% — delay now."

        CORRECT ARCHITECTURE (per audit recommendation):
          • Module 1 — Field Selection : ranks by aptitude_score ONLY (unchanged)
          • Module 2 — Event Timing    : SMI answers "Will it manifest? When?"

        This method therefore:
          ✓  Preserves the LLM aptitude ranking (final_score / rank unchanged)
          ✓  Attaches SMI, timing_band, obstructions, protections as metadata
          ✓  Computes sbc_event_score = aptitude × (smi/100) for EVENT PREDICTION only
             (e.g. "Will admission happen this year?") — NOT for field selection
          ✓  Does NOT re-sort by sbc_event_score
        """
        enriched: List[Dict] = []
        _domain_smi_cache: Dict[str, SMIResult] = {}

        for r in ranked_results:
            domain    = r.get("domain", "_default")
            career_sc = float(r.get("final_score", 50.0))

            if domain not in _domain_smi_cache:
                _domain_smi_cache[domain] = self.compute_manifestation_index(domain)
            smi_result = _domain_smi_cache[domain]

            extra_transit = self._check_field_ruling_planet_transit(
                r.get("affinity_planets", {}), domain)
            smi = round(max(0.0, min(100.0, smi_result.smi + extra_transit)), 1)

            # Timing band: human-readable manifestation window
            if smi >= 70:   timing_band = "High"
            elif smi >= 45: timing_band = "Moderate"
            else:           timing_band = "Low"

            enriched.append({
                **r,
                # ── Advisory SMI fields (timing / event prediction) ──────────
                "smi":             smi,
                "timing_band":     timing_band,    # "High" | "Moderate" | "Low"
                # sbc_event_score: for EVENT PREDICTION only ("Will IIT happen?")
                # Do NOT use this for field ranking / selection.
                "sbc_event_score": round(career_sc * (smi / 100.0), 2),
                "sbc_detail": {
                    "c1_natal_strength":    smi_result.c1_natal_strength,
                    "c2_benefic_activation":smi_result.c2_career_resonance,
                    "c3_vedha_obstruction": smi_result.c3_vedha_obstruction,
                    "transit_bonus":        smi_result.transit_bonus,
                    "key_protections":      smi_result.key_protections[:3],
                    "key_obstructions":     smi_result.key_obstructions[:3],
                    "career_nakshatras":    CAREER_DOMAIN_NAKSHATRAS.get(
                        domain, CAREER_DOMAIN_NAKSHATRAS["_default"])["nakshatras"][:4],
                    "vedha_mode_note": (
                        "Retrograde planets cast Dakshina (backward) vedha; "
                        "atichara planets cast Vama (forward) vedha."
                    ),
                },
            })

        # ── PRESERVE aptitude ranking — do NOT sort by sbc_event_score ───────
        # (aptitude determines WHAT career; SBC determines WHEN/HOW EASILY)
        logger.info(
            "SBC advisory layer applied to %d fields. "
            "Timing bands: High=%d Moderate=%d Low=%d. "
            "Aptitude ranking preserved.",
            len(enriched),
            sum(1 for r in enriched if r["timing_band"] == "High"),
            sum(1 for r in enriched if r["timing_band"] == "Moderate"),
            sum(1 for r in enriched if r["timing_band"] == "Low"),
        )
        return enriched

    # ── Private Helpers ────────────────────────────────────────────────────────
    def _compute_natal_nakshatras(self) -> Dict[str, str]:
        """Map every natal planet → its nakshatra."""
        result: Dict[str, str] = {}
        for planet, data in self._planets_d1.items():
            if isinstance(data, dict):
                result[planet] = nakshatra_from_planet_d1(data)
        # Lagna
        result["Lagna"] = nakshatra_from_sign_degree(self._lagna_sign, self._lagna_deg)
        return result

    def _extract_key_nakshatras(self) -> List[str]:
        """Four key natal points: Moon, Lagna, AK, 10th Lord."""
        keys = []
        for label in ("Moon", "Lagna", self._ak, self._h10_lord):
            if label and label in self._natal_naks:
                nak = self._natal_naks[label]
                if nak not in keys:
                    keys.append(nak)
        if not keys:
            keys = [self._natal_naks.get("Moon", "Ashwini")]
        return keys

    def _compute_natal_vedha(self) -> List[VedhaLink]:
        """Precompute natal vedha links using motion-aware vedha direction (FIX 2C).

        Natal retrograde planets cast Dakshina (backward) vedha.
        Natal direct planets cast Sammukha (frontal) vedha.
        Atichara is not applied to natal positions (it is a transit phenomenon).
        """
        links: List[VedhaLink] = []
        for planet, pnak in self._natal_naks.items():
            if planet == "Lagna": continue
            is_retro = self._natal_retro.get(planet, False)
            vmap = _DAKSHINA_VEDHA_MAP if is_retro else VEDHA_MAP
            for (tgt, strength) in vmap.get(pnak, []):
                links.append(VedhaLink(
                    source=pnak, target=tgt, strength=strength,
                    planet=planet, nature=_planet_nature(planet)
                ))
        return links

    def _compute_transit_nakshatras(self) -> Dict[str, str]:
        """Map current-sky transit planets → their nakshatras."""
        result: Dict[str, str] = {}
        for planet, data in self.transit_planets.items():
            if isinstance(data, dict):
                result[planet] = nakshatra_from_planet_d1(data)
        return result

    # ── Component computations ─────────────────────────────────────────────────
    def _c1_natal_strength(self) -> float:
        """
        C1: How well-placed are the four key natal nakshatras? (0–100)

        Logic:
          - Start at 60 (neutral)
          - Natal benefics whose nakshatra is in trikona to a key nak → +8 each
          - Natal malefics casting direct vedha on a key nak → -15 each
          - Natal malefics casting diagonal vedha on a key nak → -10 each
          - Natal malefics casting side vedha on a key nak → -6 each
          - Natal benefics casting vedha → still an obstruction (strict SBC:
            vedha = obstruction regardless of the obstructing planet's
            nature), but at reduced severity vs a malefic vedha.

        GAP-FIX (2026-08-22, audit item #21): a benefic's vedha was
        previously treated as a *protective bonus* (+4 each). Classical SBC
        (Sarvatobhadra Chakra) vedha is an obstruction/blocking relationship
        by definition, independent of whether the obstructing planet is a
        natural benefic or malefic — a benefic's vedha is a softer
        obstruction, not a reversal into protection. Changed to a smaller
        malus instead of a bonus.
        """
        score = 60.0
        key_naks = set(self._key_naks)

        for link in self._natal_vedha:
            if link.target not in key_naks:
                continue
            if link.nature == "malefic":
                penalty_map = {1.00: 15.0, 0.75: 10.0, 0.50: 6.0}
                score -= penalty_map.get(link.strength, 6.0)
            elif link.nature == "benefic":
                # Vedha is obstruction regardless of planet nature; a
                # benefic's vedha is milder than a malefic's, not protective.
                penalty_map = {1.00: 6.0, 0.75: 4.0, 0.50: 2.5}
                score -= penalty_map.get(link.strength, 2.5)

        # Trikona relationship bonus: a natal benefic in trikona of key nak → protect
        for planet, pnak in self._natal_naks.items():
            if planet == "Lagna": continue
            if _planet_nature(planet) == "benefic":
                trikona = _trikona_naks(pnak)
                for knak in self._key_naks:
                    if knak in trikona:
                        score += 8.0; break  # once per planet

        return round(max(0.0, min(100.0, score)), 1)

    def _c2_career_resonance(self, career_nakshatras: List[str]) -> float:
        """
        C2: Benefic Activation (FIX 3) — 0–100.

        This is the POSITIVE counterpart to C3 (malefic obstruction).
        Measures how actively natal benefics (Jupiter, Venus, Mercury, Moon)
        cast vedha on or trikona-align with career domain nakshatras.

        A Jupiter vedha on a career nakshatra = massive manifestation boost.
        A Venus vedha on an arts nakshatra = almost guaranteed artistic success.
        This signal must carry 40% weight to properly offset C3 malefic obstructions.

        Scoring layers (using motion-aware vedha for retrograde benefics):
          1. Benefic vedha → career nakshatra:  weight × strength × 25 pts
          2. Benefic trikona → career nakshatra: weight × 15 pts
          3. Benefic directly occupies career nakshatra: weight × 20 pts
          4. AK / H10-lord in career nakshatra group: +12 / +10 pts (soul alignment)
        """
        career_nak_set = set(career_nakshatras)
        score = 0.0
        # Benefic weights: Jupiter = primary, Moon = secondary (waning Moon less)
        _BW = {'Jupiter': 1.00, 'Venus': 0.85, 'Moon': 0.75, 'Mercury': 0.70}

        for planet, pnak in self._natal_naks.items():
            if planet == 'Lagna': continue
            weight = _BW.get(planet, 0.0)
            if weight == 0.0: continue

            # Use motion-aware vedha map (retrograde benefic casts Dakshina vedha)
            is_retro = self._natal_retro.get(planet, False)
            vmap = _DAKSHINA_VEDHA_MAP if is_retro else VEDHA_MAP

            # Layer 1: benefic vedha hitting a career nakshatra
            for (tgt, strength) in vmap.get(pnak, []):
                if tgt in career_nak_set:
                    score += weight * strength * 25.0

            # Layer 2: benefic in trikona of a career nakshatra
            for trinak in _trikona_naks(pnak):
                if trinak in career_nak_set:
                    score += weight * 15.0; break  # once per planet

            # Layer 3: benefic directly occupies a career nakshatra
            if pnak in career_nak_set:
                score += weight * 20.0

        # Layer 4: AK / H10-lord in career nakshatras = soul-level alignment
        ak_nak  = self._natal_naks.get(self._ak, '')
        h10_nak = self._natal_naks.get(self._h10_lord, '')
        amk_nak = self._natal_naks.get(self._amk, '')
        if ak_nak  in career_nak_set: score += 12.0
        if h10_nak in career_nak_set: score += 10.0
        if amk_nak in career_nak_set: score += 8.0

        # Normalise: max theoretical ≈ 4 benefics × (25+15+20) = 240, + 30 alignment = 270
        _MAX = 270.0
        return round(max(0.0, min(100.0, (score / _MAX) * 100.0)), 1)

    def _c3_vedha_obstruction(self, career_nakshatras: List[str]
                              ) -> Tuple[float, List[str], List[str]]:
        """
        C3: Are career nakshatras being blocked by natal malefic vedha? (0–100, 100=clean)

        Returns (score, protection_labels, obstruction_labels).
        """
        career_nak_set = set(career_nakshatras)
        obstruction_total = 0.0
        protection_total  = 0.0
        obstructions: List[str] = []
        protections:  List[str] = []

        for link in self._natal_vedha:
            if link.target not in career_nak_set:
                continue
            if link.nature == "malefic":
                penalty = link.strength * 20.0
                obstruction_total += penalty
                obstructions.append(
                    f"{link.planet}({link.source})→{link.target} "
                    f"[{'-' + str(round(penalty)):>6}pts]"
                )
            elif link.nature == "benefic":
                bonus = link.strength * 10.0
                protection_total += bonus
                protections.append(
                    f"{link.planet}({link.source})→{link.target} "
                    f"[+{round(bonus)}pts]"
                )

        net_obstruction = max(0.0, obstruction_total - protection_total)
        score = max(0.0, min(100.0, 100.0 - net_obstruction))
        return round(score, 1), protections, obstructions

    def _c4_transit_activation(self, career_nakshatras: List[str],
                               career_planets: List[str]
                               ) -> Tuple[float, List[TransitActivation]]:
        """
        C4: Current-sky transit activations of career nakshatras (additive delta).

        Rules:
          +15 if transit Jupiter/Venus hits a career nakshatra directly
          +10 if transit Jupiter hits a trikona of key natal nak AND career nak
          -12 if transit Saturn/Rahu casts vedha on a key natal nak
          -8  if transit Mars/Ketu casts vedha on a career nakshatra
          +8  if transit planet is one of career_planets and hits a career nak
        """
        if not self._transit_naks:
            return 0.0, []

        career_nak_set = set(career_nakshatras)
        key_nak_set    = set(self._key_naks)
        delta = 0.0
        acts: List[TransitActivation] = []

        for planet, tnak in self._transit_naks.items():
            nature = _planet_nature(planet)
            # FIX 2D: read retrograde and daily_motion from transit planet data
            t_data    = self.transit_planets.get(planet, {})
            t_retro   = bool(t_data.get('retrograde', False))
            t_motion  = t_data.get('daily_motion', None)
            t_atichar = _check_atichara(planet, t_motion)
            t_vmap    = _select_vedha_map(t_retro, t_atichar)

            # Direct hit on a career nakshatra
            if tnak in career_nak_set:
                if planet in ("Jupiter", "Venus"):
                    d = 15.0
                elif planet in career_planets:
                    d = 8.0
                elif nature == "malefic":
                    d = -6.0
                else:
                    d = 4.0
                delta += d
                motion_tag = '/retro' if t_retro else ('/atichar' if t_atichar else '')
                acts.append(TransitActivation(planet, tnak, tnak,
                                              f"direct_hit{motion_tag}", d))

            # Vedha from transit planet onto a key natal nakshatra
            # Uses motion-aware vedha map (FIX 2D)
            for (vedha_tgt, strength) in t_vmap.get(tnak, []):
                if vedha_tgt in key_nak_set:
                    if nature == "malefic" and planet in ("Saturn", "Rahu"):
                        d = -12.0 * strength
                        delta += d
                        acts.append(TransitActivation(
                            planet, tnak, vedha_tgt,
                            f"vedha_hit{'[retro]' if t_retro else ''}",
                            round(d, 1)))
                    elif nature == "malefic":
                        d = -6.0 * strength
                        delta += d
                        acts.append(TransitActivation(
                            planet, tnak, vedha_tgt, "vedha_hit", round(d, 1)))
                    elif nature == "benefic":
                        d = 6.0 * strength
                        delta += d
                        acts.append(TransitActivation(
                            planet, tnak, vedha_tgt, "vedha_hit", round(d, 1)))

            # Trikona of transit planet's nak overlapping career nakshatras
            for trinak in _trikona_naks(tnak):
                if trinak in career_nak_set and nature == "benefic":
                    d = 5.0
                    delta += d
                    acts.append(TransitActivation(
                        planet, tnak, trinak, "trikona_hit", d))
                    break  # once per planet

        # Cap transit delta
        delta = max(-25.0, min(20.0, delta))
        return round(delta, 1), acts

    def _check_field_ruling_planet_transit(self, affinity_planets: Dict[str, float],
                                            domain: str = "") -> float:
        """
        Per-field personalisation: if this field's top affinity planet is currently
        in one of ITS OWN FIELD'S career nakshatras, give a small +4 personalisation
        bonus.

        GAP-FIX (2026-08-22): previously looped over ALL domains in
        CAREER_DOMAIN_NAKSHATRAS instead of just the current field's own domain
        (the `domain` parameter was never passed in), so a field could receive
        the +4.0 bonus based on an unrelated domain's ruling-planet/nakshatra
        list. Now scoped to the current field's own domain only.
        """
        if not self._transit_naks or not affinity_planets:
            return 0.0
        top_planet = max(affinity_planets.items(), key=lambda x: x[1])[0]
        tnak = self._transit_naks.get(top_planet, "")
        if not tnak:
            return 0.0
        _dom_data = CAREER_DOMAIN_NAKSHATRAS.get(domain)
        if not _dom_data:
            return 0.0
        if (top_planet in _dom_data["planets"] and
                tnak in _dom_data["nakshatras"]):
            return 4.0
        return 0.0


# ─── Pipeline Integration Helper ──────────────────────────────────────────────
def apply_sbc_manifestation(
    ranked_results: List[Dict],
    payload_data: Any,
    transit_planets: Optional[Dict[str, Dict]] = None,
    enabled: bool = True,
) -> List[Dict]:
    """
    Drop-in post-ranking SBC layer.

    Inserts SMI, sbc_final_score, sbc_detail, sbc_rank into every result dict.
    Re-sorts by sbc_final_score.

    Args:
        ranked_results:  Output of the LLM+guard stage (list of field dicts).
        payload_data:    NatalPayloadV2.
        transit_planets: Optional current-sky {planet: {sign, degree}} for timing.
        enabled:         Kill-switch (if False, returns ranked_results unchanged).
    """
    if not enabled or not ranked_results:
        return ranked_results
    try:
        engine = SarvatobhadraEngine(payload_data, transit_planets=transit_planets)
        return engine.apply_to_ranking(ranked_results)
    except Exception as exc:
        logger.warning("SBC layer failed (%s) — returning original ranking", exc)
        return ranked_results


# ─── Standalone admission/event prediction ────────────────────────────────────
def predict_manifestation_probability(
    payload_data: Any,
    event_type: str,
    event_domain: str,
    transit_planets: Optional[Dict[str, Dict]] = None,
) -> Dict:
    """
    Predict probability that a specific career event will manifest.

    event_type:   "admission" | "placement" | "promotion" | "foreign_admission"
    event_domain: career domain (e.g. "engineering", "medicine")

    Returns:
        {
          "event_type": ...,
          "smi": 0-100,
          "manifestation_band": "High" | "Moderate" | "Low",
          "key_factors": [...],
          "key_obstacles": [...],
          "transit_window": "Active" | "Dormant" (if transit data provided),
        }
    """
    try:
        engine = SarvatobhadraEngine(payload_data, transit_planets=transit_planets)
        smi_result = engine.compute_manifestation_index(event_domain)
        smi = smi_result.smi

        if smi >= 70:   band = "High"
        elif smi >= 45: band = "Moderate"
        else:           band = "Low"

        transit_window = "Unknown"
        if transit_planets:
            if smi_result.transit_bonus >= 8:   transit_window = "Active"
            elif smi_result.transit_bonus <= -8: transit_window = "Obstructed"
            else:                                transit_window = "Neutral"

        return {
            "event_type":        event_type,
            "event_domain":      event_domain,
            "smi":               smi,
            "manifestation_band":band,
            "key_protections":   smi_result.key_protections[:3],
            "key_obstructions":  smi_result.key_obstructions[:3],
            "transit_window":    transit_window,
            "transit_bonus":     smi_result.transit_bonus,
            "c1_natal_strength": smi_result.c1_natal_strength,
            "c2_resonance":      smi_result.c2_career_resonance,
            "c3_vedha_clean":    smi_result.c3_vedha_obstruction,
        }
    except Exception as exc:
        logger.error("SBC event prediction failed: %s", exc)
        return {"smi": 50, "manifestation_band": "Unknown", "error": str(exc)}
