import type { BirthInput, ChartSession, StudentContext, UserInfo } from "./types";
import { normalizeTableResponse } from "./normalize";

export const CHART_SESSION_KEY = "jyotish:chartSession";
export const CHART_SESSION_EVENT = "jyotish:chartSession";

export function defaultStudentContext(): StudentContext {
  return {
    pob: null,
    gender: "O",
    education_system: "India_CBSE",
    student_preference: {
      interested_in: [],
      already_excel_at: [],
      financial_constraints: false,
      risk_appetite: "MODERATE",
    },
  };
}

export function loadChartSession(): ChartSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(CHART_SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as ChartSession;
    if (session.d1Table) {
      session.d1Table = normalizeTableResponse(session.d1Table);
    }
    return session;
  } catch {
    return null;
  }
}

export function saveChartSession(session: ChartSession): void {
  sessionStorage.setItem(CHART_SESSION_KEY, JSON.stringify(session));
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(CHART_SESSION_EVENT));
  }
}

export function patchChartSession(patch: Partial<ChartSession>): ChartSession | null {
  const current = loadChartSession();
  if (!current) return null;
  const next = { ...current, ...patch };
  saveChartSession(next);
  return next;
}

export function clearChartSession(): void {
  sessionStorage.removeItem(CHART_SESSION_KEY);
}

/** Split HTML date/time inputs into pyJHora birth fields. */
export function parseBirthDateTime(date: string, time: string): Pick<
  BirthInput,
  "year" | "month" | "day" | "hour" | "minute" | "second"
> {
  const [y, m, d] = date.split("-").map(Number);
  const timeParts = time.split(":").map(Number);
  return {
    year: y,
    month: m,
    day: d,
    hour: timeParts[0] ?? 0,
    minute: timeParts[1] ?? 0,
    second: timeParts[2] ?? 0,
  };
}

export function buildBirthInput(
  dt: ReturnType<typeof parseBirthDateTime>,
  place: {
    place_label: string;
    latitude: number;
    longitude: number;
    timezone_offset_hours: number;
    ayanamsa: string;
    use_true_nodes: boolean;
    include_outer_planets: boolean;
  },
): BirthInput {
  return { ...dt, ...place };
}

export function buildUserInfo(
  displayName: string,
  email: string,
  locationQuery: string,
): UserInfo {
  return {
    display_name: displayName,
    email: email.trim() || null,
    location_query: locationQuery.trim() || null,
  };
}
