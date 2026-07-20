"""Uncertainty-aware tiers and boundary ties for shadow decisions."""
from __future__ import annotations

MARGIN_VERSION = "meaningful-margin.r8.v1"


def attach_meaningful_margin_tiers(rows: list[dict]) -> list[dict]:
    ordered = sorted(rows, key=lambda row: (-float((row.get("structural_vocational_fit") or {}).get("score", 0.0)), str(row.get("field_id"))))
    tier = 1
    previous_interval = None
    previous_score = None
    for position, row in enumerate(ordered, 1):
        structural = row.get("structural_vocational_fit") or {}
        score = float(structural.get("score", 0.0))
        interval = tuple((structural.get("sensitivity") or {}).get("score_interval", [score, score]))
        overlaps = previous_interval is not None and interval[1] >= previous_interval[0]
        if previous_interval is not None and not overlaps:
            tier += 1
        row["meaningful_margin"] = {
            "contract_version": MARGIN_VERSION,
            "authoritative": False,
            "shadow_position": position,
            "tier": f"TIER_{tier}",
            "score": round(score, 4),
            "margin_from_previous": None if previous_score is None else round(previous_score - score, 4),
            "uncertainty_interval": list(interval),
            "interval_overlaps_previous": bool(overlaps),
            "exact_ordering_claimed": not overlaps,
        }
        previous_interval = interval
        previous_score = score
    return rows

