import { useMemo } from "react";
import { loadChartSession } from "@/lib/pyjhora/session";

/** Read pyJHora analysis payloads cached after Save & generate charts. */
export function useChartSession() {
  return useMemo(() => loadChartSession(), []);
}
