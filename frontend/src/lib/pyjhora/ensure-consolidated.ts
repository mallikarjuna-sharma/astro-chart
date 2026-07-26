import { pyjhora } from "./client";
import type { BirthInput, CareerContextInput, StudentContext } from "./types";

const EXPECTED_DIVISIONAL_KEYS = [
  "D1_rashi",
  "D2_hora",
  "D3_drekkana",
  "D4_chaturthamsa",
  "D5_panchamsa",
  "D6_shashthamsa",
  "D7_saptamsa",
  "D8_ashtamsa",
  "D9_navamsha",
  "D10_dashamsha",
  "D16_shodasamsa",
  "D24_siddhamsam",
  "D60_shashtiamsam",
  "D81_ashtottariamsa",
] as const;

/** True when consolidated JSON has D1 planets under pyhora_calculations.divisional_charts. */
export function consolidatedHasEngineData(
  consolidated: Record<string, unknown> | null | undefined,
): boolean {
  if (!consolidated) return false;
  const pyh = consolidated.pyhora_calculations as Record<string, unknown> | undefined;
  if (!pyh) return false;
  const div = pyh.divisional_charts as Record<string, unknown> | undefined;
  const d1 = div?.D1_rashi as Record<string, unknown> | undefined;
  const planets = (d1?.planets ?? pyh.planets_d1) as Record<string, unknown> | undefined;
  return !!planets && typeof planets === "object" && Object.keys(planets).length > 0;
}

/** Re-fetch when legacy flat D1 fields exist or divisional charts are incomplete. */
export function consolidatedNeedsRefresh(
  consolidated: Record<string, unknown> | null | undefined,
): boolean {
  if (!consolidatedHasEngineData(consolidated)) return true;
  const pyh = consolidated!.pyhora_calculations as Record<string, unknown>;
  if (pyh.planets_d1 || pyh.d1_lagna || pyh.d1_lagna_degree) return true;
  const div = (pyh.divisional_charts as Record<string, unknown> | undefined) ?? {};
  return EXPECTED_DIVISIONAL_KEYS.some((key) => !div[key]);
}

/**
 * Return consolidated JSON suitable for education/career engines.
 * Re-fetches via /api/consolidated when the saved copy omitted pyhora_calculations.
 */
export async function ensureConsolidatedForEngine(
  birthInput: BirthInput,
  studentContext: StudentContext | undefined,
  consolidated: Record<string, unknown> | null | undefined,
  careerContext?: CareerContextInput | null,
  displayName?: string | null,
): Promise<Record<string, unknown>> {
  let out: Record<string, unknown>;
  if (!consolidatedNeedsRefresh(consolidated)) {
    out = { ...consolidated! };
  } else {
    out = await pyjhora.consolidated({
      birth_input: birthInput,
      student_context: studentContext ?? null,
    });
  }
  const name = displayName?.trim();
  if (name) {
    const sc = (out.student_context as Record<string, unknown> | undefined) ?? {};
    out = {
      ...out,
      profile_name: name,
      user_info: { ...((out.user_info as Record<string, unknown> | undefined) ?? {}), display_name: name },
      student_context: { ...sc, student_name: name, name },
    };
  }
  if (careerContext && Object.keys(careerContext).length > 0) {
    out = { ...out, career_context: careerContext };
  }
  return out;
}
