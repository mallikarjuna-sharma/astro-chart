"""jyotish/astrology_explainer.py

Pure astrological-reasoning functions extracted out of jyotish/web_report.py
(Phase 1 of the career-report refactor). These functions contain the actual
Vedic-astrology judgment logic (KP verdicts, yoga explanations, "career
weather" mood mapping, dusthana placement flags) that was previously
interleaved directly inside HTML-rendering code in web_report.py.

Behavior-preserving relocation: no astrological doctrine was changed here,
only moved and (where a function was a nested closure) hoisted to module
level so it can be reused by the new view-model / narrative-composer layer
(jyotish/view_model.py, jyotish/narrative_composer.py) without importing the
entire HTML-string-building web_report module.

jyotish/web_report.py imports these names back from this module so the
legacy renderer keeps working unchanged (regression safety net).
"""
from typing import Any, Dict, List, Optional, Tuple


# BUG FIX (2026-07-05): _CAREER_WEATHER, _ROADMAP_SIGNAL_DOT, and _NET_SIGNAL_COLOR
# were all referenced below (and further down in the node-rendering loop) without
# ever being defined anywhere in this module — each one is a fresh NameError that
# crashes _build_career_roadmap_html() and, in turn, generate_career_timeline_report()
# entirely (silently caught by the CLI, producing no HTML output). Defining all three
# here, alongside the already-fixed _ROADMAP_EVENT_COLORS.
#
# Ordered highest-bar-first; _career_weather() takes the first row whose thresholds
# are both satisfied by the combined score/signal.
_CAREER_WEATHER: list = [
    # (min_score, min_net_favor, emoji, label)
    (0.70,  1, "☀️", "Strong Tailwind"),
    (0.70,  0, "🌤️", "Bright, Steady"),
    (0.55,  1, "🌤️", "Favorable Winds"),
    (0.55,  0, "⛅", "Steady, Mixed"),
    (0.40, -1, "🌥️", "Cloudy, Cautious"),
    (0.40,  0, "⛅", "Steady, Mixed"),
    (0.00, -1, "🌧️", "Headwinds"),
]

_ROADMAP_SIGNAL_DOT = {
    "favorable":   "#059669",
    "mixed":       "#D97706",
    "neutral":     "#94A3B8",
    "challenging": "#DC2626",
}

_NET_SIGNAL_COLOR = {
    "Favorable":  ("#065F46", "#D1FAE5"),
    "Mixed":      ("#92400E", "#FEF3C7"),
    "Challenging":("#991B1B", "#FEE2E2"),
}


def _career_weather(score: float, net_signal: str) -> tuple:
    """Map a year's career score + transit net signal to a 'career weather'
    mood — an at-a-glance visual metaphor replacing the removed detailed
    dasha cards' wall of text."""
    net_favor = {"Favorable": 1, "Mixed": 0, "Challenging": -1}.get(net_signal, 0)
    combined = score + (net_favor * 0.06)
    for min_score, min_favor, emoji, label in _CAREER_WEATHER:
        if combined >= min_score and net_favor >= min_favor:
            return emoji, label
    return "⛅", "Steady, Mixed"


_KP_CAREER_HOUSES = {
    "2":  "income",
    "6":  "job/service/competition",
    "10": "career/authority",
    "11": "gains/networks",
    "12": "loss/foreign/expenditure",
    # Gap-review (4th round, Gap 7): added so event-specific KP verdicts
    "1":  "self/identity/leadership",
    "3":  "effort/short-travel/change-of-job",
    "5":  "recognition/intelligence/authority-of-merit",
    "8":  "sudden-change/transformation/loss",
    "9":  "fortune/long-journeys/foreign",
}

