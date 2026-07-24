"""Stream_Determination — early-age (<15) broad-stream + subject engine.

This package is deliberately independent of Field_Determination's 199-branch
field-ranking engine. For a natal chart belonging to a child under 15, running
the full career/field engine (199 specific vocational branches, route
suitability, defensibility contracts, etc.) is premature -- what's actually
useful at that age is a coarse, defensible signal at the level Indian
secondary education actually asks a student to choose at: Science / Commerce /
Humanities, plus which specific subjects within the chosen (or each) stream
the chart supports most strongly.

Only chart-parsing and low-level astrology primitives are shared with the
rest of the codebase (jyotish.engine_io, jyotish.astro, jyotish.constants,
jyotish.validation_contract) and a few generic output-shaping helpers from
Field_Determination.field_methods.common. No dependency runs the other way:
Field_Determination's own engine never imports this package, and this
package never imports jyotish.engine / jyotish.affinity / the 199-field
course registry.

Entry point: early_age_stream_engine.py (CLI + run_for_payload()).
"""
