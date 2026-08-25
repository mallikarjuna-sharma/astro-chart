"""JyotishAI jyotish package — re-exports all public symbols."""
# Gap-audit fix (2026-08): __version__ here and ENGINE_VERSION in payload.py
# (stamped into run manifests/provenance) must be bumped together — they had
# drifted (11.2.0 vs v11.0-llm) before this fix. Keep both in sync.
__version__ = "11.2.0"   # 11.2: EduAlign (E-1/E-2/E-3/E-4), CareerPath (C-1/C-2/C-3), Prashna Panchang (P-1/P-2)
from .payload    import NatalPayloadV2, ENGINE_VERSION, logger
from .constants  import *
from .astro      import *
from .affinity   import BRANCH_PLANET_AFFINITY, compute_branch_affinity_score_llm
from .engine_io  import parse_json_payload, compute_aptitude_by_domain, _load_course_registry
# D-1: public alias (underscore-prefixed name kept for backward compat)
load_course_registry = _load_course_registry
from .boosts     import *
from .engine     import run_engine, execute_qa_verification_v8_9, classify_age_stage
from .output     import ExplainabilityEngine
from .llm import (
    call_llm_for_fields
)
# 2026-07-19: the Prashna subsystem (prashna.py, prashna_engine.py) was
# moved out of jyotish/ into the top-level Prashnam/ package, which itself
# imports jyotish.dignity / jyotish.constants / jyotish.ephemeris /
# jyotish.panchang / jyotish.llm_policy. Re-exporting Prashnam.prashna_engine
# HERE would make jyotish/__init__.py depend on Prashnam, while Prashnam
# depends on jyotish -- a circular import that breaks whichever module
# happens to be imported first (confirmed: `import Prashnam.prashnam_
# determination` before anything touches `jyotish` directly used to raise
# "cannot import name 'PrashnaRequest' from partially initialized module").
# Nothing else in the codebase imports Prashna symbols via `jyotish.*`
# (verified by search) -- every caller already goes through
# Prashnam.prashna_engine / Prashnam.prashna_integration directly -- so this
# re-export was pure convenience, not load-bearing. Dropped to break the
# cycle; import Prashna symbols from Prashnam.prashna_engine instead.
# ── New modules (v11.2) ─────────────────────────────────────────────
from .panchang import (
    compute_panchang,
    panchang_quality,
)
from .edu_align import (
    compute_d1_d24_stream_score,
    compute_sub_branch_compatibility,
    rank_sub_branches,
    compute_exam_day_scores,
    compute_academic_tier_recommendation,
)
from Job_Career.timeline import compute_d10_pivot_radar
from .foreign_opportunities import compute_global_mobility_pct
from .boosts import compute_d10_politics_risk
