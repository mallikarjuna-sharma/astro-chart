import type { EducationAnalysisResponse } from "@/lib/pyjhora/types";

/** Ages 15, 16, 17 default to PUC; all others default to UG. */
export function defaultEducationTab(currentAge: number | undefined | null): "puc" | "ug" {
  if (typeof currentAge !== "number" || Number.isNaN(currentAge)) return "ug";
  const floor = Math.floor(currentAge);
  if (floor === 15 || floor === 16 || floor === 17) return "puc";
  return "ug";
}

export function educationTabFromResponse(
  data: EducationAnalysisResponse | { default_tab?: string | null } | null | undefined,
  currentAge?: number | null,
): "puc" | "ug" {
  const tab = data?.default_tab;
  if (tab === "puc" || tab === "ug") return tab;
  return defaultEducationTab(currentAge ?? undefined);
}
