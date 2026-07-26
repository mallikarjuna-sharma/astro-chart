import { create } from "zustand";
import { persist } from "zustand/middleware";
import { authApi, getStoredAuthToken, setStoredAuthToken } from "@/lib/auth/client";
import type { AuthUser } from "@/lib/auth/types";
import { clearChartSession } from "@/lib/pyjhora/session";
import { PYJHORA_LS_USER } from "@/lib/pyjhora/client";
import { useUserStore } from "@/stores/user-store";
import { useProfileStore } from "@/stores/profile-store";

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  hydrated: boolean;
  setSession: (token: string, user: AuthUser) => void;
  /** Wipe chart, profile, and display data without touching auth tokens. */
  clearAllAppData: () => void;
  clearSession: () => void;
  restoreSession: () => Promise<void>;
  ensureAuthenticated: () => Promise<boolean>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      hydrated: false,

      setSession: (token, user) => {
        setStoredAuthToken(token);
        localStorage.setItem(PYJHORA_LS_USER, user.user_id);
        useUserStore.getState().setProfile({
          userId: user.user_id,
          displayName: user.username,
          email: user.email,
        });
        set({ accessToken: token, user, hydrated: true });
      },

      clearAllAppData: () => {
        useUserStore.getState().resetProfile();
        useProfileStore.getState().reset();
        clearChartSession();
        try {
          localStorage.removeItem(PYJHORA_LS_USER);
        } catch {
          /* ignore */
        }
      },

      clearSession: () => {
        setStoredAuthToken(null);
        get().clearAllAppData();
        set({ accessToken: null, user: null, hydrated: true });
      },

      restoreSession: async () => {
        const token = get().accessToken || getStoredAuthToken();
        if (!token) {
          get().clearAllAppData();
          set({ accessToken: null, user: null, hydrated: true });
          return;
        }
        try {
          const { user } = await authApi.me(token);
          get().setSession(token, user);
        } catch {
          get().clearSession();
        }
      },

      ensureAuthenticated: async () => {
        if (!get().hydrated) {
          await get().restoreSession();
        }
        return Boolean(get().user && get().accessToken);
      },
    }),
    {
      name: "jyotish:auth",
      partialize: (state) => ({
        accessToken: state.accessToken,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        state?.restoreSession();
      },
    },
  ),
);

export function useIsAuthenticated(): boolean {
  return useAuthStore((s) => Boolean(s.user && s.accessToken));
}
