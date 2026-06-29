import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { ChartSession } from "@/lib/pyjhora/types";
import { normalizeTableResponse } from "@/lib/pyjhora/normalize";

export const CHART_SESSION_STORAGE_KEY = "jyotish:chartSessionZustand";
const LEGACY_CHART_SESSION_KEY = "jyotish:chartSession";

function normalizeSession(session: ChartSession): ChartSession {
  if (session.d1Table) {
    return { ...session, d1Table: normalizeTableResponse(session.d1Table) };
  }
  return session;
}

function readLegacyChartSession(): ChartSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(LEGACY_CHART_SESSION_KEY);
    if (!raw) return null;
    return normalizeSession(JSON.parse(raw) as ChartSession);
  } catch {
    return null;
  }
}

interface ChartSessionState {
  session: ChartSession | null;
  setSession: (session: ChartSession) => void;
  patchSession: (patch: Partial<ChartSession>) => ChartSession | null;
  clearSession: () => void;
}

export const useChartSessionStore = create<ChartSessionState>()(
  persist(
    (set, get) => ({
      session: null,
      setSession: (session) => set({ session: normalizeSession(session) }),
      patchSession: (patch) => {
        const current = get().session;
        if (!current) return null;
        const next = normalizeSession({ ...current, ...patch });
        set({ session: next });
        return next;
      },
      clearSession: () => set({ session: null }),
    }),
    {
      name: CHART_SESSION_STORAGE_KEY,
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ session: state.session }),
      onRehydrateStorage: () => (state) => {
        if (state?.session) {
          state.session = normalizeSession(state.session);
          return;
        }
        const legacy = readLegacyChartSession();
        if (legacy) {
          useChartSessionStore.setState({ session: legacy });
        }
      },
    },
  ),
);
