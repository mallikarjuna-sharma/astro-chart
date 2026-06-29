import type { ChartSession, UserInfo } from "@/lib/pyjhora/types";
import { useChartSessionStore } from "@/stores/chart-session-store";
import { useUserStore } from "@/stores/user-store";

/** Copy profile fields from chart session into localStorage-backed user store. */
export function syncUserProfileFromSession(session: ChartSession): void {
  const { display_name, email, location_query, phone, notes } = session.userInfo;
  useUserStore.getState().setProfile({
    userId: session.userId,
    displayName: display_name?.trim() ?? "",
    email: email?.trim() ?? "",
    phone: phone?.trim() ?? "",
    locationQuery: location_query?.trim() ?? "",
    notes: notes?.trim() ?? "",
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

/** Persist user profile fields from a full UserInfo payload. */
export function syncUserProfileFromUserInfo(userId: string, userInfo: UserInfo): void {
  useUserStore.getState().setProfile({
    userId,
    displayName: userInfo.display_name?.trim() ?? "",
    email: userInfo.email?.trim() ?? "",
    phone: userInfo.phone?.trim() ?? "",
    locationQuery: userInfo.location_query?.trim() ?? "",
    notes: userInfo.notes?.trim() ?? "",
  });
}
