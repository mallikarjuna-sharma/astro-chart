"""Single declared calculation-and-doctrine policy object for this engine.

GAP-FIX (2026-07, audit item P0-2 / item 8): the audit found that different
modules made different implicit ayanamsha/school choices with no single
source of truth to check them against (concretely: ephemeris.py defaulted to
KP/Krishnamurti while transit_engine.py hardcoded Lahiri -- see the fix in
transit_engine.py's _compute_via_swisseph referencing this module). This
module is that single source of truth: every place in the codebase that
needs to declare "what ayanamsha/house-system/school am I using" should
import from here rather than hardcode a literal, and this is also the
`policy_json` fed to the LLM rule-trace validator (jyotish/llm_validator.py)
so the LLM can check policy CONSISTENCY (is every module actually using this
declared policy) without ever being asked to pick a policy itself, per the
do/don't list: "Do not use an LLM for ... inventing missing birth data or
silently selecting an ayanamsha/school."

This module does not compute anything. It is a policy declaration only.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

# ── Sidereal / ayanamsha policy ─────────────────────────────────────────────
# Confirmed against real chart data: every sample chart JSON's own
# system_config.ayanamsa field is "KP_Krishnamurti" (see Charts/*.json), and
# ephemeris.py's Skyfield-based ayanamsha formula already implements this
# specific ayanamsha. KP/Krishnamurti (not Lahiri) is therefore the engine's
# actual declared ayanamsha -- this is a factual statement about what the
# input data and majority of the codebase already do, not a new choice being
# introduced here.
AYANAMSHA = "KP_KRISHNAMURTI"

# pyswisseph's sidereal-mode constant for the ayanamsha above. Resolved lazily
# (pyswisseph may not be installed) rather than imported at module load time.
def _sidereal_mode_swe() -> int:
    try:
        import swisseph as swe  # type: ignore
        return swe.SIDM_KRISHNAMURTI
    except Exception:
        return 5  # SIDM_KRISHNAMURTI's numeric value in pyswisseph, as a last-resort fallback

SIDEREAL_MODE_SWE = _sidereal_mode_swe()

# ── House system policy, BY METHOD (not a single global choice) ────────────
# The audit correctly notes that Whole-Sign and Placidus houses genuinely
# coexist in this codebase for different, declared purposes -- that is not
# itself a bug, but every CONSUMER of a house placement needs to know which
# one it's reading. This is the declared mapping.
HOUSE_SYSTEM_BY_METHOD: Dict[str, str] = {
    "shadbala": "whole_sign",
    "gap_boosts": "whole_sign",
    "confluence_gate": "whole_sign",
    "vimshopaka": "whole_sign",
    "kp_significators": "placidus",
    "kp_cusps": "placidus",
    "transit_gochar": "whole_sign",
    # Anything not listed here should be treated as UNDECLARED and flagged by
    # the rule-trace validator, not assumed.
}

# ── Node (Rahu/Ketu) policy ─────────────────────────────────────────────────
NODE_TYPE = "true"  # vs "mean" -- matches system_config.node_type="True" in sample charts
NODE_ASPECT_CONVENTION = "5th_9th"  # matches astro.py's RAHU_KETU_ASPECT_MODE default;
                                     # configurable via that env var, NOT by this module or
                                     # any LLM call -- see astro.py's own docstring for the
                                     # documented alternate conventions ("7th_only", "none").
NODE_DIGNITY_SCHEME = "parashari_extended"  # this engine assigns Rahu/Ketu exaltation/
                                             # debilitation/own-sign per one commonly-used
                                             # (but NOT universally agreed) extended Parashari
                                             # convention -- flagged here as school-dependent,
                                             # matching the audit's item on this exact point.

# ── Jaimini karaka scheme ────────────────────────────────────────────────────
KARAKA_SCHEME = "7-karaka-no-nodes"  # matches provenance.py's
                                      # JAIMINI.CHARA_KARAKAS fact convention field;
                                      # the 8-karaka (Rahu-included) scheme is a
                                      # different school, not used here.

# ── Combustion / Cazimi doctrine ────────────────────────────────────────────
COMBUSTION_ORB_SOURCE = "BPHS (per-planet orbs, see constants._COMBUST_ORB)"
CAZIMI_DOCTRINE_NOTE = (
    "Cazimi (within 1 deg of the Sun granting a strength bonus rather than "
    "combustion) is a Hellenistic/Western astrological concept, not a "
    "classical Parashari Jyotish doctrine. This engine applies it as a "
    "deliberate, documented modeling choice (astro.py's eff_strengths "
    "cazimi_mod), not as a claim that it is classically Vedic. Flagged "
    "explicitly so the rule-trace validator does not mistake it for a "
    "Parashari rule."
)

# ── Dasha year-length convention ────────────────────────────────────────────
VIMSHOTTARI_YEAR_LENGTH_DAYS = 365.25  # tropical/Gregorian year length used for
                                        # MD/AD/PD age-boundary math throughout
                                        # engine.py -- NOT the sidereal/nakshatra
                                        # year some classical sources reference;
                                        # documented here as a school-dependent choice.

# ── Varga (divisional chart) conventions actually implemented ──────────────
VARGA_CONVENTIONS: Dict[str, str] = {
    "D9":  "sourced from upstream (pyhora); not rebuilt in-house; treated as trusted input",
    "D10": "Parashari odd/even 9th-sign-counted rule (astro.py.compute_d10_sign), in-house + tested",
    "D2":  "Parashari Hora (Sun/Moon split by half-sign) -- vimshopaka.py",
    "D3":  "Parashari Drekkana (same/5th/9th sign by decan) -- vimshopaka.py",
    "D7":  "Parashari Saptamsa (odd-from-same, even-from-7th) -- vimshopaka.py",
    "D12": "Parashari Dwadasamsa (sequential from same sign) -- vimshopaka.py",
    "D16": "Parashari Shodasamsa (movable/fixed/dual start-sign rule) -- vimshopaka.py",
    "D30": "Parashari Trimsamsa (unequal 5/5/8/7/5 deg planetary lords, BPHS) -- vimshopaka.py",
    "D60": "documented LOW-CONFIDENCE convention (simple cumulative sign advance); "
           "genuine cross-text variance exists for D60 specifically -- see "
           "vimshopaka.py's compute_d60_sign docstring. Any conclusion resting "
           "primarily on D60 should be treated as school-dependent and birth-time-sensitive.",
}

# ── Birth-time precision gating ─────────────────────────────────────────────
# Audit item P0-4: "Prevent strong KP/D60/cusp conclusions when birth-time
# precision is absent or insufficient." This is the single threshold every
# consumer (including the rule-trace validator) should check against.
BIRTH_TIME_UNCERTAINTY_HIGH_SENSITIVITY_MINUTES = 5


def data_quality_gate(payload: Any) -> Dict[str, Any]:
    """Score-neutral read of birth-time precision/uncertainty, for both the
    LLM validator's `birth_time_and_data_quality_json` input and any other
    consumer that needs to decide whether to suppress a KP/D60/cusp-precision
    claim. Does not change any score; purely descriptive."""
    def _get(name: str, default: Any = None) -> Any:
        if isinstance(payload, Mapping):
            return payload.get(name, default)
        return getattr(payload, name, default)

    precision = str(_get("birth_time_precision", "unknown") or "unknown")
    uncertainty_minutes = int(_get("birth_time_uncertainty_minutes", 0) or 0)
    high_sensitivity = (
        precision != "exact"
        or uncertainty_minutes >= BIRTH_TIME_UNCERTAINTY_HIGH_SENSITIVITY_MINUTES
    )
    return {
        "birth_time_precision": precision,
        "birth_time_uncertainty_minutes": uncertainty_minutes,
        "high_sensitivity_gate": high_sensitivity,
        "suppress_high_precision_claims": high_sensitivity,
        "affected_facts": (
            ["KP.CUSPS", "KP.SIGNIFICATORS", "D60.CHART", "D24.CHART",
             "ARUDHA_LAGNA", "SREE_LAGNA", "GHATI_LAGNA", "BHAVA_LAGNA", "HORA_LAGNA"]
            if high_sensitivity else []
        ),
    }


def build_policy_json() -> Dict[str, Any]:
    """The full declared-policy object -- fed to the LLM rule-trace validator
    as `policy_json` and usable by any other consumer that wants a single
    canonical reference instead of hardcoding a literal."""
    return {
        "ayanamsha": AYANAMSHA,
        "node_type": NODE_TYPE,
        "node_aspect_convention": NODE_ASPECT_CONVENTION,
        "node_dignity_scheme": NODE_DIGNITY_SCHEME,
        "karaka_scheme": KARAKA_SCHEME,
        "house_system_by_method": HOUSE_SYSTEM_BY_METHOD,
        "combustion_orb_source": COMBUSTION_ORB_SOURCE,
        "cazimi_doctrine_note": CAZIMI_DOCTRINE_NOTE,
        "vimshottari_year_length_days": VIMSHOTTARI_YEAR_LENGTH_DAYS,
        "varga_conventions": VARGA_CONVENTIONS,
        "birth_time_uncertainty_high_sensitivity_minutes": BIRTH_TIME_UNCERTAINTY_HIGH_SENSITIVITY_MINUTES,
    }
