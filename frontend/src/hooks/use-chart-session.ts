import { useEffect, useState } from "react";
import type { ChartSession } from "@/lib/pyjhora/types";
import { CHART_SESSION_EVENT, loadChartSession } from "@/lib/pyjhora/session";

/** Read pyJHora analysis payloads cached after Save & generate charts. */
export function useChartSession() {
  const [session, setSession] = useState<ChartSession | null>(null);

  useEffect(() => {
    setSession(loadChartSession());
    const refresh = () => setSession(loadChartSession());
    window.addEventListener(CHART_SESSION_EVENT, refresh);
    return () => window.removeEventListener(CHART_SESSION_EVENT, refresh);
  }, []);

  return session;
}
