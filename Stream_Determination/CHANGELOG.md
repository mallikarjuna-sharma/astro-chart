# CHANGELOG — 2026-08-22 audit fixes

Fixes made against the two-pass BPHS audit. All are additive/documented in-place edits;
no public function/class was renamed, and every existing signature stays call-compatible
(new parameters are keyword-only with defaults that preserve prior behavior).

1. **subject_registry.py — H10 added to Science/Humanities.** Added house 10 to both
   streams' `houses`/`house_weights` at 0.28 (below Commerce's own 0.40), following the
   existing "universal house, capped low" damping pattern already used for H10/H11
   elsewhere in the file.

2. **subject_registry.py — H2 added to Science/Humanities.** Added house 2 to both
   streams at weight 0.18 (BPHS Ch 12 vidya-sthana-adjacent: speech/early learning/family
   knowledge), separate from and additional to Commerce's existing wealth-only H2 role.

3. **subject_registry.py + stream_scoring.py — naisargika karaka dignity bonus.** Added
   `_naisargika_karaka_strength_bonus(planet, chart_data)` in stream_scoring.py, reusing
   existing dignity data (`true_planet_dignities`, `combust_planets`,
   `_KENDRA_HOUSES`/`_TRIKONA_HOUSES`, `_get_planetary_aspects`) rather than
   reimplementing dignity logic. Wired as a bounded ±15%-of-contribution multiplier into
   `score_stream`'s `weighted_strength` computation, applied only to Mercury for
   Science/Commerce and Jupiter/Venus for Humanities — the streams where each is
   classically karaka-relevant. Documented as a supplementary refinement, not an
   independent evidence channel.

4. **subject_registry.py — Mars/Saturn domain comments + Rahu/Ketu added to Science.**
   Added explanatory comments citing Mars (engineering/surgery, Phaladeepika Ch 12) and
   Saturn (mining/labor/technical-service) without changing their numeric weights. Added
   Rahu (0.12) and Ketu (0.08) to Science's planet-weight dict, both commented as
   commonly-used-but-non-BPHS-original supplementary signals.

5. **stream_scoring.py — `_mandatory_ceiling_multiplier` made dignity-aware.** Added
   optional keyword-only `planet`/`chart_data` params (default `None`, so the old
   scalar-only call pattern still works unchanged). When supplied, checks
   combust/debilitated state and lowers the floor from 0.55 toward a new
   `_MANDATORY_FLOOR_MULT_AFFLICTED = 0.40`, scaled by affliction severity. `score_subjects`
   gained an optional `chart_data=` kwarg (default `None`) threaded through from
   `compute_stream_determination`'s existing `payload`.

6. **stream_scoring.py — arbitration-mechanism conflict guard.** Added an explicit check
   in `compute_stream_determination`: if both `d24_arbitration_enabled` and
   `classical_precedence_chain_enabled` are `True`, the deprecated D24/JAIMINI policy is
   forced off (chosen over a hard `ValueError` since the surrounding code already
   documents the chain as "declared default" and the old policy as "deprecated" — forcing
   is the less disruptive, still-unambiguous resolution). A new report field
   `dual_arbitration_mechanism_conflict_note` states plainly, when this happens, that the
   precedence chain was the sole mechanism that actually ran.

7. **stream_scoring.py — cross-section correlation discount raised.** `_CROSS_SECTION_MAX_DISCOUNT`
   raised from 0.20 to 0.65, so full overlap (Jaccard=1.0 across
   role_placement/d24_confirmation/relational_d1/jaimini_apparatus) now discounts to 35%
   of raw value instead of 80%. The existing smooth Jaccard-interpolated curve is
   unchanged — only the ceiling moved.

8. **stream_narrative.py — validator checks claim attribution, not just mention.** Added a
   conservative regex pass in `_validate()` that extracts `(planet, stream)` claims of the
   shape "`<Planet> ... supports/favors/... <Stream>`" from the astrological narrative and
   rejects the narrative if that planet does not actually appear in that specific stream's
   own evidence-packet section notes (i.e. scoring never attributed it there) — same
   string-matching approach as the existing unsupported-entity checks, not a full NLU pass.

