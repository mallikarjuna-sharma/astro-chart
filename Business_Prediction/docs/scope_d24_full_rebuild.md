# Scope: D24 (Siddhamsha) Full Rebuild

Planning only -- nothing implemented yet. Grounded against the actual
payload/code as of business-engine.v43.

## Current state

`_d24_competency_status()` (`business_determination/d24_d60_sign.py:133`)
asks exactly one question: what is the D24 dignity of the natal (D1) 10th
lord? It returns a single multiplicative factor (0.55/1.0/1.15) consumed
only by `business_execution_capacity`. Nothing else about D24 is read.

## What's actually available and unused

This is the key finding that makes this a tractable project rather than a
speculative one: `jyotish/engine_io.py` already computes and exposes far
more D24 data on the payload than `business_determination` currently reads.

- `payload.d24_lagna_sign` -- the D24 ascendant sign (e.g. "Virgo"),
  computed from `divisional_charts.D24_siddhamsam.Lagna` (engine_io.py:268).
- `payload.d24_house_lords` -- a full `{"1":"Mercury", "2":"Venus", ...}`
  house-lord map for all 12 D24 houses, derived from the D24 Lagna sign
  (engine_io.py:271).
- `payload.d24_house_occupancy` -- whole-sign D24 house -> occupant-planet-list
  map (engine_io.py:832).
- `payload.d24_planet_dignities` -- dignity per planet in D24
  (engine_io.py:328, via `compute_dignity()`, the same function D9/D10 use).

None of `d24_lagna_sign`, `d24_house_lords`, or `d24_house_occupancy` are
read anywhere in `business_determination/` today -- only
`d24_planet_dignities` is, and only for one planet (the D1 10th lord).

## What a real D24 analysis needs (per the audit)

1. **D24 Lagna and Lagnesh** -- dignity/placement of the D24 ascendant lord.
   Directly buildable: `d24_house_lords["1"]`, its D24 house via
   `d24_house_occupancy`, its dignity via `d24_planet_dignities`.
2. **D24 H4/H5/H9/H10** -- house-lord strength for the houses classically
   tied to education/foundation (H4), aptitude/intelligence (H5),
   higher-learning/mentorship (H9), and the career-competency house itself
   (H10). Directly buildable the same way, and structurally identical to
   the existing `_d10_house_lord_strength()` pattern in `house_evidence.py`
   -- that function is a template, not something to invent from scratch.
3. **Occupants and aspects** -- who sits in each of those D24 houses
   (`d24_house_occupancy` already has this) and whether benefics/malefics
   support or afflict them. Aspects specifically are NOT free: this repo's
   whole-sign special-aspect logic (Mars/Jupiter/Saturn) exists in
   `house_evidence.py` for D1/D10 but isn't parameterized for an arbitrary
   house-lord/occupancy map yet -- would need a small generalization, not a
   rewrite.
4. **Vidya yogas** -- classical D24 combinations for
   education/skill-acquisition success (e.g. D24 Lagna lord in kendra/trikona
   from D24 Lagna, benefics in D24 H4/H5/H9). This is the one item that's
   genuinely new doctrine, not a data-availability question -- needs an
   explicit, disclosed list of which yoga(s) are implemented and which
   classical variants were NOT attempted (matching this codebase's existing
   practice for Viparita Raja Yoga's own disclosed gaps).
5. **Dispositor chains** -- whether a D24 house lord's own dispositor
   (the lord of the sign that lord sits in) is itself strong or weak.
   Straightforward given `d24_house_lords` + `d24_planet_dignities`, but is
   a new helper (`_d24_dispositor_strength()`), not a reuse of an existing
   D1/D10 dispositor function (this codebase doesn't have one for ANY
   divisional chart yet -- item 13 in the audit, "dispositor chains are
   incomplete", applies everywhere, not just D24).
6. **D1-D10-D24 coherence** -- does the D24 read agree or disagree with the
   existing D1/D10-based `business_execution_capacity`? This is a new
   contradiction-style check, following the same pattern as the existing
   D1-vs-D10 operating-model contradiction (`contradictions.py`) already
   does for two OTHER charts -- extending that established pattern to a
   third, not inventing a new mechanism.
7. **Skill-type vs business-type matching** -- whether the competencies D24
   suggests actually match the sector/operating-model the rest of the
   engine is recommending. This is the least well-defined item: it needs an
   explicit mapping from D24 house/planet signatures to skill categories,
   and then a comparison against `top_sectors`/`operating_model` -- closer
   in spirit to the existing sector-registry combo-bonus mechanism
   (`sectors.py::_sector_house_combination_bias`) than anything else in the
   codebase, but would need its own registry-style mapping table authored
   from scratch (no existing "skill category" concept exists anywhere in
   this repo today).

## Proposed shape of the change

- New function `_d24_full_analysis(payload) -> dict` in `d24_d60_sign.py`,
  returning a structured result (Lagnesh strength, H4/H5/H9/H10 strengths,
  dispositor notes, Vidya-yoga hits, D1/D10 coherence note) -- NOT a single
  collapsed number, matching this codebase's own house_evidence.py
  convention of returning an inspectable evidence list rather than an
  opaque score.
- `_d24_competency_status()` is kept as-is (backward compatible -- multiple
  existing tests and `business_execution_capacity` read its exact
  `{status, factor, note}` shape) and gains a NEW sibling field,
  `d24_full_analysis`, rather than being restructured in place. This
  mirrors how `business_execution_capacity_components` was added alongside
  (not instead of) `business_execution_capacity` in a prior round.
- `business_execution_capacity`'s existing single-factor D24 discount stays
  mechanically unchanged in this first pass -- widening what it's driven by
  (beyond just 10th-lord dignity) is a natural follow-up once the full
  analysis exists and has been spot-checked against real charts, not
  something to fold into the same change that introduces the new data.

## Sizing and risk

- **Items 1-3, 6** (Lagnesh, H4/H5/H9/H10 strength, occupancy, D1/D10
  coherence): low risk, direct reuse of existing patterns and already-
  available payload data. This is the bulk of "full D24 analysis" in
  practical terms.
- **Item 5** (dispositor chains): low-moderate risk, new but simple helper.
- **Item 4** (Vidya yogas): moderate risk -- the actual yoga definitions
  need to be chosen and disclosed explicitly; over-claiming coverage here
  would recreate the exact problem this whole audit has been finding
  elsewhere (Viparita Raja Yoga, rare-cancellation coverage).
- **Item 7** (skill-type/business-type matching): highest risk and least
  scoped -- effectively a new registry-authoring project, not a natural
  extension of anything that exists. Recommend treating this as an
  explicitly separate, later follow-up rather than bundling it into the
  same change as items 1-6.
- **Testing**: needs new fixtures in `test_business_engine.py` exercising a
  chart with a real D24_siddhamsam block (the existing `_FakePayload`
  doesn't set `d24_lagna_sign`/`d24_house_lords`/`d24_house_occupancy` at
  all), plus verification against at least one real chart from `Charts/`
  the way every other fix this session was checked against real data, not
  just synthetic fixtures.

## Recommended cut for a first implementation pass

Items 1, 2, 3, 5, 6 (Lagnesh + H4/H5/H9/H10 strength + occupants/aspects +
dispositor chains + D1/D10/D24 coherence) as one bounded, additive change.
Item 4 (Vidya yogas) as a clearly-scoped second pass with explicit
doctrine disclosure. Item 7 (skill/business matching) deferred as its own
project -- it's a registry-design problem, not a scoring problem.
