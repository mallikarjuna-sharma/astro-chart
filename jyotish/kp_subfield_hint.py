"""KP cuspal sub-field narrowing — shared by both career engines.

GAP FIX (2026-08-17): framework Step 6 asks that the KP 10th-cusp star-lord
and sub-lord "narrow to specific sub-fields (e.g., not just 'medicine' but
'surgery' vs 'diagnostics')." Both engines previously stopped at a single
aggregate numeric KP score/flag per broad field — with ~200+ fields already
tracked in the affinity ontology (see jyotish/affinity.py), hand-building a
per-field sub-domain vocabulary (which specific specializations exist within
each of 200+ fields) is not a tractable single-pass addition.

What IS tractable, and directly implements the framework's own worked
example: within any broad field, WHICH cuspal-chain planet is dominant tells
you the *orientation* of the specialization, using the same Step-3
karakatwa mapping already established elsewhere in this codebase, applied
one layer down (at the specialization axis, not the broad-field axis).
E.g. for "medicine": a Mars-ruled cuspal chain skews interventional/surgical,
a Mercury-ruled chain skews diagnostic/analytical, a Jupiter-ruled chain
skews teaching/research, a Saturn-ruled chain skews public-health/systemic
administration -- which is exactly the surgery-vs-diagnostics distinction
the framework names as its example, derived generically rather than from a
hardcoded per-field lookup table.

This is intentionally advisory/narrative, not a new scoring signal: it adds
a `sub_field_hint` string to each engine's KP output without touching any
ranking math, so it carries zero regression risk to existing scores.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Step-3 karakatwa, restated as a specialization *orientation* rather than a
# broad-field assignment -- this is the one-layer-down reuse described above.
_ORIENTATION_HINTS: Dict[str, str] = {
    "Sun":     "administrative/leadership orientation (authority, oversight, governance roles within the field)",
    "Moon":    "public-facing/caregiving orientation (direct client or patient contact, nurturing/service roles)",
    "Mars":    "interventional/hands-on orientation (surgery, engineering execution, competitive or high-tempo roles)",
    "Mercury": "analytical/diagnostic orientation (diagnostics, writing, data, commerce, communication-heavy roles)",
    "Jupiter": "advisory/teaching orientation (research, education, strategic or judicial roles)",
    "Venus":   "aesthetic/relational orientation (design, arts, luxury, client-relationship-heavy roles)",
    "Saturn":  "structural/systemic orientation (long-cycle, administrative, infrastructure, or labor-intensive roles)",
    "Rahu":    "unconventional/disruptive orientation (foreign, emerging, non-traditional variants of the field)",
    "Ketu":    "research/technical-depth orientation (specialized, detail-heavy, or detached/back-office roles)",
}


def narrow_field_specialization(
    field_label: str,
    sub_lord: str = "",
    sub_sub_lord: str = "",
    star_lord: str = "",
) -> Dict[str, Any]:
    """Return a narrative sub-field hint for `field_label` derived from which
    planet(s) govern the KP 10th-cusp chain.

    Priority: sub_sub_lord (finest KP level available) > sub_lord > star_lord.
    When the finest available lord's orientation differs from the next lord
    up, both are surfaced (primary + secondary) — this is itself informative:
    agreement across levels means a clean, unambiguous specialization signal,
    while disagreement means the field may span two sub-domains.

    Returns {"sub_field_hint": str, "primary_lord": str, "secondary_lord": str, "trace": [str]}.
    Empty/neutral fields when no cuspal-chain data is available.
    """
    primary_lord = sub_sub_lord or sub_lord or star_lord or ""
    secondary_lord = sub_lord if (sub_sub_lord and sub_lord and sub_lord != sub_sub_lord) else ""

    if not primary_lord or primary_lord not in _ORIENTATION_HINTS:
        return {
            "sub_field_hint": "",
            "primary_lord": "",
            "secondary_lord": "",
            "trace": ["No usable KP cuspal-chain lord available for sub-field narrowing."],
        }

    primary_text = _ORIENTATION_HINTS[primary_lord]
    hint = f"{field_label}: {primary_text}" if field_label else primary_text
    trace = [f"KP cuspal chain lord {primary_lord} -> {primary_text}."]

    if secondary_lord and secondary_lord in _ORIENTATION_HINTS and secondary_lord != primary_lord:
        secondary_text = _ORIENTATION_HINTS[secondary_lord]
        hint += f" (secondary influence from {secondary_lord}: {secondary_text})"
        trace.append(f"Secondary cuspal-chain lord {secondary_lord} -> {secondary_text}.")

    return {
        "sub_field_hint": hint,
        "primary_lord": primary_lord,
        "secondary_lord": secondary_lord if secondary_lord in _ORIENTATION_HINTS else "",
        "trace": trace,
    }