# Gap-review (4th round, Gap 7): a single KP verdict ("3 of 4 career houses
# support") is too coarse — classical KP practice judges each EVENT TYPE
# against its own required house combination, since a chart can favor
# promotion houses while denying job-change houses in the same period.
_KP_EVENT_HOUSE_RULES = {
    "Promotion":   (("2", "6", "10", "11"), ()),
    "Income":      (("2", "6", "11"), ()),
    "Job Change":  (("3", "10", "12"), ()),
    "Foreign":     (("3", "9", "10", "12"), ()),
    "Leadership":  (("1", "5", "10", "11"), ()),
    "Risk":        (("8", "12"), ("10",)),   # supportive houses are 8/12; 10 here is a BLOCKING/weakening house
}


def _kp_house_chain_summary(kp_cusps: dict) -> dict:
    """Phase-1 fix (2026-07-05 roadmap): print the full KP cusp chain
    (sign lord / star lord / sub lord / sub-sub lord) for every career-relevant
    house (2/6/10/11/12), not just H10 in isolation. This is the concrete data
    a KP promotion/job-change/loss verdict needs (2+6+10+11 for promotion,
    3+10+12 for job change, 8+12+weak-10 for loss) — previously only H10 was
    surfaced in the sidebar, and the year narratives had no access to the
    other houses at all, so they could never actually apply the classical
    multi-house KP test even though the source cusp data (payload.kp_cusps)
    always had it."""
    chain = {}
    for h, theme in _KP_CAREER_HOUSES.items():
        cusp = kp_cusps.get(f"H{h}", {}) or {}
        if not cusp:
            continue
        chain[f"H{h}"] = {
            "theme":      theme,
            "sign_lord":  cusp.get("sign_lord", ""),
            "star_lord":  cusp.get("star_lord", ""),
            "sub_lord":   cusp.get("sub_lord", ""),
            "sub_sub_lord": cusp.get("sub_sub_lord", ""),
        }
    return chain


def _kp_event_verdicts(kp_house_chain: dict, md_lord: str = "", ad_lord: str = "") -> list:
    """New computation (2026-07-06, roadmap gap): reuses the existing
    `_KP_EVENT_HOUSE_RULES` house-requirement map (already defined above but
    never called anywhere before this fix) plus the per-year KP cusp chain
    already surfaced via `_kp_house_chain_summary()` to compute an
    independent KP verdict for EACH candidate event type, instead of only
    ever exposing the single event_type the deterministic scorer happened to
    pick. For every event type's required houses, a house "supports" that
    event if its sign/star/sub lord chain contains the period's own running
    MD or AD lord (the classical KP test: does the cuspal sub-lord of the
    house tie back to the operating dasha lord?). Houses in the tuple's
    second slot are BLOCKING houses (currently only used for "Risk") and
    count negatively.

    This performs no new astrological doctrine beyond what
    `_KP_EVENT_HOUSE_RULES` already encodes (itself pre-existing, unused
    code) — it only evaluates it multiple times, once per event type,
    instead of discarding all but the winning one. Conservative by
    construction: a house only "supports" if the running MD/AD lord
    literally appears somewhere in that house's cusp chain; no fuzzy/implied
    scoring is added.
    """
    if not kp_house_chain:
        return []
    _lords = {l for l in (md_lord, ad_lord) if l}
    if not _lords:
        return []
    results = []
    for event_name, (support_houses, block_houses) in _KP_EVENT_HOUSE_RULES.items():
        _total = len(support_houses) + len(block_houses)
        if _total == 0:
            continue
        _hit = 0.0
        for h in support_houses:
            cusp = kp_house_chain.get(f"H{h}")
            if not cusp:
                continue
            _chain_lords = {cusp.get("sign_lord"), cusp.get("star_lord"),
                             cusp.get("sub_lord"), cusp.get("sub_sub_lord")}
            if _chain_lords & _lords:
                _hit += 1.0
        for h in block_houses:
            cusp = kp_house_chain.get(f"H{h}")
            if not cusp:
                continue
            _chain_lords = {cusp.get("sign_lord"), cusp.get("star_lord"),
                             cusp.get("sub_lord"), cusp.get("sub_sub_lord")}
            if _chain_lords & _lords:
                _hit -= 1.0
        _evaluated = sum(1 for h in support_houses if kp_house_chain.get(f"H{h}")) + \
                     sum(1 for h in block_houses if kp_house_chain.get(f"H{h}"))
        if _evaluated == 0:
            continue
        _ratio = _hit / _evaluated
        if _ratio >= 0.6:
            verdict, color = "Supports", "var(--green,#1E7B50)"
        elif _ratio >= 0.3:
            verdict, color = "Mixed", "var(--amber,#B8720A)"
        else:
            verdict, color = "Denies", "var(--red,#B33A2E)"
        results.append({
            "name": event_name,
            "verdict": verdict,
            "color": color,
            "detail": f"{max(_hit, 0.0):.1f}/{_evaluated} houses",
        })
    return results


