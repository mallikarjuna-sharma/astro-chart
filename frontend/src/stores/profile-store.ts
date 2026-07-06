import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ProfileSummary } from "@/lib/profiles/types";

interface ProfileState {
  profiles: ProfileSummary[];
  activeProfileId: string | null;
  setProfiles: (profiles: ProfileSummary[]) => void;
  setActiveProfileId: (id: string | null) => void;
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set) => ({
      profiles: [],
      activeProfileId: null,
      setProfiles: (profiles) => set({ profiles }),
      setActiveProfileId: (id) => set({ activeProfileId: id }),
    }),
    { name: "jyotish:profiles" },
  ),
);