9. **field_stream_mapping.py / cross_validate.py — provenance disclosure.** Added explicit
   module-level comments stating `FIELD_STREAM_AFFINITY`/`DOMAIN_STREAM_AFFINITY`/
   `DOMAIN_TO_STREAM` are this codebase's own engineered heuristic estimates, not derived
   from classical Jyotish texts or an official CBSE table. No numeric changes.

10. **early_age_stream_engine.py / adult_engine_bridge.py — age-boundary discontinuity.**
    Reviewed both files: the under-15/adult engine choice is a hard cutoff owned by
    `Field_Determination/education_engine.py`'s `__main__` block, which is **outside this
    directory** and was not part of this fix's scope. `adult_engine_bridge.py` only fetches
    supplementary adult-engine evidence for an already-under-15 chart (never an alternative
    full determination for a boundary chart), so there is no natural point in these two
    files to blend two determinations, and reimplementing/duplicating the external router
    to add blending was judged out of scope for a bounded, minimal-risk fix. Documented the
    discontinuity as a known, accepted limitation with clear comments in both files instead
    of implementing a blend.

## Scoped down / deliberately not done

- **Item 10** — blending was not implemented (see above); documented as a known limitation
  instead, since the actual dispatch logic lives in a file outside `Stream_Determination/`.
