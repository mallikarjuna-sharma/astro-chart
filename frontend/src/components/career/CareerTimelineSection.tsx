import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Info, Loader2, RefreshCw } from "lucide-react";
import { defaultCareerContext } from "@/components/career/CareerContextForm";
import { pyjhora } from "@/lib/pyjhora/client";
import { ensureConsolidatedForEngine, consolidatedHasEngineData } from "@/lib/pyjhora/ensure-consolidated";
import { ageFromConsolidated, patchChartSession } from "@/lib/pyjhora/session";
import { useChartSession } from "@/hooks/use-chart-session";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CareerTimelineReport } from "@/components/career/CareerTimelineReport";

const MIN_CAREER_AGE = 20;

export function CareerTimelineSection() {
  const session = useChartSession();
  const [loading, setLoading] = useState(false);

  const data = session?.careerTimeline;
  const error = session?.careerTimelineError ?? null;
  const consolidated = session?.consolidated;
  const careerContext = session?.careerContextInput;
  const currentAge = useMemo(() => ageFromConsolidated(consolidated), [consolidated]);
  const isUnderAge = typeof currentAge === "number" && currentAge < MIN_CAREER_AGE;

  const run = useCallback(async () => {
    if (!session?.birthInput) {
      patchChartSession({
        careerTimelineError:
          "Consolidated chart JSON is not available. Open a profile from the Profiles page.",
      });
      return;
    }
    const ctx = careerContext ?? defaultCareerContext(currentAge);
    setLoading(true);
    patchChartSession({ careerTimelineError: undefined, careerContextInput: ctx });
    try {
      const engineJson = await ensureConsolidatedForEngine(
        session.birthInput,
        session.studentContext,
        consolidated,
        ctx,
      );
      if (!consolidatedHasEngineData(consolidated)) {
        patchChartSession({ consolidated: engineJson });
      }
      const result = await pyjhora.careerTimeline(engineJson, {
        careerContext: ctx,
        enrichLlm: true,
      });
      patchChartSession({
        careerTimeline: result,
        careerTimelineError: undefined,
      });
    } catch (err) {
      patchChartSession({
        careerTimelineError: String((err as Error)?.message ?? err),
      });
    } finally {
      setLoading(false);
    }
  }, [consolidated, careerContext, currentAge, session?.birthInput, session?.studentContext]);

  useEffect(() => {
    if (!data && !loading && !error && session?.birthInput && !isUnderAge) {
      void run();
    }
  }, [data, loading, error, session?.birthInput, isUnderAge, run]);

  if (!session) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No chart session. Open a profile from the Profiles page first.
        </CardContent>
      </Card>
    );
  }

  if (isUnderAge) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Info className="h-5 w-5 text-warn" />
            Career Timeline is for adult charts
          </CardTitle>
          <CardDescription>
            This chart is currently age {currentAge!.toFixed(1)}. The JyotishAI Career
            Timeline engine activates from age {MIN_CAREER_AGE}+ when there is a real working
            career to plot. For students (under {MIN_CAREER_AGE}), use Career Field instead.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <Link to="/education-analysis">
            <Button>Go to Career Field</Button>
          </Link>
          <Link to="/">
            <Button variant="outline">Switch profile</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>Career Timeline</CardTitle>
            <CardDescription>
              Built from your profile&apos;s birth data and career context
              {typeof currentAge === "number" ? ` (age ${currentAge.toFixed(1)})` : ""}.
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" disabled={loading || !session?.birthInput} onClick={() => void run()}>
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-1" />
            )}
            {loading ? "Building…" : "Refresh"}
          </Button>
        </CardHeader>
        <CardContent>
          {loading && !data ? (
            <div className="flex items-center gap-2 text-muted-foreground py-8 justify-center">
              <Loader2 className="h-5 w-5 animate-spin" />
              Building career timeline (may take 20–60 seconds)…
            </div>
          ) : null}

          {error ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive mb-4">
              {error}
            </div>
          ) : null}

          {data ? <CareerTimelineReport data={data} /> : null}

          {!loading && !data && !error ? (
            <p className="text-sm text-muted-foreground py-4">
              Open a profile from the Profiles page to load chart data first.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
