import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { profilesApi } from "@/lib/profiles/client";
import {
  isProfileSessionReady,
  restoreProfileToChartSession,
} from "@/lib/profiles/restore-session";
import { saveChartSession } from "@/lib/pyjhora/session";
import { useChartSessionStore } from "@/stores/chart-session-store";
import { useProfileStore } from "@/stores/profile-store";

/** Re-hydrate extended chart data when a profile is active but session is incomplete. */
export function ProfileSessionBootstrap() {
  const session = useChartSessionStore((s) => s.session);
  const activeProfileId = useProfileStore((s) => s.activeProfileId);
  const hydratingRef = useRef(false);

  useEffect(() => {
    if (!activeProfileId || hydratingRef.current) return;

    const profileMismatch = session?.chartId !== activeProfileId;
    const needsHydrate =
      profileMismatch || !isProfileSessionReady(activeProfileId, session);
    if (!needsHydrate) return;

    hydratingRef.current = true;
    profilesApi
      .get(activeProfileId)
      .then((profile) => restoreProfileToChartSession(profile))
      .then((full) => saveChartSession(full))
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : "Failed to load profile charts");
      })
      .finally(() => {
        hydratingRef.current = false;
      });
  }, [activeProfileId, session?.chartId, session?.consolidated, session?.kp]);

  return null;
}
