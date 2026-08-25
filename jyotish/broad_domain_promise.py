"""D1/D10 vocational promise separated from exact modern leaves.

WIRING STATUS (2026-08 gap-audit item 3.3, see
audit/FINAL_VS_V13_ASTROLOGICAL_COVERAGE_AUDIT.md coverage-matrix row
"Broad-domain promise" and P0 remediation item #2): compute_broad_domain_promise()
below IS called today, from jyotish/release_candidate.py::apply_release_4_7()
for every row, and its result (score/status/disagreement) is attached to
each field row and consumed downstream (see
Field_Determination/structural_vocational_fit.py's use of
row["broad_domain_promise"]["disagreement"]). That satisfies "attached per
field" but NOT the audit's actual P0 ask: apply_release_4_7() runs very late
in jyotish/engine.py (around the run_engine() call site near line 5297),
long after fields have already been scored and sorted by final_score
repeatedly earlier in the same module (see the many
`_all_pre_results.sort(key=lambda x: -x["final_score"])` / `results.sort(...)`
call sites between roughly lines 2256-2589). So today this module is an
informational/shadow diagnostic attached after the fact, not an independent
D1/D10 promise validation gate that runs BEFORE leaf-field ranking as the
audit specifies.

Moving this computation earlier so it can actually gate/reorder leaf fields
before ranking would require restructuring how every field's score is
produced (touching the scoring/ranking pipeline itself, not just adding an
additive post-hoc pass) -- assessed as out of scope for a minimal, low-risk
fix in this pass. Deferred; see the remediation writeup for the scoped
follow-up (move a D1/D10-only pre-check into the field-candidate generation
step in jyotish/engine.py, before the first final_score sort, and use its
status to gate/flag rather than reorder, to keep the change additive).
"""
from __future__ import annotations

def compute_broad_domain_promise(d1_score, d10_score, d24_score=None) -> dict:
    values=[float(d1_score),float(d10_score)]; weights=[.55,.45]
    if d24_score is not None: values.append(float(d24_score)); weights=[.40,.35,.25]
    if any(not 0<=v<=100 for v in values): raise ValueError("broad-domain inputs must be 0..100")
    mean=sum(v*w for v,w in zip(values,weights)); disagreement=max(values)-min(values)
    score=max(0.0,min(100.0,mean-.10*disagreement-.10*max(0.0,25-min(values))))
    status="STRONGLY_PROMISED" if score>=60 and min(values[:2])>=40 and disagreement<=25 else "PROMISED" if score>=45 and min(values[:2])>=30 else "CONDITIONAL" if score>=35 else "WEAK"
    return {"contract_version":"broad-domain-promise.v1","score":round(score,4),"status":status,"inputs":{"d1":values[0],"d10":values[1],"d24":values[2] if len(values)>2 else None},"disagreement":round(disagreement,4),"scope":"BROAD_DOMAIN_ONLY"}

