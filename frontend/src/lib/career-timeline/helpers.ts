import type { CareerTimelineBlock } from "@/lib/pyjhora/types";

const CAREER_WEATHER: Array<[number, number, string, string]> = [
  [0.7, 1, "☀️", "Strong Tailwind"],
  [0.7, 0, "🌤️", "Bright, Steady"],
  [0.55, 1, "🌤️", "Favorable Winds"],
  [0.55, 0, "⛅", "Steady, Mixed"],
  [0.4, -1, "🌥️", "Cloudy, Cautious"],
  [0.4, 0, "⛅", "Steady, Mixed"],
  [0.0, -1, "🌧️", "Headwinds"],
];

const EVENT_TONE: Record<string, "growth" | "transition" | "risk" | "steady"> = {
  PROMOTION: "growth",
  LEADERSHIP_EXPANSION: "growth",
  BREAKTHROUGH: "growth",
  INCOME_INFLECTION: "growth",
  SALARY_HIKE: "growth",
  GROWTH: "growth",
  JOB_CHANGE: "transition",
  FOREIGN_POSTING: "transition",
  TRANSITION: "transition",
  LATERAL_MOVE: "transition",
  RISK_PERIOD: "risk",
  SANDHI_PERIOD: "risk",
  STAGNATION: "risk",
};

const PARENT_GUIDANCE: Record<
  "growth" | "transition" | "risk" | "steady",
  [string, string]
> = {
  growth: [
    "A supportive window",
    "The signals for this period point toward growth or recognition. The best support you can offer is encouragement and patience with the extra hours or focus this often requires — there is nothing here that needs intervention or worry.",
  ],
  transition: [
    "A change in progress, not a crisis",
    "This period favors a considered change — a new role, a shift in direction, or a move that expands options. Change can feel unsettling from the outside; the most useful support is patience during the decision process rather than pressure to decide quickly.",
  ],
  risk: [
    "A period to stay steady, not alarmed",
    "This window carries some instability signals. That does not mean something bad will happen — it means added patience and emotional steadiness help. Avoid impulsive decisions driven by fear.",
  ],
  steady: [
    "A consolidating period",
    "Nothing dramatic is indicated this period — it favors steady, reliable effort over big decisions. No special support is needed beyond normal encouragement.",
  ],
};

