import { create } from "zustand";
import { persist } from "zustand/middleware";
import { authApi, getStoredAuthToken, setStoredAuthToken } from "@/lib/auth/client";
import type { AuthUser } from "@/lib/auth/types";
import { useUserStore } from "@/stores/user-store";
import { useProfileStore } from "@/stores/profile-store";
import { PYJHORA_LS_USER } from "@/lib/pyjhora/client";

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  hydrated: boolean;
  setSession: (token: string, user: AuthUser) => void;
  clearSession: () => void;
  restoreSession: () => Promise<void>;
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

      clearSession: () => {
        setStoredAuthToken(null);
        // Drop the cached profiles list so it can't leak into the next session.
        useProfileStore.getState().reset();
        set({ accessToken: null, user: null, hydrated: true });
      },

      restoreSession: async () => {
        const token = get().accessToken || getStoredAuthToken();
        if (!token) {
          set({ hydrated: true });
          return;
        }
        try {
          const { user } = await authApi.me(token);
          get().setSession(token, user);
        } catch {
          get().clearSession();
        }
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
