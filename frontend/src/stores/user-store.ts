import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { syncDisplayNameToChartSession } from "@/stores/profile-sync";

export const USER_PROFILE_STORAGE_KEY = "jyotish:userProfile";

export interface UserProfile {
  displayName: string;
  email: string;
  locationQuery: string;
}

interface UserState extends UserProfile {
  setDisplayName: (displayName: string) => void;
  setProfile: (profile: Partial<UserProfile>) => void;
  resetProfile: () => void;
}

const EMPTY_PROFILE: UserProfile = {
  displayName: "",
  email: "",
  locationQuery: "",
};

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      ...EMPTY_PROFILE,
      setDisplayName: (displayName) => {
        set({ displayName });
        syncDisplayNameToChartSession(displayName);
      },
      setProfile: (profile) => {
        set((state) => ({ ...state, ...profile }));
        if (profile.displayName !== undefined) {
          syncDisplayNameToChartSession(profile.displayName);
        }
      },
      resetProfile: () => set({ ...EMPTY_PROFILE }),
    }),
    {
      name: USER_PROFILE_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        displayName: state.displayName,
        email: state.email,
        locationQuery: state.locationQuery,
      }),
    },
  ),
);

/** Non-React access to the persisted display name. */
export function getStoredDisplayName(): string {
  return useUserStore.getState().displayName.trim();
}

export function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
