import type { ChartSession } from "@/lib/pyjhora/types";
import { profileIsFullyPersisted, profileToChartSession } from "./hydrate";
import type { ProfileResponse } from "./types";

/** True when extended APIs (KP, consolidated, etc.) are present in session. */
export function isChartSessionHydrated(session: ChartSession | null | undefined): boolean {
  return !!(session?.birthInput && session.consolidated && session.kp);
}

/** Active profile is already loaded in the chart session — skip API restore. */
export function isProfileSessionReady(
  profileId: string,
  session: ChartSession | null | undefined,
): boolean {
  return session?.chartId === profileId && isChartSessionHydrated(session);
}

/**
 * Load chart session from saved profile (DynamoDB → API → UI).
 * Does not re-run backend calculations.
 */
export function restoreProfileToChartSession(
  profile: ProfileResponse,
  onProgress?: (step: string) => void,
): ChartSession {
  if (!profileIsFullyPersisted(profile)) {
    onProgress?.("Profile is missing saved chart data. Create the profile again.");
    throw new Error(
      "This profile was saved before full persistence was enabled. Please delete and recreate it.",
    );
  }
  onProgress?.("Loading saved profile from database…");
  return profileToChartSession(profile);
}