export function fmtDate(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function yearLabel(start?: string, end?: string): string {
  const ys = (start ?? "").slice(0, 4);
  const ye = (end ?? "").slice(0, 4);
  if (!ys) return "";
  if (!ye || ys === ye) return ys;
  return `${ys}–${ye}`;
}

export function careerWeather(score: number, netSignal = ""): { emoji: string; label: string } {
  const netFavor = { Favorable: 1, Mixed: 0, Challenging: -1 }[netSignal] ?? 0;
  const combined = score + netFavor * 0.06;
  for (const [minScore, minFavor, emoji, label] of CAREER_WEATHER) {
    if (combined >= minScore && netFavor >= minFavor) return { emoji, label };
  }
  return { emoji: "⛅", label: "Steady, Mixed" };
}

export function strengthColor(strength: string): string {
  const key = strength.toLowerCase().split(" unless")[0]?.split(",")[0]?.trim() ?? "";
  const map: Record<string, string> = {
    high: "var(--success)",
    "medium-high": "var(--info)",
    medium: "var(--warn)",
    "medium-low": "var(--warn)",
    low: "var(--muted-foreground)",
  };
  return map[key] ?? "var(--muted-foreground)";
}

export function periodBadge(block: CareerTimelineBlock): string {
  if (block.is_current) return "Current";
  if (block.is_past) return "Past";
  return "Upcoming";
}

export function familyGuidance(eventType?: string) {
  const key = (eventType ?? "").toUpperCase().replace(/\s+/g, "_").replace(/^FORECAST_/, "");
  const tone = EVENT_TONE[key] ?? "steady";
  const [headline, body] = PARENT_GUIDANCE[tone];
  return { headline, body, tone };
}

export function contradictionCheck(block: CareerTimelineBlock) {
  const sub = (block.sub_scores ?? {}) as Record<string, unknown>;
  const supporting: string[] = [];
  const blocking: string[] = [];

  const yogaBonus = Number(sub.yoga_bonus ?? 0);
  if (yogaBonus > 0) {
    const tags = (sub.active_yogas as string[] | undefined) ?? [];
    supporting.push(
      tags.length
        ? `Active yoga(s): ${tags.join(", ")}`
        : `Yoga bonus (+${yogaBonus.toFixed(2)})`,
    );
  }
  const d9 = Number(sub.d9_modifier ?? 0);
  if (d9 > 0.005) supporting.push(`D9 dignity supportive (+${d9.toFixed(2)})`);
  else if (d9 < -0.005) blocking.push(`D9 dignity weak (${d9.toFixed(2)})`);

  const chandra = Number(sub.chandra_lagna_bonus ?? 0);
  if (chandra > 0) supporting.push(`Chandra Lagna support (+${chandra.toFixed(2)})`);

  const gandanta = Number(sub.gandanta_penalty ?? 0);
  if (gandanta > 0) blocking.push(`Gandanta penalty (-${gandanta.toFixed(2)})`);

  if (sub.is_sandhi) blocking.push("Dasha Sandhi (junction) — volatility flag");
  if (block.macro_headwinds) blocking.push("Macro-economic headwinds active");

  const d10Struct = Number(sub.d10_structural_score ?? 0);
  if (d10Struct >= 0.55) supporting.push(`D10 structurally strong (${d10Struct.toFixed(2)})`);
  else if (d10Struct > 0 && d10Struct < 0.3) blocking.push(`D10 structurally weak (${d10Struct.toFixed(2)})`);

  const net =
    supporting.length > blocking.length
      ? "Favorable"
      : blocking.length > supporting.length
        ? "Challenging"
        : "Mixed";

  return { supporting, blocking, net };
}

export function scoreMatrix(block: CareerTimelineBlock) {
  const sub = (block.sub_scores ?? {}) as Record<string, number | undefined>;
  const dims: Array<[string, number | undefined]> = [
    ["Career Score", block.career_score],
    ["Promotion", sub.promotion_score],
    ["Job Change", sub.job_change_score],
    ["Job Loss Risk", sub.risk_score],
    ["Income", sub.income_score],
    ["Foreign", sub.foreign_score],
    ["Protection", sub.stability_score],
    ["Visibility", sub.visibility_score],
  ];
  return dims.filter(([, v]) => v != null) as Array<[string, number]>;
}

export function d10Verdict(block: CareerTimelineBlock) {
  const sub = (block.sub_scores ?? {}) as Record<string, unknown>;
  const align = Number(sub.d10_dashamsha_alignment ?? sub.d10_alignment ?? NaN);
  const full = Number(sub.d10_full_score ?? NaN);
  const score = Number.isFinite(full) ? full : align;
  if (!Number.isFinite(score)) return null;

  let verdict: string;
  let color: string;
  let manifest: string;
  if (score >= 0.55) {
    verdict = "Strong";
    color = "var(--success)";
    manifest = "D10 supports a clean, comparatively direct manifestation of the D1 promise this period.";
  } else if (score >= 0.3) {
    verdict = "Moderate";
    color = "var(--warn)";
    manifest = "D10 gives partial support — the D1 signal can manifest but may need extra effort or a longer runway to land.";
  } else {
    verdict = "Weak";
    color = "var(--danger)";
    manifest =
      "D10 does not strongly support an easy/clean result — treat the D1 promise as needing more effort or a longer runway to land.";
  }
  const theme = String(sub.d10_lagna_career_theme ?? "");
  if (theme) manifest += ` D10 Lagna theme: ${theme}`;

  const occupancy = `D10 alignment score of ${score.toFixed(2)} reflects how directly the running ${block.md_lord}-${block.ad_lord} period ties into the D10 10th/11th house structure this period.`;

  return { verdict, color, manifest, score, occupancy };
}

export function d10Subscores(block: CareerTimelineBlock) {
  const sub = (block.sub_scores ?? {}) as Record<string, number | undefined>;
  const labels: Array<[string, string]> = [
    ["d10_title_support", "D10 Title Support"],
    ["d10_global_delivery_support", "D10 Global/Delivery Support"],
    ["d10_invisible_authority_support", "D10 Invisible Authority Support"],
    ["d10_clean_promotion_support", "D10 Clean-Promotion Support"],
  ];
  return labels
    .map(([key, label]) => (sub[key] != null ? { label, value: sub[key]! } : null))
    .filter(Boolean) as Array<{ label: string; value: number }>;
}

export function asHtmlString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function formatConfidence(confidence: CareerTimelineBlock["confidence"]): string {
  if (!confidence) return "";
  if (typeof confidence === "string") return confidence;
  if (typeof confidence === "object") {
    const c = confidence as { label?: string; tier?: string; score?: number };
    const label = c.label || c.tier?.replace(/_/g, " ");
    if (label && typeof c.score === "number") return `${label} (${c.score})`;
    if (label) return label;
  }
  return String(confidence);
}