- **Item 8** — the misattribution check is regex/string-matching only (consistent with the
  existing validator's approach), not a semantic/NLU check; it will not catch phrasing that
  avoids the "planet ... verb ... stream" pattern it looks for.
- **Item 3** — the naisargika karaka bonus deliberately does not add Sun/Moon/Mars/Saturn/
  Rahu/Ketu as bonus-eligible planets; per the audit's own framing (Mercury/Jupiter/Venus)
  and the codebase's convention that naisargika karakas for vidya/wisdom/arts are these
  three, it is scoped exactly to them.

## Verification

`python3 -m py_compile` passes clean on every `.py` file in this directory after all edits.

# CHANGELOG — 2026-08-22 second audit pass fixes

Fixes made against a fresh audit pass on code from the first round above.

1. **stream_scoring.py — naisargika karaka bonus now discounted by `_planet_exclusivity`.**
   `_naisargika_karaka_strength_bonus`'s bonus was previously applied at full strength to
   every karaka-relevant stream a planet touches (e.g. Mercury to both Science and
   Commerce), which is exactly the "non-discriminating shared signal" problem
   `_planet_exclusivity` already exists to solve elsewhere in the file. The call site in
   `score_stream` now multiplies the bonus by `_planet_exclusivity(p)` before it is applied
   to `weighted_strength`, so a planet shared across streams' karaka lists no longer nudges
   all of them identically. `_planet_exclusivity` itself is unchanged.

2. **stream_scoring.py — naisargika karaka bonus debilitation check now eff_strengths-aware.**
   `_naisargika_karaka_strength_bonus` previously applied a full debilitation penalty from
   raw `true_planet_dignities` alone, bypassing the chart engine's Neecha-Bhanga-aware
   `eff_strengths`. Added an optional `eff_strengths` parameter (default `None`, with a
   documented fallback to raw-dignity behavior when not supplied); the function now treats
   a planet as effectively debilitated only when both the raw dignity says DEBILITATED and
   its resolved `eff_strengths` value is still at/under the engine's minimum-viable baseline
   (1.0), so a classically-cancelled debilitation no longer takes the penalty twice. The
   call site in `score_stream` was updated to pass `payload.eff_strengths` explicitly.

3. **stream_narrative.py — misattribution regex.** `r"indicat[es|ing]*"` and
   `r"driv[es|ing]*"` were bracket character classes (matching any of the characters
   e/s/|/i/n/g repeated, not the words "indicates"/"indicating"/"driving" etc.), which made
   the "conservative" misattribution check accidentally permissive. Replaced with proper
   alternation: `r"indicat(?:es|ing|e)?"` and `r"driv(?:es|ing|e)?"`.

4. **field_derived_stream.py — reliability-constant disclosure.** Added a comment next to
   `field_count_factor`/`family_breadth_factor`/the blend weights cross-referencing
   stream_scoring.py's engineered-constant disclosure (~L2226-2239), so a reader of this
   file alone understands these are tuned, unvalidated constants, not classically or
   statistically derived values.

5. **calibration.py — `MIN_CASES_PER_STREAM`/`MIN_TOTAL_CASES` disclosure.** Added a
   matching comment noting these are round-number engineered minimums, not derived from a
   formal power analysis, for consistency with the rest of the codebase's disclosure
   discipline.

6. **stream_report.py — Rahu/Ketu contemporary-practice caveat surfaced in reports.** The
   "not BPHS-original, contemporary practitioner usage" caveat previously existed only as a
   source comment in `subject_registry.py`. Added `_rahu_ketu_caveat()` and wired it into
   each stream's entry in `build_report_payload`'s `"streams"` list as
   `"rahu_ketu_caveat"`: `None` normally, or a short disclosure string whenever Rahu/Ketu is
   one of that stream's weighted signature planets AND has an above-baseline (`>1.0`)
   `eff_strength` for the chart being scored (i.e. meaningfully contributed).

## Scoped down / deliberately not done (this pass)

- **Item 6** — the caveat was added to the JSON report payload (`streams[].rahu_ketu_caveat`)
  rather than also being threaded into `render_report_html`'s per-stream HTML markup or
  `stream_narrative.py`'s generated prose; the task explicitly called for a minimal
  conditional-string addition without new infrastructure, and the JSON field is consumed by
  both the HTML renderer and any other report consumer if/when they choose to render it.

## Verification (this pass)

`python3 -m py_compile` passes clean on every `.py` file in this directory after all edits
in this pass.

# CHANGELOG — 2026-08-22 audit fixes, round 3

Third-round audit fixes. All are in-place, backward-compatible edits — no signature or
call-site was broken.

1. **stream_scoring.py — naisargika bonus/exclusivity split (~L2258).** The
   `_planet_exclusivity` discount was previously applied to the *full signed* return value
   of `_naisargika_karaka_strength_bonus`, including its negative (combust/uncancelled-
   debilitated affliction) branch. That diluted a real affliction penalty as if it were
   shared, discriminating evidence to be split across streams, when in fact an affliction
   on the planet itself is bad evidence for every karaka-relevant stream independently.
   Refactored into a local `_karaka_bonus_multiplier(p)` helper: the bonus is computed once,
   then only the positive branch is scaled by `_planet_exclusivity`; the negative branch
   passes through at full, undiscounted value.

2. **stream_scoring.py — `_mandatory_ceiling_multiplier` Neecha Bhanga awareness
   (~L2600-2645).** This function checked `true_dignities.get(planet) == "DEBILITATED"`
   directly, unaware of Neecha Bhanga (debilitation-cancellation), unlike its sibling
   `_naisargika_karaka_strength_bonus` (fixed in round 2). Applied the same conjunctive
   pattern: debilitation only counts toward the affliction-floor drop if `eff_strengths`
   (read off the already-threaded `chart_data`, same payload object) is *also* `<= 1.0`.
   Falls back to the raw dignity check when `eff_strengths` is unavailable, matching the
   sibling function's fallback behavior. No new parameters were needed — `chart_data` was
   already threaded through from `score_subjects` in the round-1 fix, so `eff_strengths` is
   read from it the same way the naisargika bonus function does.

3. **stream_scoring.py — `SCORING_CONTRACT_VERSION` bump (~L267-278).** Bumped
   `"stream-scoring-contract.2026-07-24-v8"` → `"stream-scoring-contract.2026-08-22-v9"`
   with an explanatory comment, per the module's own stated versioning policy (rubric-shape
   changes bump the contract version even without a corresponding field-name change). Covers
   fixes #1 and #2 above plus the prior round's cross-section discount ceiling change.

