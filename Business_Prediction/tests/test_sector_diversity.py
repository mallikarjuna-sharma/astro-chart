"""Tests for diversify_sector_ranking() and the archetype_family schema
validation added alongside it (business_determination/sectors.py and
business_determination/constants.py).

Uses synthetic, already-scored sector rows (duck-typed like sector_score()
output) rather than a full chart fixture, since diversify_sector_ranking()
is a pure post-processing step over an already-ranked list -- it does not
itself need a NatalPayloadV2.
"""
import copy
import json
import sys
import pathlib

import pytest

_repo = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_engine import (
    diversify_sector_ranking,
    validate_business_rule_pack,
    _load_business_registry,
    _REGISTRY_PATH,
)


def _row(sector, score, family, rank):
    return {
        "sector": sector,
        "label": sector.replace("_", " ").title(),
        "score": score,
        "archetype_family": family,
        "rank": rank,
    }


def _synthetic_ranked():
    """3 sectors share `family_a` (a near-duplicate cluster), 2 sectors
    each sit in their own distinct family -- mirrors the real-world
    Jupiter-Mercury cluster diagnosis (consulting/finance/education) vs.
    genuinely distinct sectors."""
    rows = [
        _row("alpha_one", 90.0, "family_a", 1),
        _row("beta_solo", 85.0, "family_b", 2),
        _row("alpha_two", 80.0, "family_a", 3),
        _row("gamma_solo", 75.0, "family_c", 4),
        _row("alpha_three", 70.0, "family_a", 5),
    ]
    return rows


def test_diversified_top_sectors_surfaces_distinct_families_before_same_family_dupes():
    ranked = _synthetic_ranked()
    result = diversify_sector_ranking(ranked, max_per_family=1, top_n=3)
    top_ids = [r["sector"] for r in result["diversified_top_sectors"]]
    # Round 0 must give one pick per family in score order: alpha_one
    # (family_a's best), beta_solo (family_b), gamma_solo (family_c) --
    # NOT alpha_two/alpha_three, which are lower-scoring same-family
    # duplicates of alpha_one.
    assert top_ids == ["alpha_one", "beta_solo", "gamma_solo"]
    assert "alpha_two" not in top_ids
    assert "alpha_three" not in top_ids


def test_diversified_top_sectors_fills_second_round_only_after_every_family_covered():
    ranked = _synthetic_ranked()
    result = diversify_sector_ranking(ranked, max_per_family=1, top_n=5)
    top_ids = [r["sector"] for r in result["diversified_top_sectors"]]
    # top_n=5 with only 3 distinct families -> round 0 uses 3 slots, round
    # 1 fills the remaining 2 slots with the next-best per family (only
    # family_a has more members here).
    assert top_ids[:3] == ["alpha_one", "beta_solo", "gamma_solo"]
    assert "alpha_two" in top_ids
    assert len(top_ids) == 5


def test_family_groups_nests_same_family_sectors_with_accurate_count():
    ranked = _synthetic_ranked()
    result = diversify_sector_ranking(ranked, max_per_family=1, top_n=3)
    groups = {g["archetype_family"]: g for g in result["family_groups"]}

    assert groups["family_a"]["member_count"] == 3
    assert groups["family_a"]["member_sectors"] == ["alpha_one", "alpha_two", "alpha_three"]
    assert groups["family_a"]["surfaced_count"] == 1
    assert groups["family_a"]["hidden_count"] == 2
    assert "2" in groups["family_a"]["note"] or "similar" in groups["family_a"]["note"]

    assert groups["family_b"]["member_count"] == 1
    assert groups["family_b"]["hidden_count"] == 0
    assert groups["family_c"]["member_count"] == 1
    assert groups["family_c"]["hidden_count"] == 0


def test_graceful_fallback_when_archetype_family_missing_legacy_entry():
    ranked = _synthetic_ranked()
    # Simulate a legacy registry row that pre-dates archetype_family.
    legacy_row = _row("legacy_sector", 60.0, None, 6)
    del legacy_row["archetype_family"]
    ranked_with_legacy = ranked + [legacy_row]

    result = diversify_sector_ranking(ranked_with_legacy, max_per_family=1, top_n=10)

    assert result["status"] == "OK"
    assert "legacy_sector" in result["legacy_singleton_sectors"]
    legacy_groups = [g for g in result["family_groups"] if g["is_legacy_singleton"]]
    assert len(legacy_groups) == 1
    assert legacy_groups[0]["member_sectors"] == ["legacy_sector"]
    # Legacy row must still be selectable in diversified_top_sectors (its
    # own singleton family), never dropped or crashing.
    top_ids = [r["sector"] for r in result["diversified_top_sectors"]]
    assert "legacy_sector" in top_ids


def test_diversify_sector_ranking_never_raises_on_empty_input():
    result = diversify_sector_ranking([], max_per_family=1, top_n=8)
    assert result["diversified_top_sectors"] == []
    assert result["family_groups"] == []
    assert result["status"] == "EMPTY_INPUT"


def test_real_registry_validates_with_archetype_family_field():
    """Sanity check against the real, already-patched registry: every
    sector must declare a valid archetype_family and validation must
    pass."""
    report = validate_business_rule_pack()
    assert report["ok"], report["errors"]
    registry = _load_business_registry()
    for sector_id, meta in registry["sectors"].items():
        assert meta.get("archetype_family"), f"{sector_id} missing archetype_family"


def test_validate_business_rule_pack_catches_missing_archetype_family(tmp_path, monkeypatch):
    """A malformed future registry (missing archetype_family on one
    sector, and an unknown family value on another) must fail loudly."""
    real_registry = json.loads(pathlib.Path(_REGISTRY_PATH).read_text(encoding="utf-8"))
    broken = copy.deepcopy(real_registry)
    sector_ids = list(broken["sectors"].keys())

    # Case 1: missing entirely.
    del broken["sectors"][sector_ids[0]]["archetype_family"]
    # Case 2: unknown/typo'd family value.
    broken["sectors"][sector_ids[1]]["archetype_family"] = "totally_made_up_family"

    fixture_path = tmp_path / "broken_registry.json"
    fixture_path.write_text(json.dumps(broken), encoding="utf-8")

    import Business_Prediction.business_determination.constants as constants_mod

    monkeypatch.setattr(constants_mod, "_REGISTRY_PATH", str(fixture_path))
    monkeypatch.setattr(constants_mod, "_registry_cache", None)

    report = constants_mod.validate_business_rule_pack()

    assert report["ok"] is False
    joined = " | ".join(report["errors"])
    assert "archetype_family" in joined
    assert sector_ids[0] in joined
    assert sector_ids[1] in joined

    # Reset cache so later tests reload the real registry.
    monkeypatch.setattr(constants_mod, "_registry_cache", None)
