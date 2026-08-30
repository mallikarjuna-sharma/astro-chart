#!/usr/bin/env python3
"""followup.py — grounded follow-up Q&A and re-forecast alert checks over
an ALREADY-COMPUTED Business_Prediction prediction dict.

Two entry points:

  answer_followup_question(prediction, question, lang="en",
                            use_llm_narrative=False)
      Deterministic keyword routing over the sections already present on
      `prediction` (partnership_synastry, legal_dispute_risk,
      detected_yogas, timed_windows, ...). Never recomputes the chart,
      never calls an external LLM by default, and never fabricates an
      answer for a question nothing in `prediction` addresses -- see
      _ROUTES below and the NO_MATCH branch.

  check_reforecast_needed(prediction, as_of_date=None)
      Compares prediction['timed_windows'] (and, if present,
      prediction['ashtakavarga_years']) against `as_of_date` to flag
      whether the native has moved past the dasha/bhukti window(s) the
      report was originally computed for, or into a previously-flagged
      strong Ashtakavarga year. Status-check only -- no scheduling, no
      email, no side effects.

Both functions are pure/read-only over `prediction`; neither mutates it.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

_repo = pathlib.Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


# ─────────────────────────────────────────────────────────────────────────
# answer_followup_question
# ─────────────────────────────────────────────────────────────────────────

# Each route: (route_name, keywords, prediction_key(s) to pull evidence
# from). Keyword matching is a simple case-insensitive substring test on
# the question -- deliberately simple/honest rather than clever, since the
# whole point of this function is that it never claims to understand more
# than it does. A question can match more than one route (matched_sections
# lists every route that fired); order below only affects the order
# sections appear in the returned evidence, not which routes can fire.
_ROUTES: List[Dict[str, Any]] = [
    {
        "name": "partnership_synastry",
        "keywords": ["partner", "partnership", "co-founder", "cofounder", "spouse", "marriage compatibility"],
        "keys": ["partnership_synastry"],
    },
    {
        "name": "legal_dispute_risk",
        "keywords": ["risk", "legal", "dispute", "lawsuit", "litigation", "contract"],
        "keys": ["legal_dispute_risk"],
    },
    {
        "name": "detected_yogas",
        "keywords": ["yoga", "combination", "raja yoga", "dhana yoga", "special combination"],
        "keys": ["detected_yogas"],
    },
    {
        "name": "timing_windows",
        "keywords": ["timing", "when", "year", "window", "dasha", "bhukti", "period", "muhurta", "date"],
        "keys": ["timed_windows", "detected_yogas"],
    },
    {
        "name": "sectors",
        "keywords": ["sector", "industry", "field", "which business", "what business", "domain"],
        "keys": ["top_sectors"],
    },
    {
        "name": "wealth_flow",
        "keywords": ["wealth", "money", "profit", "revenue", "income", "cash flow"],
        "keys": ["d2_hora_evidence", "business_profitability", "gross_revenue_potential", "profit_retention"],
    },
    {
        "name": "recommendation",
        "keywords": ["should i", "recommend", "proceed", "verdict", "pursue business"],
        "keys": ["authoritative_recommendation", "recommendation"],
    },
]

_NO_MATCH_MESSAGE = {
    "en": (
        "This question isn't addressed by anything already computed in this report. "
        "No answer is being fabricated -- ask a question about partnership/co-founder fit, "
        "legal/dispute risk, detected yogas, timing windows, business sectors, wealth flow, "
        "or the overall recommendation, or request a fresh computation covering this topic."
    ),
    "ta": (
        "இந்த அறிக்கையில் ஏற்கனவே கணக்கிடப்பட்ட எதுவும் இந்தக் கேள்விக்கு பதிலளிக்கவில்லை. "
        "பதில் கற்பனையாக உருவாக்கப்படவில்லை."
    ),
    "te": (
        "ఈ నివేదికలో ఇప్పటికే లెక్కించిన దేనికీ ఈ ప్రశ్న సంబంధించినది కాదు. "
        "సమాధానం కల్పితంగా రూపొందించబడలేదు."
    ),
}


def _route_matches(question_lower: str, route: Dict[str, Any]) -> bool:
    return any(kw in question_lower for kw in route["keywords"])


def _collect_evidence(prediction: Dict[str, Any], route: Dict[str, Any]) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {}
    for key in route["keys"]:
        val = prediction.get(key)
        if val:
            evidence[key] = val
    return evidence


def answer_followup_question(
    prediction: Dict[str, Any],
    question: str,
    lang: str = "en",
    use_llm_narrative: bool = False,
    payload: Optional[Any] = None,
) -> Dict[str, Any]:
    """Grounds an answer to `question` in the already-computed `prediction`
    dict via simple, honest keyword/section routing. Does NOT recompute
    the chart and does NOT call an external LLM unless BOTH
    use_llm_narrative=True is passed AND consent is already granted per
    the existing _has_llm_narrative_consent() gate in
    generate_business_report.py -- the default (use_llm_narrative=False)
    is fully deterministic and works offline.

    Returns
    -------
    {
        "question": str,
        "matched_sections": [route names that fired],
        "confidence": "GROUNDED" | "NO_MATCH",
        "evidence": {prediction_key: prediction[key], ...} (only present
            keys, only for matched routes),
        "message": str (human-readable summary; for NO_MATCH this is an
            honest "not addressed" message, never a fabricated answer),
        "narrative": str | None (only populated if use_llm_narrative=True
            and consent was granted; a plain-language rephrasing of
            `evidence`, still strictly grounded in it -- no new claims).
    }
    """
    if not question or not question.strip():
        return {
            "question": question,
            "matched_sections": [],
            "confidence": "NO_MATCH",
            "evidence": {},
            "message": _NO_MATCH_MESSAGE.get(lang, _NO_MATCH_MESSAGE["en"]),
            "narrative": None,
        }

    q_lower = question.lower()
    matched_routes = [r for r in _ROUTES if _route_matches(q_lower, r)]

    if not matched_routes:
        return {
            "question": question,
            "matched_sections": [],
            "confidence": "NO_MATCH",
            "evidence": {},
            "message": _NO_MATCH_MESSAGE.get(lang, _NO_MATCH_MESSAGE["en"]),
            "narrative": None,
        }

    matched_sections: List[str] = []
    evidence: Dict[str, Any] = {}
    for route in matched_routes:
        route_evidence = _collect_evidence(prediction, route)
        if route_evidence:
            matched_sections.append(route["name"])
            evidence.update(route_evidence)

    if not evidence:
        # Keywords matched a route, but this particular chart has nothing
        # under that route's key(s) (e.g. asked about "partnership" but
        # partnership_synastry was never computed for this native) --
        # still honest NO_MATCH, not a fabricated answer.
        return {
            "question": question,
            "matched_sections": [],
            "confidence": "NO_MATCH",
            "evidence": {},
            "message": _NO_MATCH_MESSAGE.get(lang, _NO_MATCH_MESSAGE["en"]),
            "narrative": None,
        }

    result: Dict[str, Any] = {
        "question": question,
        "matched_sections": matched_sections,
        "confidence": "GROUNDED",
        "evidence": evidence,
        "message": (
            f"Answer grounded in already-computed report section(s): {', '.join(matched_sections)}."
        ),
        "narrative": None,
    }

    if use_llm_narrative:
        narrative = _maybe_llm_rephrase(evidence, question, lang, payload)
        result["narrative"] = narrative

    return result


def _maybe_llm_rephrase(
    evidence: Dict[str, Any], question: str, lang: str, payload: Optional[Any],
) -> Optional[str]:
    """Optional LLM rephrasing of the routed evidence into fuller prose.
    Only runs if the existing consent gate (_has_llm_narrative_consent,
    same contract as the rest of this repo's LLM narrative layer) grants
    consent; returns None (never raises, never fabricates) otherwise --
    the caller already has the deterministic `evidence`/`message` fields
    regardless of whether this succeeds."""
    try:
        from Business_Prediction.generate_business_report import (
            _has_llm_narrative_consent,
            _translate_texts_llm,
        )
    except Exception:
        return None

    if not _has_llm_narrative_consent(payload):
        return None

    # Reuse the existing batched-translation LLM path as a lightweight
    # rephrasing call: feed it a single "evidence summary -> plain
    # sentence" prompt string. This intentionally piggybacks on
    # _translate_texts_llm's already-consent-gated plumbing rather than
    # opening a second, separate LLM call path in this module.
    summary = f"Question: {question}\nEvidence: {evidence}"
    try:
        translated = _translate_texts_llm([summary], lang=lang, payload=payload)
    except Exception:
        return None
    if not translated:
        return None
    return translated[0]


# ─────────────────────────────────────────────────────────────────────────
# check_reforecast_needed
# ─────────────────────────────────────────────────────────────────────────

def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def check_reforecast_needed(
    prediction: Dict[str, Any],
    as_of_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Status-check only: determines whether a fresh report computation is
    warranted, comparing prediction['timed_windows'] (as already computed
    by timing.py and embedded in the prediction dict at report-generation
    time) against `as_of_date` (default: today).

    Flags reforecast_recommended=True when:
      (a) `as_of_date` falls after every window's end_date in
          prediction['timed_windows'] -- i.e. the native has moved past
          the entire dasha/bhukti calendar the report was computed for,
          or
      (b) `as_of_date` falls inside a *different* window than the one
          that was current at the earliest window's start (a dasha/bhukti
          change since the report was generated), or
      (c) a previously-flagged Ashtakavarga strong year
          (prediction['ashtakavarga_years']['ranked_years'], if present --
          this key is only populated when the caller separately invoked
          rank_business_years() and merged it into the prediction dict)
          has an as_of_date year >= its flagged year.

    Returns
    -------
    {"reforecast_recommended": bool, "reason": str, "next_check_date": str}

    Does NOT schedule, email, or otherwise act on the result -- that is
    explicitly out of scope; this is the decision logic only, for a
    caller (e.g. a scheduled job elsewhere) to act on.
    """
    today = _parse_date(as_of_date) or date.today()

    windows = prediction.get("timed_windows") or []
    parsed_windows = []
    for w in windows:
        start = _parse_date(w.get("start_date"))
        end = _parse_date(w.get("end_date"))
        if start and end:
            parsed_windows.append((start, end, w))

    if not parsed_windows:
        return {
            "reforecast_recommended": True,
            "reason": (
                "No usable timed_windows found on this prediction (empty, missing start/end dates, "
                "or timing computation did not succeed originally) -- recommend a fresh computation "
                "to establish a current timing baseline."
            ),
            "next_check_date": (today + timedelta(days=30)).isoformat(),
        }

    parsed_windows.sort(key=lambda t: t[0])
    earliest_start = parsed_windows[0][0]
    latest_end = max(w[1] for w in parsed_windows)

    # Case (a): entirely past the computed calendar.
    if today > latest_end:
        return {
            "reforecast_recommended": True,
            "reason": (
                f"as_of_date {today.isoformat()} is past the end of every timed window in this "
                f"report (latest window ends {latest_end.isoformat()}) -- the native has moved "
                "beyond the dasha/bhukti calendar this report was generated for."
            ),
            "next_check_date": today.isoformat(),
        }

    # Which window (if any) was current at the earliest window's start
    # (i.e. "current" as of report-generation time) vs which window is
    # current as of as_of_date -- a change signals a dasha/bhukti shift.
    def _window_at(d: date):
        for start, end, w in parsed_windows:
            if start <= d <= end:
                return (start, end, w.get("md_lord"), w.get("ad_lord"))
        return None

    original_window = _window_at(earliest_start)
    current_window = _window_at(today)

    if current_window is not None and original_window is not None and current_window[:2] != original_window[:2]:
        return {
            "reforecast_recommended": True,
            "reason": (
                f"as_of_date {today.isoformat()} falls in a different dasha/bhukti window "
                f"(md_lord={current_window[2]}, ad_lord={current_window[3]}, "
                f"{current_window[0].isoformat()}..{current_window[1].isoformat()}) than the window "
                f"current when this report was generated (md_lord={original_window[2]}, "
                f"ad_lord={original_window[3]}, {original_window[0].isoformat()}..{original_window[1].isoformat()})."
            ),
            "next_check_date": current_window[1].isoformat(),
        }

    # Case (c): a previously-flagged strong Ashtakavarga year has arrived.
    av = prediction.get("ashtakavarga_years") or {}
    ranked_years = av.get("ranked_years") if isinstance(av, dict) else None
    if ranked_years:
        strong_years = [
            y.get("year") for y in ranked_years
            if isinstance(y, dict) and str(y.get("tier", "")).upper() in ("STRONG", "VERY_STRONG")
            and isinstance(y.get("year"), int)
        ]
        for year in sorted(strong_years):
            if today.year >= year:
                return {
                    "reforecast_recommended": True,
                    "reason": (
                        f"as_of_date {today.isoformat()} has reached or passed the previously-flagged "
                        f"strong Ashtakavarga year {year} -- a fresh timing pass is warranted to confirm "
                        "the window is still active/favorable."
                    ),
                    "next_check_date": today.isoformat(),
                }

    # No trigger fired -- still inside the originally-computed window and
    # (if data available) no flagged strong year has arrived yet.
    next_check = current_window[1] if current_window else latest_end
    return {
        "reforecast_recommended": False,
        "reason": (
            f"as_of_date {today.isoformat()} is still inside the dasha/bhukti window this report was "
            "originally computed for, and no flagged strong Ashtakavarga year has arrived -- no "
            "reforecast needed yet."
        ),
        "next_check_date": next_check.isoformat(),
    }