4. **calibration.py — version-drift awareness in `calibration_state()`.** Added a
   prominent docstring/comment explaining that a calibration validated against an older
   `SCORING_CONTRACT_VERSION` is not valid for the current contract and must be re-run.
   Also added a small, backward-compatible runtime guard: if the config dict carries an
   optional `scoring_contract_version` key and it no longer matches
   `stream_scoring.SCORING_CONTRACT_VERSION`, `calibration_state()` downgrades
   `status` from `VALIDATED_CALIBRATED` back to `ENGINEERED_PROVISIONAL` and reports
   `contract_version_mismatch: True` in the returned dict. The import of `stream_scoring`
   is local/lazy and wrapped in `try/except` so this module never hard-fails or risks an
   import cycle; existing callers that omit `scoring_contract_version` see no behavior
   change.

## Scoped down / deliberately not done (round 3)

- **Item 4** — no existing on-disk calibration config in this repo carries a
  `scoring_contract_version` field yet, so the new runtime guard is inert until a producer
  of calibration config starts stamping that key. Wiring that stamping into whatever
  produces/persists calibration config (outside the scope of the files audited this round)
  was not done; the comment/docstring warning stands as the authoritative guidance in the
  meantime.

## Verification (round 3)

`python3 -m py_compile` passes clean on every `.py` file in this directory after all round-3
edits.

# CHANGELOG — 2026-08-22 round 4: classical yoga-pattern detection (NEW FUNCTIONALITY)

Round 4 is **new functionality**, not a bug fix — classical yoga-pattern detection has been
flagged as absent across all three prior audit rounds. Added a new module and wired it into
scoring/report/narrative, following the same disclosure/bounding conventions established in
rounds 1-3 (see `_naisargika_karaka_strength_bonus` and `rahu_ketu_caveat` as the two closest
precedents).

