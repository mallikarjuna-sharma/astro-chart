import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { pyjhora } from "@/lib/pyjhora/client";
import { profilesApi } from "@/lib/profiles/client";
import { ensureConsolidatedForEngine, consolidatedHasEngineData } from "@/lib/pyjhora/ensure-consolidated";
import { patchChartSession } from "@/lib/pyjhora/session";
import { useChartSession } from "@/hooks/use-chart-session";
import type { EducationAnalysisResponse } from "@/lib/pyjhora/types";
import { EducationCareerReport } from "@/components/education/EducationCareerReport";
import { Card, CardContent } from "@/components/ui/card";

export function useUgAnalysis() {
  const session = useChartSession();
  const [loading, setLoading] = useState(false);

  const data = session?.educationAnalysis;
  const error = session?.educationAnalysisError ?? null;
  const consolidated = session?.consolidated;
  const profileId = session?.chartId;

  const runAnalysis = useCallback(
    async (forceRefresh = false) => {
      if (!session?.birthInput) {
        patchChartSession({
          educationAnalysisError:
            "Consolidated chart JSON is not available. Open a profile from the Profiles page.",
        });
        return;
      }
      setLoading(true);
      patchChartSession({ educationAnalysisError: undefined });
      try {
        const engineJson = await ensureConsolidatedForEngine(
          session.birthInput,
          session.studentContext,
          consolidated,
          undefined,
          session.userInfo?.display_name,
        );
        if (!consolidatedHasEngineData(consolidated)) {
          patchChartSession({ consolidated: engineJson });
        }

        if (profileId && !forceRefresh) {
          try {
            const cached = await profilesApi.educationAnalysis(profileId, engineJson);
            if (cached.AI != null) {
              patchChartSession({ educationAnalysis: cached, educationAnalysisError: undefined });
              return;
            }
            // Legacy cache without AI diagnostics — recompute below with chart JSON.
          } catch {
            // cache miss — compute below
          }
        }

        const result = profileId
          ? await profilesApi.educationAnalysis(profileId, engineJson, { refresh: forceRefresh })
          : await pyjhora.ugEducationAnalysis(engineJson);
        patchChartSession({
          educationAnalysis: result,
          educationAnalysisError: undefined,
        });
      } catch (err) {
        patchChartSession({
          educationAnalysisError: String((err as Error)?.message ?? err),
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

type UgAnalysisSectionProps = {
  loading: boolean;
  error: string | null;
  data?: EducationAnalysisResponse;
  hasSession: boolean;
};

export function UgAnalysisSection({ loading, error, data, hasSession }: UgAnalysisSectionProps) {
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
            Running UG career engine (may take 30–60 seconds)…
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {data ? <EducationCareerReport data={data} /> : null}
    </div>
  );
}
