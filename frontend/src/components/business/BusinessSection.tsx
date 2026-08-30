import { useCallback, useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Loader2, RefreshCw } from "lucide-react";
import { pyjhora } from "@/lib/pyjhora/client";
import {
  ensureConsolidatedForEngine,
  consolidatedHasEngineData,
} from "@/lib/pyjhora/ensure-consolidated";
import { patchChartSession } from "@/lib/pyjhora/session";
import { useChartSession } from "@/hooks/use-chart-session";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { BusinessReport } from "@/components/business/BusinessReport";

export function BusinessSection() {
  const session = useChartSession();
  const [loading, setLoading] = useState(false);

  const data = session?.businessPrediction;
  const error = session?.businessPredictionError ?? null;
  const consolidated = session?.consolidated;

  const run = useCallback(async () => {
    if (!session?.birthInput) {
      patchChartSession({
        businessPredictionError:
          "Consolidated chart JSON is not available. Open a profile from the Profiles page.",
      });
      return;
    }
    setLoading(true);
    patchChartSession({ businessPredictionError: undefined });
    try {
      const engineJson = await ensureConsolidatedForEngine(
        session.birthInput,
        session.studentContext,
        consolidated,
        session.careerContextInput,
      );
      if (!consolidatedHasEngineData(consolidated)) {
        patchChartSession({ consolidated: engineJson });
      }
      const result = await pyjhora.businessPrediction(engineJson);
      patchChartSession({
        businessPrediction: result,
        businessPredictionError: undefined,
      });
    } catch (err) {
      patchChartSession({
        businessPredictionError: String((err as Error)?.message ?? err),
      });
    } finally {
      setLoading(false);
    }
  }, [consolidated, session?.birthInput, session?.careerContextInput, session?.studentContext]);

  useEffect(() => {
    if (!data && !loading && !error && session?.birthInput) {
      void run();
    }
  }, [data, loading, error, session?.birthInput, run]);

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
    <div className="space-y-4 px-4 sm:px-6 md:px-8">
      <div className="flex justify-end">
        <Button
          variant="outline"
          size="sm"
          disabled={loading || !session?.birthInput}
          onClick={() => void run()}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin mr-1" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-1" />
          )}
          {loading ? "Analyzing…" : "Refresh"}
        </Button>
      </div>

      {loading && !data ? (
        <Card>
          <CardContent className="flex items-center gap-2 text-muted-foreground py-10 justify-center">
            <Loader2 className="h-5 w-5 animate-spin" />
            Building your business analysis…
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {data ? <BusinessReport data={data} /> : null}

      {!loading && !data && !error ? (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground text-center">
            <p className="mb-3">Open a profile from the Profiles page to load chart data first.</p>
            <Link to="/">
              <Button variant="outline" size="sm">
                Go to Profiles
              </Button>
            </Link>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
