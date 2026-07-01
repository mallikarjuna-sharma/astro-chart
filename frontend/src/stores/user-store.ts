import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { syncDisplayNameToChartSession } from "@/stores/profile-sync";

export const USER_PROFILE_STORAGE_KEY = "jyotish:userProfile";

export interface UserProfile {
  userId: string;
  displayName: string;
  email: string;
  phone: string;
  locationQuery: string;
  notes: string;
}

interface UserState extends UserProfile {
  setUserId: (userId: string) => void;
  setDisplayName: (displayName: string) => void;
  setProfile: (profile: Partial<UserProfile>) => void;
  resetProfile: () => void;
}

const EMPTY_PROFILE: UserProfile = {
  userId: "",
  displayName: "",
  email: "",
  phone: "",
  locationQuery: "",
  notes: "",
};

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      ...EMPTY_PROFILE,
      setUserId: (userId) => set({ userId }),
      setDisplayName: (displayName) => {
        set({ displayName });
        syncDisplayNameToChartSession(displayName);
      },
      setProfile: (profile) => {
        const next = Object.fromEntries(
          Object.entries(profile).filter(([, value]) => value !== undefined),
        ) as Partial<UserProfile>;
        set((state) => ({ ...state, ...next }));
        if (next.displayName !== undefined) {
          syncDisplayNameToChartSession(next.displayName);
        }
      },
      resetProfile: () => set({ ...EMPTY_PROFILE }),
    }),
    {
      name: USER_PROFILE_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        userId: state.userId,
        displayName: state.displayName,
        email: state.email,
        phone: state.phone,
        locationQuery: state.locationQuery,
        notes: state.notes,
      }),
    },
  ),
);

/** Non-React access to the persisted display name. */
export function getStoredDisplayName(): string {
  return (useUserStore.getState().displayName ?? "").trim();
}

export function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
