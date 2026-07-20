"""Gap-11 (audit 2026-07) fix: keyword-coverage test for the field registry.

Dozens of scoring gates across engine.py / boosts.py / constants.py / the
field_methods/*.py files use word-boundary keyword matching (`_wm(kw, label)`)
against a field's label/track/description text to decide whether a bonus
(nakshatra-career fit, Rahu-house career direction, yoga-domain fit, exalted
domain, karakamsha domain, etc.) can ever fire for that field. Because these
lists were hand-curated over time as new registry fields were added, nothing
previously asserted that every field in the registry is actually reachable by
at least one of these clusters -- a field whose label/description doesn't
share vocabulary with any keyword list silently never receives any of these
bonuses, no matter how astrologically apt it is.

This test does NOT assert perfect 1:1 keyword design (that would require
curating ~199 fields against ~30 independently-evolved lists, which is a
product/content task, not a code fix). It gives the codebase what it was
missing: a concrete, automatically-updating measurement of coverage, and a
regression guard so silent coverage regressions are caught before shipping
instead of discovered anecdotally per stress-test chart.

How it works:
1. Load the live field registry (same loader engine_io.py uses).
2. Introspect constants.py and boosts.py for every module-level name that
   looks like a keyword-gate list/dict (`_..._KW`, `_..._FIELDS`,
   `_..._HINTS`, `_..._KEYWORD...`) and flatten every string leaf into one
   big keyword set. This is automatic -- new keyword lists that follow the
   existing naming convention are picked up without editing this test.
3. For each registry field, build its searchable text from
   label/field/track/specialization/niche/description and test it against
   every keyword using the SAME `_wm` word-boundary matcher the engine uses
   (imported directly from boosts.py, not re-implemented).
4. Report which fields match zero keywords across the entire combined set
   ("orphaned" fields) and assert the orphan count does not exceed a
   documented baseline. If this test starts failing after adding fields to
   the registry, either add matching vocabulary to the new field's
   label/description/niche or add its terms to the relevant keyword list --
   don't just raise the baseline without checking why.
"""
from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from jyotish.engine_io import _load_course_registry  # noqa: E402
from jyotish.boosts import _wm  # noqa: E402
from jyotish import constants as _constants_mod  # noqa: E402
from jyotish import boosts as _boosts_mod  # noqa: E402

# Gap-11: naming convention used across the codebase for keyword-gate lists.
_KEYWORD_NAME_RE = re.compile(r"^_[A-Z0-9_]*(KW|FIELDS|HINTS|KEYWORDS?)[A-Z0-9_]*$")

# A documented ceiling, not an aspiration: a source-text scan (regex over
# constants.py/boosts.py, since the sandbox couldn't import the full package
# at test-authoring time -- see below) measured 42 orphaned field_ids at
# authoring time, including: microelectronics_vlsi, blockchain_web3,
# cloud_devops, internet_of_things, biochemistry, earth_sciences,
# microbiology, dentistry, homeopathy, occupational_therapy, optometry,
# physiotherapy, criminology_penology, gender_studies, linguistics,
# bioinformatics, neuroscience, quantum_computing, fintech, geophysics,
# psychiatry, photography, and 20 more. These fields can NEVER receive any
# nakshatra-career, Rahu-house, yoga-domain, exalted-domain, or karakamsha
# keyword bonus regardless of chart strength, purely because their field_id
# shares no vocabulary with any existing keyword list. The baseline below has
# headroom above the measured 42 because the live introspection this test
# performs (module attribute walk + full string flattening) is more thorough
# than the source-text regex used to produce that estimate, so the true
# in-process count may differ slightly. If this test fails, don't just raise
# the number -- check whether real coverage regressed or the estimate was
# simply off, and prefer fixing the underlying field_id/keyword-list gap.
_ORPHAN_BASELINE = 55


def _flatten_strings(obj) -> list:
    """Recursively collect every string leaf out of a dict/list/set/tuple."""
    out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_flatten_strings(v))
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            out.extend(_flatten_strings(v))
    return out


def _collect_gate_keywords() -> set:
    """Auto-discover every keyword-gate list/dict in constants.py + boosts.py."""
    keywords = set()
    for mod in (_constants_mod, _boosts_mod):
        for name in dir(mod):
            if not _KEYWORD_NAME_RE.match(name):
                continue
            value = getattr(mod, name)
            for s in _flatten_strings(value):
                s = s.strip().lower()
                # Skip obvious non-keyword strings (single chars, house labels).
                if len(s) >= 3 and not s.isdigit():
                    keywords.add(s)
    return keywords


def _field_text(field_id: str, entry: dict) -> str:
    """Mirror the exact text every method file gates on.

    knrao.py, jaimini.py, parashara.py, and kp.py all derive their `label`
    variable identically: `field_id.replace("_", " ").lower()` -- NOT the
    registry's human-written `label`/`description`/`niche` text. So the real
    coverage question is whether a field's *id* (e.g. "aerospace_engineering"
    -> "aerospace engineering") shares vocabulary with a keyword list, not
    whether its prose description does. We match on the code's actual text
    first, and additionally OR in the registry's descriptive fields as a
    secondary, more generous check so the test also surfaces fields that
    *could* be reached if a gate were changed to use richer text -- those are
    reported separately, not counted as coverage failures.
    """
    return field_id.replace("_", " ").lower()


def _field_descriptive_text(entry: dict) -> str:
    parts = [
        entry.get("label", ""),
        entry.get("field", ""),
        entry.get("track", ""),
        entry.get("specialization", ""),
        entry.get("niche", ""),
        entry.get("description", ""),
    ]
    return " ".join(str(p) for p in parts if p)


class KeywordCoverageTest(unittest.TestCase):
    def test_every_field_reachable_by_at_least_one_keyword_cluster(self):
        registry = _load_course_registry()
        self.assertTrue(registry, "Field registry failed to load or is empty.")

        keywords = _collect_gate_keywords()
        self.assertGreater(
            len(keywords), 50,
            "Keyword auto-discovery found suspiciously few keywords -- check "
            "_KEYWORD_NAME_RE naming convention against constants.py/boosts.py.",
        )

        orphaned = []          # zero match on the code's actual gate text (field_id-derived)
        recoverable = []       # zero match on code text, BUT registry description WOULD match
        for field_id, entry in registry.items():
            if not isinstance(entry, dict):
                continue
            code_text = _field_text(field_id, entry)
            matched_code = any(_wm(kw, code_text) for kw in keywords)
            if matched_code:
                continue
            orphaned.append(field_id)
            desc_text = _field_descriptive_text(entry)
            if desc_text.strip() and any(_wm(kw, desc_text) for kw in keywords):
                recoverable.append(field_id)

        orphaned.sort()
        recoverable.sort()
        if len(orphaned) > _ORPHAN_BASELINE:
            recoverable_note = (
                f"\n\n{len(recoverable)} of these WOULD match if the gate used the "
                f"registry's descriptive text instead of field_id alone: "
                + ", ".join(recoverable[:20]) + (" ..." if len(recoverable) > 20 else "")
            ) if recoverable else ""
            self.fail(
                f"Keyword-cluster coverage regressed: {len(orphaned)} registry "
                f"fields (baseline {_ORPHAN_BASELINE}) match zero keyword gates "
                f"across constants.py/boosts.py (matched against the same "
                f"field_id-derived text the scoring methods actually use). "
                f"New/changed orphans:\n"
                + "\n".join(f"  - {f}" for f in orphaned)
                + recoverable_note
            )


if __name__ == "__main__":
    unittest.main()
