import type { EducationAnalysisResponse } from "@/lib/pyjhora/types";
import type { BirthInput } from "@/lib/pyjhora/types";

const PUC_AGE_FLOORS = new Set([15, 16, 17]);
const PUC_MAX_AGE_EXCLUSIVE = 18;

/** True when the chart is in the PUC stream-analysis age window. */
export function isPucEligible(currentAge: number | undefined | null): boolean {
  if (typeof currentAge !== "number" || Number.isNaN(currentAge) || currentAge <= 0) return false;
  const floor = Math.floor(currentAge);
  if (PUC_AGE_FLOORS.has(floor)) return true;
  return currentAge < PUC_MAX_AGE_EXCLUSIVE;
}

/** Rough age in whole years from birth date (matches server eligibility closely enough for UI gating). */
export function approxAgeFromBirthInput(birth: BirthInput): number {
  const born = new Date(birth.year, birth.month - 1, birth.day);
  const now = new Date();
  let age = now.getFullYear() - born.getFullYear();
  const monthDelta = now.getMonth() - born.getMonth();
  if (monthDelta < 0 || (monthDelta === 0 && now.getDate() < born.getDate())) age -= 1;
  return age;
}

export function pucAgeErrorMessage(currentAge: number): string {
  return (
    "PUC stream analysis is only available for students aged 15–17. " +
    `This profile is ${Math.round(currentAge)} years old — use the UG career analysis instead.`
  );
}

/** Ages 15, 16, 17 default to PUC; all others default to UG. */
export function defaultEducationTab(currentAge: number | undefined | null): "puc" | "ug" {
  if (typeof currentAge !== "number" || Number.isNaN(currentAge)) return "ug";
  return isPucEligible(currentAge) ? "puc" : "ug";
}

export function educationTabFromResponse(
  data: EducationAnalysisResponse | { default_tab?: string | null } | null | undefined,
  currentAge?: number | null,
): "puc" | "ug" {
  const tab = data?.default_tab;
  if (tab === "puc" || tab === "ug") return tab;
  return defaultEducationTab(currentAge ?? undefined);
}
