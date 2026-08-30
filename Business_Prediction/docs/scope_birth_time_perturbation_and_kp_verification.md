# Scope: Birth-Time Perturbation/Abstention vs. Independent KP-Chain Verification

Two candidate next projects from the remediation sequence (items 2 and 5), scoped
side by side so effort and impact can be compared before committing to either.
Neither has been started; this is planning only.

---

## Option A: Birth-Time Perturbation & Abstention Logic

### What it would do
Recompute the full downstream decision (D10, D24, D60, bhava cusps, KP sub-lords,
Arudha positions, and everything scoring.py builds on top of them) at birth times
offset by ±1, ±2, ±5, ±10, and ±15 minutes from the reported time, then report
whether `business_advantage_label` / `authoritative_recommendation.action_level`
stays the same across that range. If the verdict flips within a narrow window,
the engine should say so explicitly and downgrade its own action_level (that's
the "abstention" half) rather than presenting a single confident number that
happens to sit right next to a cliff.

### Where it plugs in
- `birth_time_reliability` is currently a single scalar multiplier applied at
  `scoring.py` (the site just fixed this session, now floored at 0.6 for
  unreported reliability). Perturbation would replace/supplement this with an
  actual sensitivity measurement instead of a flat discount.
- The perturbation loop itself belongs upstream of `business_determination/` —
  in `jyotish/engine_io.py`, wherever the natal chart (D1) and each divisional
  chart get computed from `dob`/`tob`. That's the boundary this project has to
  cross: `Business_Prediction` consumes an already-built `payload`; it doesn't
  recompute charts from raw ephemeris itself.
- `compute_business_prediction()` in `engine.py` (line ~425) would need to run
  N times (once per offset) rather than once, then diff the outputs.

### Concrete steps
1. Establish whether `jyotish/engine_io.py` already exposes a "build payload
   from dob/tob/lat/lon" entry point that can be called repeatedly with a
   shifted `tob` — if yes, this is a wrapper; if the chart-building pipeline
   assumes a single global chart context, this becomes a larger refactor.
2. Write `_perturbed_verdicts(payload_builder, dob, tob, lat, lon, offsets)` 
   that returns `{offset_minutes: {"verdict": ..., "action_level": ..., 
   "business_promise": ..., "job_promise": ...}}`.
3. Define a stability rule: e.g. "abstain / downgrade to VALIDATE_BEFORE_COMMITTING
   if action_level changes anywhere within ±5 minutes; flag but don't downgrade
   for changes only visible at ±10/±15."
4. Surface a new `birth_time_sensitivity` block in the debug JSON: per-offset
   verdicts, the stability rule's verdict, and which specific layers moved
   (D10 house flip, KP sub-lord change, etc.) — not just a pass/fail.
5. Gate this behind `birth_time_reliability` status: skip perturbation entirely
   (and say so) when reliability is already HIGH/EXACT, since the whole point
   is bounding uncertainty that's already known to be small.
6. Test with fixtures that are deliberately built near a cusp boundary (a
   planet within ~1° of a house/sign edge) to confirm the mechanism actually
   catches instability, plus a stable-chart fixture to confirm it doesn't
   cry wolf.

### Cost/risk
- **Compute cost**: 11 offsets × full chart computation × full
  `compute_business_prediction()` — probably the most expensive single feature
  in the engine. Needs profiling; may need to cache/short-circuit divisional
  charts that don't change materially at 1-minute resolution.
- **Scope risk**: if `engine_io.py`'s chart-building isn't cleanly re-callable
  per offset (e.g. it does file I/O, caches globally, or assumes a single
  chart per process), this could turn into a larger refactor of a module this
  session hasn't touched. That needs to be checked BEFORE estimating this as
  a quick project.
- **High leverage**: this is the most-cited fragility in the audit (item 3),
  and it's the one gap that quietly undermines everything else — a D10 house
  flip half a degree away from the reported time can silently change the
  entire recommendation with no signal to the reader that it happened.

---

## Option B: Independent KP-Chain Verification

### What it would do
Right now `kp.py` trusts `payload.kp_significators` / `payload.kp_cusps`
wholesale — every KP-based judgment (10th-cusp job-vs-business, 7th-cusp
result/loss, event-type bucketing) reads `occupant → star_lord → sub_lord →
sign_lord` fields that arrive pre-computed from upstream
(`jyotish/engine_io.py::_build_kp_significators`, `pyh.get("kp_cusp_data")`,
`pyh.get("kp_planetary_significators")`), with no independent check that those
chains are internally consistent (e.g. that the sub-lord's own sub-lord degree
range actually contains the cusp longitude, or that no cusp is silently
missing a level).

