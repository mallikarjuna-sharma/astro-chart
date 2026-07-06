import { pyjhora } from "./client";
import type { BirthInput, CareerContextInput, StudentContext } from "./types";

/** True when consolidated JSON has planets_d1 under pyhora_calculations (engine requirement). */
export function consolidatedHasEngineData(
  consolidated: Record<string, unknown> | null | undefined,
): boolean {
  if (!consolidated) return false;
  const pyh = consolidated.pyhora_calculations as Record<string, unknown> | undefined;
  const planets = pyh?.planets_d1;
  return !!planets && typeof planets === "object" && Object.keys(planets).length > 0;
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
): Promise<Record<string, unknown>> {
  let out: Record<string, unknown>;
  if (consolidatedHasEngineData(consolidated)) {
    out = { ...consolidated! };
  } else {
    out = await pyjhora.consolidated({
      birth_input: birthInput,
      student_context: studentContext ?? null,
    });
  }
  if (careerContext && Object.keys(careerContext).length > 0) {
    out = { ...out, career_context: careerContext };
  }
  return out;
}