_YOGA_TRADITIONAL_DOMAIN = {
    "Gajakesari":  "career",
    "Budha_Aditya":"career",
    "Ruchaka":     "career",
    "Bhadra":      "career",
    "Hamsa":       "career",
    "Malavya":     "career",
    "Sasha":       "career",
    "Rajayoga":    "career",
    "Dhana_Yoga":  "finance",
    "ChandraMangala": "finance",
    "Amala":       "career",
    "Harsha_VRY":  "career",     # 6th-lord reversal — service/competition domain, still career-adjacent
    "Sarala_VRY":  "career",     # 8th-lord reversal — transformation, still career-adjacent
    "Vimala_VRY":  "moksha",     # 12th-lord (expenditure/loss/detachment/moksha) — NOT primarily career
    "Adhi_Yoga":   "career",
    "Chamara_Yoga":"career",
    "Vasumati_Yoga":"finance",
    "Kemadruma":   "general",
    "Kala_Sarpa":  "general",
}

def _domain_hedge(tag: str, explanation: str) -> str:
    """Append a qualifying sentence when a yoga's own traditional domain
    isn't "career" but it's being surfaced inside a career report."""
    _base = tag.split("_VRY")[0] + "_VRY" if tag.endswith("_VRY") else tag.split("_")[0]
    _domain = None
    for _k, _v in _YOGA_TRADITIONAL_DOMAIN.items():
        if tag == _k or tag.startswith(_k + "_") or tag.startswith(_k):
            _domain = _v
            break
    if _domain and _domain != "career":
        _domain_label = {
            "finance": "wealth/finance",
            "moksha": "moksha/detachment/reduced-expenditure",
            "health": "health",
            "general": "general life-condition",
        }.get(_domain, _domain)
        explanation = (
            explanation.rstrip(".") +
            f". Traditional domain note: this yoga's classical significations are "
            f"primarily {_domain_label}, not direct career gain — cited here for "
            f"completeness, but its presence should not be read as asserting a "
            f"career-specific outcome."
        )
    return explanation