This project would add a verification pass that reconstructs each cusp's
occupant/star-lord/sub-lord chain from the underlying planetary longitudes
and KP sub-lord degree tables, and flags disagreement with what upstream
handed over — rather than doing new astronomical computation from scratch.

### Where it plugs in
- `kp.py::_kp_10th_cusp_job_vs_business()` (line ~154) already exposes the raw
  `kp_chain` dict (occupant/star_lord/sub_lord/sign_lord) for inspection — that
  was a prior session's transparency fix (v34). This project would add the
  actual cross-check against that exposed chain, not just display it.
- Needs: cusp longitudes (should already be on payload, since cusps had to be
  computed to assign KP cusps at all), the KP sub-lord degree-span table (the
  Vimshottari-proportional 249-segment division of the zodiac), and each
  planet's longitude — to independently derive sub_lord from raw degrees and
  compare against what upstream supplied.
- `_kp_significator_weighted_houses()` (line ~128) would gain a companion
  `_verify_kp_chain(cusp_longitude, claimed_chain)` used before, not instead
  of, the existing weighting logic.

### Concrete steps
1. Confirm whether `jyotish/` already has a KP sub-lord degree-table
   implementation anywhere (it may — check `jyotish/` for anything named
   `sub_lord`, `kp_table`, `vimshottari_span`) before building one from
   scratch; this determines whether step 2 is "reuse" or "author."
2. Write `_derive_kp_chain_from_longitude(cusp_or_planet_longitude) ->
   {occupant, star_lord, sub_lord, sign_lord}` purely from degrees + the
   249-segment table — no payload trust involved.
3. Write `_reconcile_kp_chains(claimed, derived) -> {"agrees": bool,
   "disagreements": [...]}"` and call it for every cusp/planet KP.py reads.
4. Decide the failure mode: does a disagreement (a) block KP evidence
   entirely for that cusp, (b) downgrade KP's confidence weight in the
   `kp` scoring layer, or (c) just surface a diagnostic without changing the
   score? Given this project's own principle (independent verification, not
   silent trust), (a) or (b) is more consistent than (c) alone.
5. Add a `kp_chain_verification_status` field per cusp to the debug JSON:
   `VERIFIED_MATCH` / `DISAGREEMENT` / `UNVERIFIABLE_MISSING_LONGITUDE`.
6. Test against fixtures with a deliberately corrupted `kp_significators`
   entry (mismatched sub-lord) to confirm the reconciliation actually catches
   it, plus the existing clean fixtures to confirm no false positives.

### Cost/risk
- **Self-contained**: doesn't require touching the chart-building boundary in
  `jyotish/engine_io.py` the way Option A does — this stays entirely within
  data already computed and already flowing to `Business_Prediction`, plus
  one static reference table (KP sub-lord degree spans) that's fixed
  regardless of chart.
- **Main unknown**: whether the KP sub-lord degree table already exists
  somewhere in `jyotish/` (cheap) or needs to be authored and validated
  against a known reference chart (more work, and it's exactly the kind of
  "doctrinal implementation, not a bug fix" work flagged as out of scope for
  quick fixes in the prior round).
- **Narrower leverage than Option A**: this only strengthens KP specifically
  — one of nine business-promise layers and one of seven job-promise layers.
  It closes a real trust gap (item 5) but doesn't touch D10/D24/D60/Jaimini,
  which have their own, larger unaddressed gaps (items 7–10 in the audit).

---

## Comparison

| | Option A: Birth-time perturbation | Option B: KP-chain verification |
|---|---|---|
| Audit item | #3 (most-cited fragility) | #5 |
| Touches chart-building boundary (`jyotish/engine_io.py`) | Yes — main open risk | No |
| New reference data needed | No | Possibly (KP sub-lord degree table) |
| Compute cost | High (11x full chart+decision recompute) | Low (one extra pass per cusp) |
| Breadth of impact | All layers, all divisional charts | KP layer only |
| Biggest unknown before estimating | Is chart-building cleanly re-callable per offset? | Does the degree table already exist in `jyotish/`? |

Recommendation if forced to pick one: Option A addresses the single largest
fragility named in the audit and affects every layer, but its cost is
genuinely unknown until the `engine_io.py` re-callability question is
answered — that should be the very first investigation, before committing
to a full build estimate. Option B is smaller, self-contained, and safer to
scope precisely right now, but it closes a narrower gap.