1. **New module `yoga_detection.py`.** Implements five classical yoga detectors, each
   returning a structured `{yoga_name, present, strength (0-1), contributing_planets,
   classical_citation, precision ("precise"|"coarse"), notes}` dict, computed entirely from
   real `chart_data` fields already used elsewhere in this package (`planet_house`,
   `house_lords`, `planets_d1`, `true_planet_dignities`, `combust_planets`, `eff_strengths`) —
   no stubbed/random/hardcoded results. Reuses `jyotish.astro._get_planetary_aspects` (same
   whole-sign Parashari aspect convention `_naisargika_karaka_strength_bonus` already uses)
   and `jyotish.constants._SIGN_LORD`, rather than re-deriving aspect/sign-lordship logic.

   - **Budha-Aditya Yoga** (BPHS Ch. 36 / Phaladeepika Ch. 6): Mercury-Sun conjunction. When
     both planets' degrees are available in `planets_d1`, strength scales with orb tightness
     (`precision="precise"`); otherwise falls back to a flat 0.7 (`precision="coarse"`). A
     tight conjunction (orb < 14°) is NOTED as classically implying Mercury combustion, but
     that penalty is explicitly NOT re-applied here — it is already scored by
     `_naisargika_karaka_strength_bonus` in `stream_scoring.py`, and double-penalizing it was
     the exact failure mode rounds 2-3 fixed for that function's own bonus/exclusivity split.
   - **Saraswati Yoga** (compiled Phaladeepika/Saravali-adjacent formulation, explicitly
     disclosed as a compiled popular formulation, not a single-verse citation — same
     disclosure convention as subject_registry.py's (A)/(B) provenance note): Jupiter in
     own/exaltation/friendly sign, associated (conjunct or mutually aspecting) with both
     Mercury and Venus, with at least one of the three in kendra/trikona from lagna.
     `precision="coarse"` always — association is checked at whole-sign resolution, not
     degree orb.
   - **Dharma-Karmadhipati Yoga** (BPHS Ch. 39): 9th lord and 10th lord in conjunction,
     mutual aspect, or parivartana (sign exchange). Mapped to all three streams at different
     relevance weights (Humanities 1.0, Commerce 0.8, Science 0.4), following STREAM_META's
     own house-weight pattern (9th weighted 1.00 for Humanities, present at lower weight for
     Science/Commerce too).
   - **Gaja-Kesari Yoga** (BPHS Ch. 36): Moon and Jupiter in mutual kendra (house distance in
     {0,3,6,9} from each other). `precision="precise"` — unlike the two yogas above, this
     yoga's classical criterion IS purely house-distance-based, so there is no finer-grained
     version this is a coarse stand-in for. Strength is reduced (not zeroed) when either
     planet is combust or uncancelled-debilitated, since the positional yoga still classically
     holds but its practical expression is weakened.
   - **Dhana Yoga** (BPHS Ch. 39, commerce-relevant): 2nd lord and 11th lord in conjunction,
     mutual aspect, or parivartana. Mapped only to Commerce.

   All five detectors share a `_lord_yoga()` helper (Dharma-Karmadhipati and Dhana Yoga are
   structurally the same classical pattern applied to different house pairs) and a shared
   `detect_all_yogas()` entry point that never raises — an individual detector's failure on an
   unexpected `chart_data` shape degrades to `present=False` for that yoga only, matching this
   codebase's existing "missing data degrades gracefully, never fabricates" convention.

2. **`stream_scoring.py` integration.** Added `_yoga_pattern_bonus()`, called from
   `score_stream()` right after `total_raw` (the pre-compression, capped-section sum) is
   computed. Each present, stream-relevant yoga contributes
   `strength * stream_relevance * planet_exclusivity_avg * cross_section_factor`, capped per
   yoga at ±5% (`_YOGA_PER_YOGA_CAP_FRACTION`) and capped in total at ±10%
   (`_YOGA_BONUS_CAP_FRACTION`) of the stream's pre-yoga `total_raw`. Chosen at 10% (not the
   full 12% ceiling the task allowed) to stay clearly subordinate to the fully-classical
   rubric sections it sits alongside, while still being large enough to matter on a chart that
   actually carries one of these patterns.

   Routed through the **same** double-counting guards already built for this purpose, rather
   than reintroducing the problem they exist to prevent:
   - `_planet_exclusivity` — a yoga's contributing planets that are also on the stream's own
     signature-planet list are discounted by how many streams' lists they're shared across
     (same reasoning `_naisargika_karaka_strength_bonus`'s bonus already uses); planets not on
     the stream's signature list (e.g. a house-lord planet the yoga uses that isn't itself a
     stream signature planet) are treated as fully exclusive to this detection.
   - `_cross_section_factor` — the same overlap-based discount already computed for
     role_placement/d24_confirmation/relational_d1/jaimini_apparatus is reused directly (not
     recomputed) for the yoga bonus too, since these yogas draw on the same small set of
     house-lord/karaka planets those four sections do (9th/10th lords, 2nd/11th lords,
     Moon/Jupiter/Mercury/Venus/Sun).

   Bumped `SCORING_CONTRACT_VERSION` from `...v9` to `...v10` per this module's own stated
   versioning policy (rubric-shape change) — v9 and v10 reports are not guaranteed to agree on
   scores for any chart carrying one of these five yoga patterns.

   Added `result["yoga_detection"]` to `score_stream`'s return dict (bonus fraction applied,
   pre-yoga total_raw, and full detail for every yoga that was `present`, including yogas not
   relevant to this particular stream, flagged via `relevant_to_this_stream`) — same pattern
   as the other `*_data_status`/`*_signal_state` report fields already on that dict.

3. **`stream_report.py` wiring.** Added `"yoga_detection": s.get("yoga_detection", {})` to
   each stream's entry in `build_report_payload`'s `"streams"` list, mirroring exactly how
   `"rahu_ketu_caveat"` was wired in round 2 (item 6 above) — a straight pass-through of a
   field `score_stream` already computes, no new report infrastructure.

4. **`stream_narrative.py` wiring (conservative, additive-only).** Added a
   `"yogas_present"` list (yoga names only, no scores/strengths, matching this function's
   existing "minimized, calculated-only" evidence-packet convention) to each stream's entry in
   `build_stream_narrative_evidence()`. Because rubric sections' own `note` text already flows
   into this evidence packet's `sections` list unchanged, the LLM-facing prompt path required
   no further change to become yoga-aware. For the deterministic `_fallback_narrative()` path,
   added one *optional* trailing sentence to the `astrological_narrative` paragraphs, appended
   only when `yogas_present` is non-empty for the top (or first tied) stream — a chart with no
   detected yoga produces byte-identical fallback narrative output to before this change.

## Weight caps chosen and why