def _explain_yoga_tag(tag: str) -> str:
    """Return a one-sentence, career-focused explanation for a detected yoga tag.

    Handles the two most common structured tag families first (Parivartana /
    NakParivartana mutual-exchange yogas, which encode the two planets involved
    in their own name), then falls back to a lookup table for named classical
    yogas, then a generic explanation if the tag is otherwise unrecognised."""
    # Gap fix (2026-07-05): Amala Yoga (10th-house benefic) requires the
    # benefic to be unafflicted to give its classical "spotless career"
    # result. When a natural malefic (Rahu/Ketu/Saturn/Mars) co-occupies the
    # same house, timeline.py's detector now emits "Amala_Yoga_Partial__<afflictor(s)>"
    # instead of the plain "Amala_Yoga" tag — surface that qualifier here so
    # the narrative never asserts an unblemished result in the same house a
    # different panel is (correctly) describing as afflicted/volatile.
    if tag.startswith("Amala_Yoga_Partial"):
        _afflictors = tag.split("__", 1)[1].replace("_", ", ") if "__" in tag else "a natural malefic"
        return (
            f"Amala Yoga (partial — conjunct {_afflictors}, conditional): a benefic occupies "
            f"the 10th house from Lagna/Moon, which classically supports professional "
            f"reputation, but {_afflictors} co-occupies the same house. Classical Amala Yoga "
            f"requires the benefic to be unafflicted; this placement is real but qualified — "
            f"expect the reputational benefit to coexist with (and be complicated by) the "
            f"co-occupant's own significations (e.g. detachment/volatility for Ketu) rather "
            f"than a clean, unblemished result."
        )
    if tag.startswith("NakParivartana_"):
        parts = tag.split("_")[1:]
        if len(parts) == 2:
            p1, p2 = parts
            return (
                f"{p1} and {p2} sit in each other's nakshatra (a KP-style star-lord "
                f"exchange): {p1} occupies a nakshatra ruled by {p2} while {p2} sits in "
                f"one ruled by {p1}. This is a subtler cousin of a sign-based Parivartana "
                f"— it binds the two planets' significations together at a finer "
                f"(nakshatra) resolution, so periods ruled by either planet tend to "
                f"deliver outcomes that draw on BOTH planets' domains simultaneously."
            )
        return f"{tag.replace('_', ' ')} — a nakshatra-level (KP star-lord) mutual exchange yoga."
    if tag.startswith("Parivartana_H10_"):
        _house_map = {
            "H1":  "the Lagna (1st house, self/identity)",
            "H2":  "the 2nd house (wealth, family resources)",
            "H6":  "the 6th house (service, competition, daily work)",
            "H11": "the 11th house (income, gains, networks)",
        }
        target = tag.replace("Parivartana_H10_", "")
        house_desc = _house_map.get(target, target)
        return (
            f"The 10th house (career) lord and the lord of {house_desc} are in mutual "
            f"sign exchange (Parivartana) — each planet sits in the other's sign. This "
            f"directly wires career authority to that house's domain: whenever either "
            f"lord's dasha/antardasha runs, both houses' significations activate together, "
            f"typically strengthening career outcomes tied to that house's theme."
        )
    if tag.startswith("Parivartana_"):
        parts = tag.split("_")[1:]
        if len(parts) == 2:
            p1, p2 = parts
            return (
                f"{p1} and {p2} are in mutual sign exchange (Rasi Parivartana): {p1} sits "
                f"in a sign owned by {p2}, and {p2} sits in a sign owned by {p1}. Classically "
                f"this creates a strong, near-permanent alliance between whatever these two "
                f"planets signify — during either planet's dasha/antardasha, the other "
                f"planet's houses and significations are pulled in as well, effectively "
                f"doubling the reach of that period."
            )
        return f"{tag.replace('_', ' ')} — a sign-exchange (Parivartana) yoga."

    # Gap fix (2026-07-05): traditional_domain tagging. Classically not every
    # detected yoga is primarily about CAREER — Vimala Yoga (12th lord in the
    # 12th) is a moksha/detachment/reduced-expenditure yoga, not a direct
    # career-gain yoga, yet the pre-fix explanation text below flatly asserted
    # "career gain" for it. This registry records each yoga's traditional
    # domain so the qualifier loop right after _NAMED_YOGA_EXPLANATIONS can
    # append a hedge whenever a yoga is being cited in a CAREER report but its
    # own classical domain is something else (finance/moksha/health/general).
    _NAMED_YOGA_EXPLANATIONS = {
        "Gajakesari": (
            "Jupiter is angular (kendra) from the Moon — a classical yoga for wisdom, "
            "reputation, and steady public standing; supports career credibility and "
            "long-term professional respect rather than sudden events."
        ),
        "Budha_Aditya": (
            "Mercury and the Sun are conjunct (within the same house) — the intelligence/"
            "administrative-ability yoga; supports analytical, communication-heavy, or "
            "administrative career roles, and articulate self-presentation."
        ),
        "Ruchaka":  "Mars is exalted/own-sign in a kendra — a Panch Mahapurusha yoga for courage, technical mastery, and decisive execution ability.",
        "Bhadra":   "Mercury is exalted/own-sign in a kendra — a Panch Mahapurusha yoga for sharp analytical intellect and communication skill.",
        "Hamsa":    "Jupiter is exalted/own-sign in a kendra — a Panch Mahapurusha yoga for wisdom, ethics, and advisory/teaching authority.",
        "Malavya":  "Venus is exalted/own-sign in a kendra — a Panch Mahapurusha yoga for creative, aesthetic, or finance-related career success.",
        "Sasha":    "Saturn is exalted/own-sign in a kendra — a Panch Mahapurusha yoga for disciplined, structural, long-endurance career authority.",
        "Rajayoga": "A trikona (1/5/9) lord and a kendra (1/4/7/10) lord are conjoined or mutually connected — a classical royal/status-elevation yoga for career authority.",
        "Dhana_Yoga": "The 2nd (wealth) and 11th (gains) lords are connected — a classical wealth-accumulation yoga supporting income growth.",
        "ChandraMangala": "Moon and Mars are conjunct or mutually aspecting — a wealth/enterprise yoga associated with business drive and material ambition.",
        "Amala": "A benefic (Jupiter/Venus/Mercury) occupies the 10th house from Lagna or Moon, unafflicted — the 'spotless career' yoga for an unblemished, honourable professional reputation.",
        "Harsha_VRY": "Viparita Raja Yoga (Harsha): the 6th lord sits in a dusthana (6/8/12) — reversal-yoga that turns apparent adversity (conflict/service pressure) into career gain.",
        "Sarala_VRY": "Viparita Raja Yoga (Sarala): the 8th lord sits in a dusthana (6/8/12) — reversal-yoga that turns apparent adversity (crisis/transformation) into career gain.",
        "Vimala_VRY": "Viparita Raja Yoga (Vimala): the 12th lord sits in a dusthana (6/8/12) — reversal-yoga classically read as reduced loss/expenditure and a capacity to convert isolation into detachment-based clarity, rather than a direct career-gain signal.",
    }
    for _prefix, _explanation in _NAMED_YOGA_EXPLANATIONS.items():
        if tag == _prefix or tag.startswith(_prefix + "_"):
            return _domain_hedge(tag, _explanation)
    return f"{tag.replace('_', ' ')} — a detected classical yoga influencing this period."


