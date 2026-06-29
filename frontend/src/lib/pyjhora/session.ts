import type { BirthInput, ChartSession, StudentContext, UserInfo } from "./types";
import { normalizeTableResponse } from "./normalize";
import { useChartSessionStore } from "@/stores/chart-session-store";
import { syncUserProfileFromSession } from "@/stores/profile-sync";
import { useUserStore } from "@/stores/user-store";

/** @deprecated Use chart session store subscriptions; kept for legacy listeners. */
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
  return useChartSessionStore.getState().session;
}

export function saveChartSession(session: ChartSession): void {
  const normalized = session.d1Table
    ? { ...session, d1Table: normalizeTableResponse(session.d1Table) }
    : session;
  useChartSessionStore.getState().setSession(normalized);
  syncUserProfileFromSession(normalized);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(CHART_SESSION_EVENT));
  }
}

export function patchChartSession(patch: Partial<ChartSession>): ChartSession | null {
  const next = useChartSessionStore.getState().patchSession(patch);
  if (next) {
    syncUserProfileFromSession(next);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(CHART_SESSION_EVENT));
    }
  }
  return next;
}

export function clearChartSession(): void {
  useChartSessionStore.getState().clearSession();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(CHART_SESSION_EVENT));
  }
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

/** Compute current age (years, with decimals) from a consolidated chart JSON. */
export function ageFromConsolidated(consolidated: Record<string, unknown> | undefined | null): number | null {
  if (!consolidated) return null;
  const sc = (consolidated as { student_context?: { dob?: string } }).student_context;
  const sys = (consolidated as { system_config?: { current_date?: string } }).system_config;
  const dob = sc?.dob;
  if (!dob) return null;
  const dobTime = Date.parse(dob);
  if (!Number.isFinite(dobTime)) return null;
  const refTime = sys?.current_date ? Date.parse(sys.current_date) : Date.now();
  const ref = Number.isFinite(refTime) ? refTime : Date.now();
  const diffMs = ref - dobTime;
  if (!Number.isFinite(diffMs) || diffMs <= 0) return null;
  return diffMs / (365.25 * 24 * 60 * 60 * 1000);
}

export function buildUserInfo(
  displayName: string,
  email: string,
  locationQuery: string,
): UserInfo {
  return {
    display_name: displayName.trim(),
    email: email.trim() || null,
    location_query: locationQuery.trim() || null,
  };
}

/** Persist a full UserInfo payload to localStorage-backed profile store. */
export function persistUserProfile(userInfo: UserInfo, userId?: string): UserInfo {
  useUserStore.getState().setProfile({
    userId: userId ?? useUserStore.getState().userId,
    displayName: userInfo.display_name.trim(),
    email: userInfo.email?.trim() ?? "",
    phone: userInfo.phone?.trim() ?? "",
    locationQuery: userInfo.location_query?.trim() ?? "",
    notes: userInfo.notes?.trim() ?? "",
  });
  return userInfo;
}
