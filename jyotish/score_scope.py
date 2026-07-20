"""Authoritative scope declarations for score-producing signals.

This module is deliberately independent of the ranking implementation.  It is
the contract used while the legacy final score remains frozen and the clean
permanent/timing/education axes are introduced in shadow mode.
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable


class ScoreScope(str, Enum):
    PERMANENT = "PERMANENT"
    TIMING = "TIMING"
    EDUCATION = "EDUCATION"
    PREFERENCE = "PREFERENCE"
    PRACTICAL = "PRACTICAL"
    DISALLOWED = "DISALLOWED"


SIGNAL_SCOPE: dict[str, ScoreScope] = {
    "d1_tenth_house": ScoreScope.PERMANENT,
    "d10_h10": ScoreScope.PERMANENT,
    "d10_lagna_lord": ScoreScope.PERMANENT,
    "ak_amk": ScoreScope.PERMANENT,
    "karakamsha": ScoreScope.PERMANENT,
    "dignity": ScoreScope.PERMANENT,
    "kp_vocational": ScoreScope.PERMANENT,
    "karakamsha": ScoreScope.PERMANENT,
    "yogakaraka": ScoreScope.PERMANENT,
    "h10_lord_str": ScoreScope.PERMANENT,
    "h10_lord_trikona": ScoreScope.PERMANENT,
    "exalted_domain": ScoreScope.PERMANENT,
    "d9_ak": ScoreScope.PERMANENT,
    "yoga": ScoreScope.PERMANENT,
    "h5_lord": ScoreScope.PERMANENT,
    "amk_house": ScoreScope.PERMANENT,
    "ak_house": ScoreScope.PERMANENT,
    "karakamsha_occ": ScoreScope.PERMANENT,
    "d9_h10": ScoreScope.PERMANENT,
    "dharma_karma": ScoreScope.PERMANENT,
    "d10_comprehensive": ScoreScope.PERMANENT,
    "aspect_h10": ScoreScope.PERMANENT,
    "nakshatra_career": ScoreScope.PERMANENT,
    "nodal_axis": ScoreScope.PERMANENT,
    "material_grit": ScoreScope.PERMANENT,
    "ak_domain_flat": ScoreScope.PERMANENT,
    "dasha_bonus": ScoreScope.TIMING,
    "prime_dasha_affinity": ScoreScope.TIMING,
    "peak_md_boost": ScoreScope.TIMING,
    "prd_boost": ScoreScope.TIMING,
    "antardasha_affinity": ScoreScope.TIMING,
    "chara_dasha": ScoreScope.TIMING,
    "transit_activation": ScoreScope.TIMING,
    "compound_dasha_quality": ScoreScope.TIMING,
    "dasha_timing_gate": ScoreScope.TIMING,
    "d24_ak": ScoreScope.EDUCATION,
    "d24_full": ScoreScope.EDUCATION,
    "bhavesha_phala": ScoreScope.EDUCATION,
    "d24_field_score": ScoreScope.EDUCATION,
    "interest_pref": ScoreScope.PREFERENCE,
    "risk_appetite": ScoreScope.PRACTICAL,
    "gender_field": ScoreScope.DISALLOWED,
}

_PREFIX_SCOPE: tuple[tuple[str, ScoreScope], ...] = (
    ("dasha_", ScoreScope.TIMING),
    ("peak_", ScoreScope.TIMING),
    ("prd_", ScoreScope.TIMING),
    ("antardasha_", ScoreScope.TIMING),
    ("transit_", ScoreScope.TIMING),
    ("d24_", ScoreScope.EDUCATION),
    ("interest_", ScoreScope.PREFERENCE),
    ("gender_", ScoreScope.DISALLOWED),
    ("risk_", ScoreScope.PRACTICAL),
)


PERMANENT_FORBIDDEN_SCOPES = frozenset({
    ScoreScope.TIMING,
    ScoreScope.EDUCATION,
    ScoreScope.PREFERENCE,
    ScoreScope.PRACTICAL,
    ScoreScope.DISALLOWED,
})


def scope_for(signal_id: str) -> ScoreScope:
    """Return a declared scope; undeclared signals fail closed."""
    if signal_id in SIGNAL_SCOPE:
        return SIGNAL_SCOPE[signal_id]
    for prefix, scope in _PREFIX_SCOPE:
        if signal_id.startswith(prefix):
            return scope
    raise KeyError(f"score signal has no declared scope: {signal_id}")


def assert_permanent_safe(signal_ids: Iterable[str]) -> None:
    unsafe = {
        signal_id: scope_for(signal_id).value
        for signal_id in signal_ids
        if scope_for(signal_id) in PERMANENT_FORBIDDEN_SCOPES
    }
    if unsafe:
        raise ValueError(f"non-permanent signals attempted to enter permanent score: {unsafe}")
