import type {
  EducationFieldRegistry,
  EducationFieldResult,
  InstitutionalTier,
} from "@/lib/pyjhora/types";

const TIER_ALLOW: Record<string, Set<string>> = {
  Tier1_Premier: new Set(["IIT", "IISER", "ISI", "BITS", "central_universities", "liberal_arts_private"]),
  Tier1_Foreign: new Set(["IIT", "IISER", "ISI", "BITS", "central_universities"]),
  Tier2_Technical: new Set(["NIT", "BITS", "IIIT", "deemed_private", "state_universities"]),
  Tier2_Professional: new Set([
    "central_universities",
    "liberal_arts_private",
    "deemed_private",
    "state_universities",
    "BITS",
  ]),
};

const PREFIX_KEYS = new Set(["IIT", "NIT", "BITS", "IISER", "ISI"]);
const BOOL_LABEL: Record<string, string | null> = {
  IIIT: "IIITs",
  state_universities: "State Universities",
  deemed_private: "Deemed / Private",
  central_universities: null,
  liberal_arts_private: null,
};

export function parentReason(field: EducationFieldResult): string {
  return (
    field.parent_friendly_explanation?.trim() ||
    field.llm_parent_reason?.trim() ||
    `This field aligns well with your child's natural strengths in ${field.domain}.`
  );
}

export function astroReason(field: EducationFieldResult): string {
  return (
    field.astrological_reason?.trim() ||
    field.llm_astrological_reason?.trim() ||
    "Score driven by planetary affinity and domain-aptitude convergence."
  );
}

export function parseVerifiedFactors(raw: string | undefined): { positive: string[]; negative: string[] } {
  const parts = (raw ?? "")
    .split("|")
    .map((p) => p.trim())
    .filter(Boolean);
  return {
    positive: parts.filter((p) => p.includes(":+")).slice(0, 5),
    negative: parts.filter((p) => p.includes(":-")).slice(0, 2),
  };
}

export function institutionExamples(
  tier: InstitutionalTier | undefined,
  registry: EducationFieldRegistry | undefined,
): string[] {
  const tierKey = tier?.tier_key ?? "";
  const allowed = TIER_ALLOW[tierKey] ?? TIER_ALLOW.Tier2_Professional;
  const av = registry?.available_at ?? {};
  const out: string[] = [];

  for (const [key, val] of Object.entries(av)) {
    if (!allowed.has(key)) continue;
    if (val === false || val == null) continue;
    if (val === true) {
      const label = BOOL_LABEL[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      if (label) out.push(label);
    } else if (Array.isArray(val) && val.length) {
      if (val.join() === "All_IITs") {
        out.push("All IITs");
        continue;
      }
      if (val.join() === "All_NITs") {
        out.push("All NITs");
        continue;
      }
      const clean = val.slice(0, 3).map((v) => v.replace(`${key}_`, "").replace(/_/g, " "));
      if (PREFIX_KEYS.has(key)) {
        out.push(`${key} ${clean.join(" / ")}`);
      } else {
        out.push(clean.join(" / "));
      }
    }
    if (out.length >= 4) break;
  }

  if (out.length) return out.slice(0, 4);
  return (tier?.target_examples ?? []).slice(0, 4);
}

export function stageBoxClass(stage: string, recommended: boolean): string {
  if (stage === "UG") return "bg-success/12 text-success border-success/30";
  if (stage === "PG") return recommended ? "bg-info/12 text-info border-info/30" : "bg-muted text-muted-foreground border-border opacity-60";
  return recommended ? "bg-muted text-foreground border-border" : "bg-muted text-muted-foreground border-border opacity-60";
}

export function wealthBadgeClass(level: string | undefined): string {
  if (level === "High") return "bg-success/12 text-success border-success/30";
  if (level === "Medium") return "bg-warn/12 text-warn border-warn/30";
  return "bg-danger/12 text-danger border-danger/30";
}

export function geoBadgeClass(label: string | undefined): string {
  const l = (label ?? "").toLowerCase();
  if (l.includes("international") || l.includes("foreign")) return "bg-info/12 text-info border-info/30";
  if (l.includes("hybrid")) return "bg-royal/12 text-royal border-royal/30";
  return "bg-success/12 text-success border-success/30";
}

export function burnoutBadgeClass(level: string | undefined): string {
  if (level === "High") return "bg-danger/12 text-danger border-danger/30";
  if (level === "Medium") return "bg-warn/12 text-warn border-warn/30";
  return "bg-success/12 text-success border-success/30";
}
