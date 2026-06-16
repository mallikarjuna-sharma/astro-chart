// Stub API client for JyotishAI.
// In production these calls would hit Swiss Ephemeris + AI services.
// Every function returns a Promise that resolves with mock data after a short delay.

import { toast } from "sonner";

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

async function stub<T>(name: string, payload: T, ms = 400): Promise<T> {
  // Centralized stub — useful for swapping with real fetch later.
  // eslint-disable-next-line no-console
  console.info("[stub-api]", name);
  await delay(ms);
  return payload;
}

export interface BirthData {
  fullName: string;
  date: string;
  time: string;
  place: string;
  latitude?: number;
  longitude?: number;
  ayanamsa: "KP" | "KN_Rao" | "Lahiri" | "Raman" | "True_Citra";
  uncertaintyMinutes: 0 | 5 | 10 | 15;
}

export interface PrashnaQuery {
  question: string;
  category: string;
  askedAt: string;
  place: string;
}

export const PLANETS = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"] as const;
export const SIGNS = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"] as const;

export const api = {
  // ---- Birth & charts ----
  saveBirthData: (data: BirthData) =>
    stub("saveBirthData", { id: "chart_" + Date.now(), ...data }),

  generateCharts: (chartIds: string[]) =>
    stub("generateCharts", { generated: chartIds, status: "ok" as const }),

  geocodePlace: (q: string) =>
    stub("geocodePlace", [
      { name: q + ", India", lat: 12.9716, lon: 77.5946, tz: "Asia/Kolkata" },
      { name: q + " (alt)", lat: 13.0827, lon: 80.2707, tz: "Asia/Kolkata" },
    ], 200),

  // ---- KP ----
  getKPSignificators: () =>
    stub("getKPSignificators", PLANETS.map((p, i) => ({
      planet: p,
      primaryHouses: [(i % 12) + 1, ((i + 3) % 12) + 1],
      secondaryHouses: [((i + 6) % 12) + 1],
      strength: ((i * 13) % 10) + 1,
    }))),

  getCuspSubLords: () =>
    stub("getCuspSubLords", Array.from({ length: 12 }, (_, i) => ({
      cusp: i + 1,
      longitude: (i * 30 + 7.21).toFixed(4),
      nakshatra: ["Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra","Punarvasu","Pushya","Ashlesha","Magha","P.Phalguni","U.Phalguni"][i],
      nakshatraLord: PLANETS[i % 9],
      subLord: PLANETS[(i + 2) % 9],
      subSubLord: PLANETS[(i + 4) % 9],
      signifiesHouses: [(i + 1) % 12 + 1, (i + 4) % 12 + 1],
    }))),

  getVimshottariDasha: () =>
    stub("getVimshottariDasha", [
      { maha: "Jupiter", antar: "Sun", from: "2024-03-01", to: "2024-12-18", careerScore: 8, classification: "Growth" as const },
      { maha: "Jupiter", antar: "Moon", from: "2024-12-18", to: "2026-04-17", careerScore: 6, classification: "Stable" as const },
      { maha: "Jupiter", antar: "Mars", from: "2026-04-17", to: "2027-03-23", careerScore: 7, classification: "Pivot" as const },
      { maha: "Saturn", antar: "Saturn", from: "2027-03-23", to: "2030-03-26", careerScore: 5, classification: "Challenging" as const },
      { maha: "Saturn", antar: "Mercury", from: "2030-03-26", to: "2032-12-04", careerScore: 9, classification: "Growth" as const },
    ]),

  getRulingPlanets: () =>
    stub("getRulingPlanets", {
      dayLord: "Sun", lagnaLord: "Mercury", lagnaSubLord: "Jupiter",
      moonNakshatraLord: "Venus", moonSubLord: "Mars", capturedAt: new Date().toISOString(),
    }, 150),

  // ---- KN Rao / Jaimini ----
  getCharaKarakas: () =>
    stub("getCharaKarakas", [
      { karaka: "Atmakaraka", planet: "Mercury", degree: 28.42 },
      { karaka: "Amatyakaraka", planet: "Jupiter", degree: 24.11 },
      { karaka: "Bhatrukaraka", planet: "Saturn", degree: 19.55 },
      { karaka: "Matrukaraka", planet: "Sun", degree: 14.30 },
      { karaka: "Putrakaraka", planet: "Mars", degree: 11.05 },
      { karaka: "Gnatikaraka", planet: "Moon", degree: 7.49 },
      { karaka: "Darakaraka", planet: "Venus", degree: 3.12 },
    ]),

  getKarakamsa: () =>
    stub("getKarakamsa", {
      karakamsaSign: "Virgo", house: 10,
      aspectedBy: ["Jupiter", "Saturn"], conjunctWith: ["Mercury"],
      interpretation: "Career oriented toward analytics, research and intellectual fields.",
    }),

  getYogas: () =>
    stub("getYogas", [
      { name: "Budhaditya Yoga", strength: "Strong", effect: "Sharp intellect, communication-led career." },
      { name: "Gajakesari Yoga", strength: "Moderate", effect: "Fame, wisdom, prosperity over time." },
      { name: "Bhadra Mahapurusha", strength: "Strong", effect: "Mercury exalted — analytical excellence." },
      { name: "Dhana Yoga", strength: "Moderate", effect: "Wealth-forming planetary combinations active." },
    ]),

  // ---- Parashari ----
  getShadbala: () =>
    stub("getShadbala", PLANETS.slice(0, 7).map((p, i) => ({
      planet: p,
      sthana: 1.2 + (i % 3) * 0.4,
      dig: 0.8 + (i % 4) * 0.3,
      kala: 1.0 + (i % 2) * 0.5,
      cheshta: 0.6 + (i % 3) * 0.3,
      naisargika: 1.5 - i * 0.1,
      drig: 0.4 + (i % 4) * 0.2,
      total: 5.5 + ((i * 7) % 30) / 10,
      minimum: 5.0,
    }))),

  getAshtakavarga: () =>
    stub("getAshtakavarga", {
      bav: PLANETS.slice(0, 7).map((p) => ({
        planet: p,
        houses: Array.from({ length: 12 }, (_, h) => ((p.charCodeAt(0) + h) % 9)),
      })),
      sav: Array.from({ length: 12 }, (_, h) => 20 + ((h * 7) % 18)),
    }),

  getBhavaChalit: () =>
    stub("getBhavaChalit", PLANETS.map((p, i) => ({
      planet: p,
      lagnaHouse: ((i * 2) % 12) + 1,
      chalitHouse: ((i * 2 + (i % 3 === 0 ? 1 : 0)) % 12) + 1,
      shifted: i % 3 === 0,
    }))),

  getVimshopaka: () =>
    stub("getVimshopaka", PLANETS.slice(0, 7).map((p, i) => ({
      planet: p,
      score: 8 + ((i * 5) % 13),
    }))),

  // ---- Confidence ----
  getConfidenceScore: (topic: string) =>
    stub("getConfidenceScore", {
      topic,
      total: 78,
      level: "High",
      badge: "THREE SYSTEMS STRONGLY AGREE",
      breakdown: {
        kp: 30, knRao: 22, parashari: 16, prashna: 10,
      },
      explanation: "KP cusp sub-lord, KN Rao Amatyakaraka and Parashari Ashtakavarga all support this direction; Prashna shows partial confirmation.",
    }),

  // ---- Student ----
  getFieldRecommendations: (level: string) =>
    stub("getFieldRecommendations", {
      level,
      primary: { field: "Technology / Data Science", score: 84, dominantPlanet: "Mercury" },
      secondary: { field: "Engineering (Mechanical/Electrical)", score: 69, dominantPlanet: "Mars" },
      tertiary: { field: "Law / Teaching", score: 58, dominantPlanet: "Jupiter" },
      avoid: ["Performing Arts", "Hospitality"],
      timing: "Peak academic years: 2026–2029 (Jupiter Mahadasha Antardashas Sun & Mercury).",
      foreignEducation: "Moderate probability (9H + 12H + Rahu partial activation).",
      scholarship: "Strong potential — 5H, 9H and 11H simultaneously activated.",
    }),

  // ---- v8.1 Field Determination Engine ----
  // Stub: in production this would POST the built prompt + chart bundle to the LLM gateway.
  runFieldDetermination: (prompt: string, level: string) =>
    stub("runFieldDetermination", {
      engine_version: "8.1",
      promptChars: prompt.length,
      reliability: 0.92,
      prashna_used: false,
      level,
      aptitude_scores: {
        "Analytical/STEM": 88, "Engineering/Build": 71, "Medical/Bio": 44,
        "Commerce/Finance": 62, "Law/Admin": 55, "Creative/Arts": 38,
        "Research/Academia": 80, "Semiconductor/DeepTech": 74, "Foreign/Global": 66,
      },
      field_scores: [
        { cluster: "Analytical/STEM", field: "Data Science / Quant", score: 86, rationale: "Mercury exalted; D24 5H/9H clean; AK Mercury; 10H Saturn supports analytics." },
        { cluster: "Research/Academia", field: "Applied Research (CS/Math)", score: 79, rationale: "Jupiter–Ketu on 5H/9H; Karakamsa 5H aligned." },
        { cluster: "Semiconductor/DeepTech", field: "VLSI / Embedded Systems", score: 73, rationale: "Mercury–Saturn–Rahu signature; D24 unafflicted." },
      ],
      primary:   { field: "Data Science / Quant", cluster: "Analytical/STEM", score: 86, why: "Strongest reliability-adjusted aptitude + career architecture fit." },
      secondary: { field: "Applied Research", cluster: "Research/Academia", score: 79, why: "Karakamsa 5H alignment; Jupiter dasha window." },
      tertiary:  { field: "VLSI / Embedded", cluster: "Semiconductor/DeepTech", score: 73, why: "Deep-tech signature passes domain minimums." },
      avoid: ["Performing Arts", "Hospitality"],
      foreign_education: { score: 68, recommended: true, window: "2027–2029 (12L antardasha)" },
      scholarship_potential: { score: 74, notes: "5H+9H+11H simultaneously activated." },
      timing: "Peak academic years 2026–2029 (Jupiter MD, Sun/Mercury AD).",
      tie_breaker_applied: false,
      audit_trail: [
        "Stage 0: uncertainty=0 -> R=1.00",
        "Stage 2: D24_AFFINITY[Analytical/STEM]=0.95 applied",
        "Stage 8: elimination threshold = max(35, 0.55*86) = 47",
      ],
    }, 1100),

  // ---- Career Timeline ----
  getCareerTimeline: () =>
    stub("getCareerTimeline", [
      { period: "2024–2026", title: "Stable consolidation", income: 6, score: 68, type: "Stable" },
      { period: "2026–2028", title: "Pivot / new opportunity", income: 7, score: 74, type: "Pivot" },
      { period: "2028–2031", title: "Growth & promotion", income: 9, score: 86, type: "Growth" },
      { period: "2031–2034", title: "Wealth accumulation peak", income: 10, score: 91, type: "Peak" },
      { period: "2034–2037", title: "Transformation", income: 7, score: 62, type: "Transformation" },
    ]),

  // ---- Prashna ----
  askPrashna: (q: PrashnaQuery) =>
    stub("askPrashna", {
      query: q,
      answer: "YES" as "YES" | "NO" | "CONDITIONAL",
      confidence: 82,
      badge: "ALL FOUR SYSTEMS AGREE",
      timing: "Within 3–6 months, likely during Jupiter sub-period activation",
      reasoning: "Prashna Lagna sub-lord Mercury signifies 10H and 11H; Day lord and Moon nakshatra lord both connect to relevant houses.",
      conditions: "Act before October 2026 for best outcome.",
    }, 700),

  // ---- Astrologer Workspace ----
  listClients: () =>
    stub("listClients", [
      { id: "c1", name: "Anil Sharma", category: "career", lastSession: "2026-05-12" },
      { id: "c2", name: "Priya Iyer", category: "education", lastSession: "2026-05-29" },
      { id: "c3", name: "Rohan Mehta", category: "prashna", lastSession: "2026-06-02" },
      { id: "c4", name: "Sneha Rao", category: "marriage", lastSession: "2026-04-20" },
    ]),

  createClient: (name: string) =>
    stub("createClient", { id: "c_" + Date.now(), name, category: "career", lastSession: new Date().toISOString().slice(0, 10) }),

  generateReport: (template: "premium" | "professional" | "summary") =>
    stub("generateReport", { url: "/reports/sample-" + template + ".pdf", template, generatedAt: new Date().toISOString() }, 800),

  // ---- AI ----
  askAI: (prompt: string) =>
    stub("askAI", {
      prompt,
      answer: "Based on Four-System analysis: KP indicates favorable 10H sub-lord, KN Rao Amatyakaraka aligns with analytics, Parashari Ashtakavarga shows 32 bindus on 10H, and Prashna confirms. Recommendation: proceed, target window 2027 Q3.",
      score: 81,
    }, 900),

  // ---- Marketplace ----
  listAstrologers: () =>
    stub("listAstrologers", [
      { id: "a1", name: "Acharya Ramesh", systems: ["KP","Prashna"], languages: ["English","Hindi"], rating: 4.8, pricePerMin: 35 },
      { id: "a2", name: "Pandit Suresh KN", systems: ["KN Rao","Parashari"], languages: ["English","Tamil"], rating: 4.7, pricePerMin: 50 },
      { id: "a3", name: "Dr. Meera Joshi", systems: ["Parashari","Prashna"], languages: ["English","Marathi"], rating: 4.9, pricePerMin: 60 },
      { id: "a4", name: "Sri Vinod KP", systems: ["KP","Parashari","KN Rao"], languages: ["English","Telugu","Kannada"], rating: 4.6, pricePerMin: 40 },
    ]),

  bookConsultation: (astrologerId: string, slot: string) =>
    stub("bookConsultation", { bookingId: "bk_" + Date.now(), astrologerId, slot, status: "confirmed" as const }, 500),
};

export function notifyStub(action: string) {
  toast.success("Action sent: " + action, { description: "Stub API call — wire up backend to enable." });
}
