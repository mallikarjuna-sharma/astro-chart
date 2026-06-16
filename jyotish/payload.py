"""JyotishAI — Payload dataclass and engine metadata."""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set, Any, Optional

ENGINE_VERSION = "v11.0-llm"

# Set LOG_LEVEL=DEBUG (env var) to log full LLM prompt + raw response.
# Default is INFO (summary messages only).
import os as _os
_log_level = getattr(logging, _os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=_log_level, format="%(levelname)s: %(message)s")
logger = logging.getLogger("jyotish_engine_v11_0")
logger.setLevel(_log_level)

@dataclass
class NatalPayloadV2:
    name: str = "Unknown"
    lagna_sign: str = ""
    lagna_lord: str = ""
    h10_lord: str = ""
    atmakaraka: str = ""
    amatyakaraka: str = ""
    karakamsha: str = ""
    planet_strength: Dict[str, float] = field(default_factory=dict)
    shadbala: Dict[str, float] = field(default_factory=dict)
    trait_level: Dict[str, float] = field(default_factory=dict)
    kp_h10: float = 0.5
    d10_strength: float = 0.5
    d24_strength: float = 0.5
    d9_strength: float = 0.5
    d60_strength: float = 0.5
    ketu_house: int = 0
    rahu_house: int = 0
    planet_house: Dict[str, int] = field(default_factory=dict)
    house_lords: Dict[str, str] = field(default_factory=dict)
    yogas_present: List[str] = field(default_factory=list)
    dasha_sequence: List[Dict] = field(default_factory=list)
    family_income_tier: str = "middle"
    school_board: str = "CBSE"
    current_age: float = 0.0
    sun_moon_degrees_apart: float = 0.0
    transit_house_positions: Dict[str, int] = field(default_factory=dict)
    pratyantar_dasha_lord: str = ""
    prd_lord_houses: List[int] = field(default_factory=list)
    divisional_planet_strength: Dict[str, Dict[str, float]] = field(default_factory=dict)
    sav_points_houses: Dict[str, int] = field(default_factory=dict)
    d10_house_occupancy: Dict[str, List[str]] = field(default_factory=dict)
    combust_planets: List[str] = field(default_factory=list)
    cazimi_planets: List[str] = field(default_factory=list)  # v8.7 ASTRO-2
    risk_appetite: str = "MODERATE"
    kp_significators: Dict[str, Dict] = field(default_factory=dict)
    kp_cusps: Dict[str, Dict] = field(default_factory=dict)
    planet_dignities: Dict[str, str] = field(default_factory=dict)
    d24_planet_dignities: Dict[str, str] = field(default_factory=dict)
    planet_retrograde: Dict[str, bool] = field(default_factory=dict)
    detected_yogas: List[str] = field(default_factory=list)
    h5_lord: str = ""
    amk_house: int = 0
    upapada_lagna: str = ""
    h10_lord_planet: str = ""
    d9_planet_dignities: Dict[str, str] = field(default_factory=dict)
    planets_d1: Dict[str, Dict] = field(default_factory=dict)          
    divisional_charts: Dict[str, Dict] = field(default_factory=dict)   
    nakshatra_data: Dict[str, str] = field(default_factory=dict)       
    d9_lagna_sign: str = ""                                            
    karakamsha_occupants: List[str] = field(default_factory=list)      
    neecha_bhanga_planets: List[str] = field(default_factory=list)     
    gender: str = ""                                                   
    interested_in: List[str] = field(default_factory=list)            
    already_excel_at: List[str] = field(default_factory=list)
    brahma_lord: str = ""                                              
    maheshwara_lord: str = ""                                          
    birth_place: str = ""
    dob: str = ""
    GEMINI_API_KEY: str = ""
