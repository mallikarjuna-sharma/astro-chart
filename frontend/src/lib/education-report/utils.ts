import type { EducationAnalysisResponse, EducationFieldResult } from "@/lib/pyjhora/types";

export const DOMAIN_ICONS: Record<string, string> = {
  engineering: "⚙️",
  technology: "💻",
  science: "🔬",
  medicine: "🩺",
  arts: "🎨",
  law: "⚖️",
  interdisciplinary: "🌐",
  humanities: "📚",
  commerce: "💼",
  public: "🏛️",
  education: "🎓",
};

export const DOMAIN_COLORS: Record<string, string> = {
  engineering: "#1565c0",
  technology: "#0277bd",
  science: "#2e7d32",
  medicine: "#b71c1c",
  arts: "#6a1b9a",
  law: "#e65100",
  interdisciplinary: "#37474f",
  humanities: "#4a148c",
  commerce: "#1b5e20",
  public: "#37474f",
  education: "#4e342e",
};

const EXAM_LABELS: Record<string, string> = {
  JEE_Advanced: "JEE Advanced",
  JEE_Main: "JEE Main",
  NEET_UG: "NEET UG",
  CLAT: "CLAT",
  CUET: "CUET",
  BITSAT: "BITSAT",
  GATE: "GATE (PG)",
  CAT: "CAT",
  AILET: "AILET",
  LSAT_India: "LSAT India",
  State_Art_Entrance: "State Art Entrance",
  Audition_Based: "Audition / Portfolio",
  BHU_UET: "BHU UET",
  State_Entrance: "State Entrance",
  NATA: "NATA",
  NID_DAT: "NID DAT",
  UCEED: "UCEED",
  CEED: "CEED (PG)",
};

export function domainIcon(domain: string): string {
  return DOMAIN_ICONS[domain] ?? "🌐";
}

export function domainColor(domain: string): string {
  return DOMAIN_COLORS[domain] ?? "#546e7a";
}

export function formatExam(exam: string): string {
  return EXAM_LABELS[exam] ?? exam.replace(/_/g, " ");
}

export function scorePct(score: number): number {
  return Math.max(5, Math.min(100, Math.round(((score - 100) / 75) * 100)));
}

export function scoreLabel(score: number, top: number): string {
  if (score >= top - 10) return "Excellent Match";
  if (score >= top - 20) return "Strong Match";
  if (score >= top - 35) return "Good Match";
  return "Moderate Match";
}

export function isStrongMatch(score: number, top: number): boolean {
  return score >= top - 20;
}

export interface ReportLayout {
  sorted: EducationFieldResult[];
  topScore: number;
  matchFields: EducationFieldResult[];
  soulField: EducationFieldResult | null;
  shownIds: Set<string>;
}

export function buildReportLayout(data: EducationAnalysisResponse): ReportLayout {
  const sorted = [...data.fields].sort(
    (a, b) => b.final_score - a.final_score || a.field_id.localeCompare(b.field_id),
  );
  const topScore = sorted[0]?.final_score ?? 175;
  const ak = data.student.atmakaraka ?? "";

  const soulFromLlm = sorted.filter((r) => r.llm_group === "soul");
  const matchPool = sorted.filter((r) => r.llm_group !== "soul");

  const llmTop5 = matchPool
    .filter((r) => (r.llm_rank ?? 99) >= 1 && (r.llm_rank ?? 99) <= 5)
    .sort((a, b) => (a.llm_rank ?? 99) - (b.llm_rank ?? 99));

  let matchFields: EducationFieldResult[];
  if (llmTop5.length >= 3) {
    matchFields = llmTop5.slice(0, 5);
  } else {
    const strong = matchPool.filter((r) => isStrongMatch(r.final_score, topScore)).slice(0, 5);
    matchFields = strong.length ? strong : matchPool.slice(0, 3);
  }

  const shownIds = new Set(matchFields.map((r) => r.field_id));
  let soulField = soulFromLlm[0] ?? pickSoulField(sorted, shownIds, ak);
  if (soulField) shownIds.add(soulField.field_id);

  return { sorted, topScore, matchFields, soulField, shownIds };
}

const AK_SOUL: Record<string, string[]> = {
  Moon: ["arts", "medicine", "humanities"],
  Venus: ["arts", "humanities"],
  Jupiter: ["humanities", "law", "medicine"],
  Mercury: ["technology", "science"],
  Saturn: ["engineering", "science", "interdisciplinary"],
  Sun: ["law", "interdisciplinary"],
  Mars: ["engineering", "science"],
  Rahu: ["technology", "interdisciplinary"],
  Ketu: ["science", "interdisciplinary"],
};

function pickSoulField(
  results: EducationFieldResult[],
  shownIds: Set<string>,
  ak: string,
): EducationFieldResult | null {
  const preferred = AK_SOUL[ak] ?? ["interdisciplinary", "arts"];
  for (const domain of preferred) {
    const hit = results.find((r) => !shownIds.has(r.field_id) && r.domain === domain);
    if (hit) return hit;
  }
  return results.find((r) => !shownIds.has(r.field_id)) ?? null;
}
