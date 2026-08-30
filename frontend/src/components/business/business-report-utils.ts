import type { BusinessKpi, BusinessPredictionResponse } from "@/lib/pyjhora/types";

export type ViewMode = "profile" | "astrologer";

export const GLOSSARY: Array<[string, string]> = [
  [
    "Lagna (Ascendant)",
    "The sign rising on the eastern horizon at birth. It anchors the entire chart — every house is counted from it.",
  ],
  [
    "House (Bhava)",
    "One of 12 divisions governing life domains — e.g. 2nd is wealth, 7th partnership/trade, 10th career/status.",
  ],
  [
    "House Lord",
    "The planet ruling the sign in a given house. A house's strength is read largely through its lord's placement and dignity.",
  ],
  [
    "Kendra / Trikona / Dusthana",
    "Kendras (1/4/7/10) are pillars of strength. Trikonas (1/5/9) are fortune. Dusthanas (6/8/12) are struggle/loss.",
  ],
  [
    "Dignity",
    "How empowered a planet is in its sign — from Exalted (strongest) to Debilitated (weakest).",
  ],
  [
    "Yoga",
    "A named planetary combination classical texts link to a specific outcome, e.g. Raja Yoga or Dhana Yoga.",
  ],
  [
    "Dasha (Mahadasha / Antardasha)",
    "Planetary periods dividing a lifetime — used here to flag favorable and cautionary business windows.",
  ],
  [
    "Varga (D9 / D10 / D24 / D60)",
    "Divisional charts for finer confirmation: D9 durability, D10 career execution, D24 competency, D60 reliability.",
  ],
  [
    "KP Sub-Lord",
    "House-cusp refinement used when the chart's house system is confirmed Placidus.",
  ],
  [
    "Jaimini Karakas",
    "Atmakaraka and Amatyakaraka — alternate career-direction evidence based on planetary degree order.",
  ],
  [
    "Nakshatra",
    "One of 27 lunar constellations — used for finer business-aptitude and timing evidence.",
  ],
  [
    "Retrograde",
    "Apparent backward motion — classically read as internalized or delayed expression of significations.",
  ],
  [
    "Rahu / Ketu",
    "Lunar nodes associated with unconventional pursuits (Rahu) and detachment/research depth (Ketu).",
  ],
];

export const PROFILE_TABS = [
  { id: "at-a-glance", label: "At a Glance" },
  { id: "recommendation", label: "Summary" },
  { id: "financial", label: "Financial Readiness" },
  { id: "transition", label: "Transition Timing" },
  { id: "scores", label: "Your Scores" },
  { id: "reconciliation", label: "Signal Reconciliation" },
  { id: "sectors", label: "Best-Fit Sectors" },
  { id: "windows", label: "Favorable Periods" },
  { id: "appendix", label: "Technical Appendix" },
] as const;

export const ASTROLOGER_TABS = [
  { id: "at-a-glance", label: "At a Glance" },
  { id: "recommendation", label: "Recommendation" },
  { id: "scores", label: "Promise Fields" },
  { id: "forecast", label: "Forecast Window" },
  { id: "significators", label: "Significators" },
  { id: "sectors", label: "Sectors" },
  { id: "windows", label: "Timed Windows" },
  { id: "method", label: "Method Status" },
  { id: "appendix", label: "Technical Appendix" },
] as const;

export type TabId = (typeof PROFILE_TABS)[number]["id"] | (typeof ASTROLOGER_TABS)[number]["id"];

export function fmtPct(v?: number | null): string {
  return v == null || Number.isNaN(v) ? "—" : `${Number(v).toFixed(1)}%`;
}

export function verdictLabel(cat?: string): string {
  const map: Record<string, string> = {
    HYBRID_LEANING_JOB: "Hybrid, Leaning Employment",
    HYBRID_LEANING_BUSINESS: "Hybrid, Leaning Business",
    STRONG_BUSINESS: "Strong Business Case",
    STRONG_JOB: "Strong Employment Case",
    SLIGHT_BUSINESS_ADVANTAGE: "Slight Business Advantage",
    SLIGHT_JOB_ADVANTAGE: "Slight Employment Advantage",
  };
  if (!cat) return "—";
  return map[cat] ?? cat.replace(/_/g, " ");
}

export function verdictClass(cat?: string): "yes" | "no" | "hybrid" {
  const c = (cat ?? "").toUpperCase();
  if (c.includes("HYBRID") || c.includes("SLIGHT")) return "hybrid";
  if (c.includes("JOB") && !c.includes("BUSINESS")) return "no";
  if (c.includes("BUSINESS")) return "yes";
  return "hybrid";
}

export function badgeClass(label?: string): string {
  const u = (label ?? "").toUpperCase().replace(/\s+/g, "_");
  if (u.includes("STRONG_FAVORABLE") || u === "HIGH" || u === "EXCELLENT") return "STRONG_FAVORABLE";
  if (u.includes("FAVORABLE") || u === "MODERATE" || u === "GOOD") return "FAVORABLE";
  if (u.includes("CAUTION") || u.includes("RISK")) return "CAUTION";
  if (u.includes("MIXED") || u === "LOW" || u === "AVERAGE") return "MIXED";
  return "MIXED";
}

export function tierFromScore(v?: number | null): BusinessKpi["tier"] {
  if (v == null) return "unknown";
  if (v >= 70) return "strong";
  if (v >= 50) return "moderate";
  return "weak";
}

export function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

export function asArray<T = unknown>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

export function asString(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

export function getSectors(data: BusinessPredictionResponse) {
  const diversified = asRecord(data.prediction.diversified_sectors);
  const fromDiversified = asArray<Record<string, unknown>>(diversified.diversified_top_sectors);
  if (fromDiversified.length) {
    return fromDiversified.map((s, i) => ({
      rank: Number(s.rank ?? i + 1),
      label: asString(s.label ?? s.sector),
      score: typeof s.score === "number" ? s.score : null,
      match_confidence: asString(s.match_confidence),
      capital_intensity: asString(s.capital_intensity),
      archetype_family: asString(s.archetype_family),
    }));
  }
  return data.report.sectors;
}

export function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}
