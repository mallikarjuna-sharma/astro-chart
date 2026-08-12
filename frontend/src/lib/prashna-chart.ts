import type { DivisionalChart, PrashnaResponse } from "@/lib/pyjhora/types";

const RASI_NAMES = [
  "Aries",
  "Taurus",
  "Gemini",
  "Cancer",
  "Leo",
  "Virgo",
  "Libra",
  "Scorpio",
  "Sagittarius",
  "Capricorn",
  "Aquarius",
  "Pisces",
] as const;

const SIGN_TO_RASI = Object.fromEntries(RASI_NAMES.map((name, i) => [name, i])) as Record<string, number>;

const PLANET_SHORT: Record<string, string> = {
  Sun: "Su",
  Moon: "Mo",
  Mars: "Ma",
  Mercury: "Me",
  Jupiter: "Ju",
  Venus: "Ve",
  Saturn: "Sa",
  Rahu: "Ra",
  Ketu: "Ke",
};

/** Build a South-Indian D1 chart from a Prashna API response. */
export function prashnaToSouthIndianChart(answer: PrashnaResponse): DivisionalChart {
  const buckets: string[][] = Array.from({ length: 12 }, () => []);

  const lagnaRasi = SIGN_TO_RASI[answer.lagna_sign];
  if (lagnaRasi !== undefined) {
    buckets[lagnaRasi].push("La");
  }

  for (const [planet, snapshot] of Object.entries(answer.planets ?? {})) {
    const sign = snapshot.sign;
    if (!sign) continue;
    const rasi = SIGN_TO_RASI[sign];
    if (rasi === undefined) continue;
    buckets[rasi].push(PLANET_SHORT[planet] ?? planet.slice(0, 2));
  }

  return {
    factor: 1,
    name: "Prashna (D1)",
    houses: RASI_NAMES.map((rasi_name, rasi) => ({
      rasi,
      rasi_name,
      bodies: buckets[rasi],
    })),
  };
}
