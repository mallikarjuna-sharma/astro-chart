import { create } from "zustand";
import { persist } from "zustand/middleware";
import { profilesApi } from "@/lib/profiles/client";
import type { ProfileSummary } from "@/lib/profiles/types";

interface ProfileState {
  profiles: ProfileSummary[];
  maxProfiles: number;
  activeProfileId: string | null;
  /** True once the list has been fetched for the current owner. */
  loaded: boolean;
  /** True while a list fetch is in flight (transient — not persisted). */
  loading: boolean;
  /** The user_id the cached list belongs to (guards against cross-user reuse). */
  ownerUserId: string | null;
  setProfiles: (profiles: ProfileSummary[]) => void;
  setActiveProfileId: (id: string | null) => void;
  /**
   * Load the profiles list. This is a no-op when the list is already cached
   * for the current owner, so navigating back to the profiles section does not
   * hit the API again. Pass `{ force: true }` after a create/delete to refresh.
   */
  fetchProfiles: (userId: string | null, opts?: { force?: boolean }) => Promise<void>;
  reset: () => void;
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set, get) => ({
      profiles: [],
      maxProfiles: 4,
      activeProfileId: null,
      loaded: false,
      loading: false,
      ownerUserId: null,
      setProfiles: (profiles) => set({ profiles }),
      setActiveProfileId: (id) => set({ activeProfileId: id }),

      fetchProfiles: async (userId, opts) => {
        const state = get();
        const force = opts?.force ?? false;
        const ownerChanged = userId != null && state.ownerUserId !== userId;
        // Serve from cache unless forced or the owner changed — this is what
        // keeps profile-section navigation from re-hitting the API every time.
        if (state.loading) return;
        if (state.loaded && !force && !ownerChanged) return;
        set({ loading: true });
        try {
          const res = await profilesApi.list();
          set({
            profiles: res.profiles,
            maxProfiles: res.max_profiles,
            loaded: true,
            loading: false,
            ownerUserId: userId ?? state.ownerUserId,
          });
        } catch (err) {
          set({ loading: false });
          throw err;
        }
      },

      reset: () =>
        set({
          profiles: [],
          maxProfiles: 4,
          activeProfileId: null,
          loaded: false,
          loading: false,
          ownerUserId: null,
        }),
    }),
    {
      name: "jyotish:profiles",
      // `loading` is transient and must never be rehydrated as `true`.
      partialize: (state) => ({
        profiles: state.profiles,
        maxProfiles: state.maxProfiles,
        activeProfileId: state.activeProfileId,
        loaded: state.loaded,
        ownerUserId: state.ownerUserId,
      }),
    },
  ),
);
