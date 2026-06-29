import { useMemo } from "react";
import { useChartSession } from "@/hooks/use-chart-session";
import { useChartSessionStore } from "@/stores/chart-session-store";
import { getStoredDisplayName, useUserStore } from "@/stores/user-store";

const FALLBACK = "Student";

/**
 * Resolved display name for the current native — persisted in localStorage,
 * with fallbacks to chart session and education analysis payload.
 */
export function useDisplayName(educationStudentName?: string | null): string {
  const storedName = useUserStore((s) => s.displayName);
  const session = useChartSession();

  return useMemo(() => {
    return resolveDisplayName(educationStudentName, session?.userInfo.display_name);
  }, [storedName, session?.userInfo.display_name, educationStudentName]);
}

/** Non-React helper — same resolution order as {@link useDisplayName}. */
export function resolveDisplayName(
  educationStudentName?: string | null,
  sessionDisplayName?: string | null,
): string {
  const fromStore = getStoredDisplayName();
  if (fromStore) return fromStore;

  const fromSession = (sessionDisplayName ?? useChartSessionStore.getState().session?.userInfo.display_name)?.trim();
  if (fromSession) return fromSession;

  const fromEducation = educationStudentName?.trim();
  if (fromEducation) return fromEducation;

  return FALLBACK;
}
