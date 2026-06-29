import { useChartSessionStore } from "@/stores/chart-session-store";

/** Read pyJHora analysis payloads cached after Save & generate charts. */
export function useChartSession() {
  return useChartSessionStore((s) => s.session);
}
