import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { pyjhora } from "@/lib/pyjhora/client";
import { ensureConsolidatedForEngine, consolidatedHasEngineData } from "@/lib/pyjhora/ensure-consolidated";
import { patchChartSession } from "@/lib/pyjhora/session";
import { useChartSession } from "@/hooks/use-chart-session";
import { PucStreamReport } from "@/components/education/PucStreamReport";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function PucAnalysisSection() {
  const session = useChartSession();
  const [loading, setLoading] = useState(false);

  const data = session?.pucAnalysis;
  const error = session?.pucAnalysisError ?? null;
  const consolidated = session?.consolidated;

  const runAnalysis = useCallback(async () => {
    if (!session?.birthInput) {
      patchChartSession({
        pucAnalysisError:
          "Consolidated chart JSON is not available. Open a profile from the Profiles page.",
      });
      return;
    }
    setLoading(true);
    patchChartSession({ pucAnalysisError: undefined });
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
      const result = await pyjhora.pucEducationAnalysis(engineJson);
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
  }, [consolidated, session?.birthInput, session?.studentContext, session?.userInfo?.display_name]);

  useEffect(() => {
    if (!data && !loading && !error && session?.birthInput) {
      void runAnalysis();
    }
  }, [data, error, loading, runAnalysis, session?.birthInput]);

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
    <div className="space-y-5">
      <div className="flex flex-row items-start justify-between gap-4 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div>
          <div className="font-serif text-base font-semibold text-foreground">PUC Stream Analysis</div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Science / Commerce / Humanities direction and subject recommendations for 11th–12th.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={loading || !session.birthInput}
          onClick={() => void runAnalysis()}
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <RefreshCw className="h-4 w-4 mr-1" />}
          {loading ? "Analyzing…" : "Refresh"}
        </Button>
      </div>

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
