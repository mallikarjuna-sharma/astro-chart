import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { pyjhora } from "@/lib/pyjhora/client";
import { ensureConsolidatedForEngine } from "@/lib/pyjhora/ensure-consolidated";
import { profilesApi } from "@/lib/profiles/client";
import { patchChartSession } from "@/lib/pyjhora/session";
import { useChartSession } from "@/hooks/use-chart-session";
import { isPucEligible, pucAgeErrorMessage, approxAgeFromBirthInput } from "@/lib/education-report/tab-defaults";
import { PucStreamReport } from "@/components/education/PucStreamReport";
import { Card, CardContent } from "@/components/ui/card";
import type { PucAnalysisResponse } from "@/lib/pyjhora/types";

export function usePucAnalysis() {
  const session = useChartSession();
  const [loading, setLoading] = useState(false);

  const data = session?.pucAnalysis;
  const error = session?.pucAnalysisError ?? null;
  const consolidated = session?.consolidated;
  const profileId = session?.chartId;

  const runAnalysis = useCallback(
    async (forceRefresh = false) => {
      if (!session?.birthInput) {
        patchChartSession({
          pucAnalysisError:
            "Consolidated chart JSON is not available. Open a profile from the Profiles page.",
        });
        return;
      }
      const approxAge = approxAgeFromBirthInput(session.birthInput);
      if (!isPucEligible(approxAge)) {
        patchChartSession({ pucAnalysisError: pucAgeErrorMessage(approxAge) });
        return;
      }
      setLoading(true);
      patchChartSession({ pucAnalysisError: undefined });
      try {
        const result = profileId
          ? await profilesApi.pucAnalysis(profileId, { refresh: forceRefresh })
          : await pyjhora.pucEducationAnalysis(
              await ensureConsolidatedForEngine(
                session.birthInput,
                session.studentContext,
                consolidated,
                undefined,
                session.userInfo?.display_name,
              ),
            );
        patchChartSession({
          pucAnalysis: result,
          pucAnalysisError: undefined,
        });
      } catch (err) {
        patchChartSession({
          pucAnalysisError: String((err as Error)?.message ?? err),
        });
      } finally {
        setLoading(false);
      }
    },
    [consolidated, profileId, session?.birthInput, session?.studentContext, session?.userInfo?.display_name],
  );

  useEffect(() => {
    if (!data && !loading && !error && session?.birthInput) {
      void runAnalysis();
    }
  }, [data, error, loading, runAnalysis, session?.birthInput]);

  return { session, loading, error, data, runAnalysis };
}

type PucAnalysisSectionProps = {
  loading: boolean;
  error: string | null;
  data?: PucAnalysisResponse;
  hasSession: boolean;
};

export function PucAnalysisSection({ loading, error, data, hasSession }: PucAnalysisSectionProps) {
  if (!hasSession) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No chart session. Open a profile from the Profiles page first.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {loading && !data ? (
        <Card>
          <CardContent className="flex items-center gap-2 text-muted-foreground py-10 justify-center">
            <Loader2 className="h-5 w-5 animate-spin" />
            Running PUC stream engine…
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {data ? <PucStreamReport data={data} /> : null}
    </div>
  );
}
