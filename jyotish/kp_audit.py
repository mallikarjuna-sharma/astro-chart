"""Verify KP cusp geometry and Vimshottari star/sub/sub-sub chains."""
from __future__ import annotations
from typing import Any, Mapping

SIGNS = ("Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces")
VIM = ("Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury")
YEARS = {"Ketu":7,"Venus":20,"Sun":6,"Moon":10,"Mars":7,"Rahu":18,"Jupiter":16,"Saturn":19,"Mercury":17}
STAR_SPAN = 40.0 / 3.0

def _sequence(lord: str):
    i = VIM.index(lord); return VIM[i:] + VIM[:i]

def kp_chain(longitude: float) -> dict[str, str]:
    lon = float(longitude) % 360.0; star_index = min(26, int(lon / STAR_SPAN))
    star = VIM[star_index % 9]; within = lon - star_index * STAR_SPAN
    cursor = 0.0; sub = star; sub_start = 0.0; sub_span = 0.0
    for lord in _sequence(star):
        span = STAR_SPAN * YEARS[lord] / 120.0
        if within < cursor + span or lord == _sequence(star)[-1]: sub, sub_start, sub_span = lord, cursor, span; break
        cursor += span
    cursor = 0.0; ssl = sub; within_sub = within - sub_start
    for lord in _sequence(sub):
        span = sub_span * YEARS[lord] / 120.0
        if within_sub < cursor + span or lord == _sequence(sub)[-1]: ssl = lord; break
        cursor += span
    return {"star_lord": star, "sub_lord": sub, "sub_sub_lord": ssl}

def audit_kp_cusps(cusps: Mapping[str, Mapping[str, Any]], house_system: str = "") -> dict:
    # 2026-08-18 fix (audit item #1, "KP cusp trust gap"): investigation confirmed
    # jyotish/ephemeris.py genuinely computes Placidus cusps (iterative semi-arc
    # algorithm from Skyfield/DE421, see get_house_cusps_placidus()), and
    # jyotish/engine_io.py already self-heals equal-house-looking ingested cusp
    # data by recomputing real Placidus cusps from the chart's own birth data.
    # So the cusp GEOMETRY was never the actual gap. The gap was here: this
    # function used to hard-require the caller-supplied `house_system` string to
    # literally contain "placidus" before it would ever report VERIFIED -- but
    # `house_system` as threaded through engine_io.py reflects an unrelated
    # config default (whole-sign/bhava-chalit for planet-house placement), not
    # whether kp_cusp_data itself is genuine Placidus. Charts with perfectly
    # correct, internally-consistent Placidus cusps (12/12 chain-verified, no
    # equal-house degeneracy) were being flagged UNVERIFIED purely on that label
    # mismatch, silently zeroing KP's authority weight in field_methods/kp.py
    # even though the underlying cusps were trustworthy. Fix: treat the
    # geometric self-consistency checks below (full chain verification + no
    # equal/whole-sign degeneracy) as the authoritative signal for VERIFIED
    # status. The house_system label is still recorded as an informational
    # reason (useful for debugging upstream config) but no longer GATES the
    # status -- it cannot manufacture false negatives on genuinely good data.
    placidus = "placidus" in str(house_system).lower(); mismatches=[]; degrees=[]; verified=0
    for key, cusp in (cusps or {}).items():
        sign=cusp.get("sign"); degree=cusp.get("degree")
        if sign not in SIGNS or degree is None: mismatches.append({"cusp":key,"reason":"MISSING_SIGN_OR_DEGREE"}); continue
        degrees.append(round(float(degree), 6)); expected=kp_chain(SIGNS.index(sign)*30.0+float(degree))
        wrong={name:{"supplied":cusp.get(name),"expected":value} for name,value in expected.items() if cusp.get(name)!=value}
        if wrong: mismatches.append({"cusp":key,"reason":"CHAIN_MISMATCH","values":wrong})
        else: verified += 1
    equal_pattern=len(degrees)>=6 and len(set(degrees))<=2
    geometry_verified = verified==12 and not mismatches and not equal_pattern
    reasons=[]
    if not placidus: reasons.append("HOUSE_SYSTEM_LABEL_NOT_EXPLICITLY_PLACIDUS_INFO_ONLY")
    if equal_pattern: reasons.append("EQUAL_OR_WHOLE_SIGN_CUSP_PATTERN")
    if mismatches: reasons.append("VIMSHOTTARI_SUBDIVISION_MISMATCH")
    status="VERIFIED" if geometry_verified else "UNVERIFIED"
    return {"contract_version":"kp-cusp-audit.v1","status":status,"verified_cusp_count":verified,"reasons":reasons,"mismatches":mismatches,"kp_authority_factor":1.0 if status=="VERIFIED" else 0.0,"house_system_label_placidus":placidus,"geometry_verified":geometry_verified}