def _explain_active_yogas(tags: list) -> dict:
    """{tag: explanation} for every tag in `tags` — used by both the HTML
    tooltip and the LLM roadmap context so yoga names are never shown bare."""
    return {t: _explain_yoga_tag(t) for t in (tags or [])}


# --- Dusthana placement flag logic (extracted from _planet_strength_panel) ---

DUSTHANA_HOUSES = {6, 8, 12}
DUSTHANA_NOTE = {
    6:  "6th (service/conflict)",
    8:  "8th (crisis/transformation)",
    12: "12th (loss/withdrawal)",
}


def compute_dusthana_flags(eff_strengths: Dict[str, float],
                            planet_house: Optional[Dict[str, int]] = None,
                            strength_threshold: float = 1.2) -> Dict[str, Dict[str, Any]]:
    """For each planet whose effective strength is >= strength_threshold AND
    whose natal house placement is a dusthana (6th/8th/12th from Lagna),
    return a flag describing the qualifying placement.

    Extracted (behavior-preserving) from the dusthana-badge logic that was
    previously computed inline inside jyotish/web_report.py's
    _planet_strength_panel(). Classical significance: a planet strong by
    dignity/shadbala but placed in a dusthana expresses that strength through
    loss/withdrawal (12th), conflict/service (6th), or crisis/transformation
    (8th) rather than straightforward gain.

    Returns {planet: {"house": int, "note": str}} for only the planets that
    qualify — never fabricates a flag for planets missing house/strength data.
    """
    eff_strengths = eff_strengths or {}
    houses = planet_house or {}
    flags: Dict[str, Dict[str, Any]] = {}
    for planet, strength in eff_strengths.items():
        if strength is None:
            continue
        house = houses.get(planet, 0)
        if strength >= strength_threshold and house in DUSTHANA_HOUSES:
            flags[planet] = {
                "house": house,
                "note": DUSTHANA_NOTE.get(house, f"{house}th"),
            }
    return flags

