import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { pyjhora } from "@/lib/pyjhora/client";
import { profilesApi } from "@/lib/profiles/client";
import { ensureConsolidatedForEngine, consolidatedHasEngineData } from "@/lib/pyjhora/ensure-consolidated";
import { patchChartSession } from "@/lib/pyjhora/session";
import { useChartSession } from "@/hooks/use-chart-session";
import { EducationCareerReport } from "@/components/education/EducationCareerReport";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function EducationAnalysisSection() {
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
        // Fast path: a saved profile usually already has a stored analysis in
        // DynamoDB — read it without recomputing the consolidated chart.
        if (profileId && !forceRefresh) {
          try {
            const cached = await profilesApi.educationAnalysis(profileId);
            patchChartSession({ educationAnalysis: cached, educationAnalysisError: undefined });
            return;
          } catch {
            // cache miss / not stored yet — fall through to compute + persist.
          }
        }

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
        const result = profileId
          ? await profilesApi.educationAnalysis(profileId, engineJson, { refresh: forceRefresh })
          : await pyjhora.educationAnalysis(engineJson);
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
    [consolidated, profileId, session?.birthInput, session?.studentContext],
  );

  useEffect(() => {
    if (!data && !loading && !error && session?.birthInput) {
      void runAnalysis();
    }
  }, [data, loading, error, session?.birthInput, runAnalysis]);

  if (!session) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No chart session. Open a profile from the Profiles page first.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Career &amp; Education Report</CardTitle>
          <CardDescription>
            JyotishAI engine · deterministic scoring + Gemini field selection from consolidated chart JSON.
          </CardDescription>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={loading || !session?.birthInput}
          onClick={() => void runAnalysis(true)}
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <RefreshCw className="h-4 w-4 mr-1" />}
          {loading ? "Analyzing…" : "Refresh"}
        </Button>
      </CardHeader>
      <CardContent>
        {loading && !data ? (
          <div className="flex items-center gap-2 text-muted-foreground py-8 justify-center">
            <Loader2 className="h-5 w-5 animate-spin" />
            Running career engine (may take 30–60 seconds)…
          </div>
        ) : null}

        {error ? (
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive mb-4">
            {error}
          </div>
        ) : null}

        {data ? <EducationCareerReport data={data} /> : null}

        {!loading && !data && !error ? (
          <p className="text-sm text-muted-foreground py-4">
            Run analysis from consolidated chart data, or open a profile with saved charts first.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
