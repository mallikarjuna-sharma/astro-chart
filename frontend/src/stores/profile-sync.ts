import type { ChartSession, UserInfo } from "@/lib/pyjhora/types";
import { useChartSessionStore } from "@/stores/chart-session-store";
import { useUserStore } from "@/stores/user-store";

/** Copy display name (and related profile fields) from chart session into localStorage-backed user store. */
export function syncUserProfileFromSession(session: ChartSession): void {
  const { display_name, email, location_query } = session.userInfo;
  useUserStore.getState().setProfile({
    displayName: display_name?.trim() ?? "",
    email: email?.trim() ?? "",
    locationQuery: location_query?.trim() ?? "",
  });
}

/** Push user-store display name into the active chart session (if any). */
export function syncDisplayNameToChartSession(displayName: string): void {
  const trimmed = displayName.trim();
  if (!trimmed) return;

  const session = useChartSessionStore.getState().session;
  if (!session?.userInfo) return;

  const nextUserInfo: UserInfo = {
    ...session.userInfo,
    display_name: trimmed,
  };

  useChartSessionStore.getState().patchSession({ userInfo: nextUserInfo });
}