- **±10% total cap, ±5% per-yoga cap**: kept well inside the ±10-12% band the task specified,
  and deliberately smaller than the caps already established for other supplementary/bounded
  sections in this file (`_NAISARGIKA_KARAKA_BONUS_CAP` = 15%) — yoga presence is a coarser,
  more compiled signal than naisargika-karaka dignity (which draws on directly-verified
  BPHS dignity data), so it earns a correspondingly smaller ceiling.
- Multiplicative on `total_raw` (not an additive fixed-point rubric section) — matches how
  `_naisargika_karaka_strength_bonus` itself is applied (a bounded nudge on existing evidence,
  never an independent evidence channel), and keeps the yoga bonus proportionate across charts
  with very different raw score magnitudes instead of adding the same flat points to every chart.

## Scoped down / deliberately not done (round 4)

- **Saraswati Yoga's "friendly sign" check** uses only Naisargika Maitri (natural
  friendship, mirrored from `jyotish/astro.py`'s own `_detect_planetary_war._NATURAL_FRIENDS`
  table) rather than the full five-fold Panchadha Maitri (natural + temporal relationship,
  which changes at birth based on relative house positions). This module does not have an
  independent path to the temporal-friendship computation, so `_is_own_exalt_or_friendly_sign`
  is documented explicitly as a coarse, natural-friendship-only approximation.
- **Budha-Aditya Yoga's degree-level precision** depends entirely on whether the calling
  chart's `payload.planets_d1` carries a numeric `degree` for both Mercury and Sun. When it
  does, this yoga is genuinely `precision="precise"`; when it does not (older/incomplete
  chart data), it degrades to a flat, documented `precision="coarse"` strength of 0.7 rather
  than fabricating a tightness figure — this is a data-availability limitation of the upstream
  chart parser, not something this module can work around.
- **Dharma-Karmadhipati / Dhana Yoga's parivartana check** only tests the two lords' sign
  placements against `jyotish.constants._SIGN_LORD` — it does not additionally verify that
  the exchange is not simultaneously nullified by some other classical caveat (e.g. one lord
  being severely combust); an afflicted lord still counts toward yoga presence here, the same
  way `_naisargika_karaka_strength_bonus`'s own placement-bonus branch does not itself gate on
  affliction (affliction is a separate, already-scored penalty elsewhere in this file).
- **No HTML-report rendering change.** Per round 2's own precedent for `rahu_ketu_caveat`
  (item 6 there, "Scoped down" note), the new `yoga_detection` field was added to the JSON
  report payload only, not threaded into `render_report_html`'s per-stream markup — the JSON
  field is available to that renderer (or any other report consumer) to pick up later.
- **LLM-facing `_prompt()` text** was not changed to explicitly instruct the model to mention
  yogas — `yogas_present` reaches the LLM path only via the already-existing
  `sections[].note` text (which now includes the yoga trace line from `stream_scoring.py`
  when relevant), keeping this pass's prompt-schema risk at zero, consistent with how round 2
  scoped `rahu_ketu_caveat` to JSON-only rather than touching the narrative prompt.

## Verification (round 4)

`python3 -m py_compile` passes clean on every `.py` file in this directory, including the new
`yoga_detection.py`. Ran `detect_all_yogas()` against a synthetic chart_data object matching
this package's expected shape (rich chart with multiple genuine yoga patterns present, an
empty/attribute-less chart_data, a chart_data with only partial fields set, and a chart_data
whose fields are explicitly `None`) — all four cases ran to completion with no exceptions, and
the rich-chart case correctly detected Budha-Aditya (with its tight-conjunction/combustion
note), Gaja-Kesari, and Dhana Yoga while correctly reporting Saraswati and Dharma-Karmadhipati
as not present given that chart's placements. `jyotish/astro.py` and `jyotish/constants.py`
are not present in this sandbox (only staged separately at
`/mnt/user-data/uploads/LLMbased - bkp/jyotish/astro.py`), so this sanity test used lightweight
fakes reproducing `_get_planetary_aspects`'s exact documented whole-sign-aspect behavior and
`_SIGN_LORD`'s real sign-lord table — `py_compile` itself does not execute imports, so this
does not affect the compile-cleanliness verification above.
