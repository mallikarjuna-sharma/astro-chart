"""JyotishAI jyotish package — re-exports all public symbols."""
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
from .prashna_engine import (
    PrashnaRequest,
    PrashnaResponse,
    run_prashna_query,
    prashna_from_payload,
    batch_prashna,
    generate_prashna_report,
    get_category_metadata,
    PRASHNA_CATEGORIES,
    PRASHNA_CATEGORY_ORDER,
)
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
