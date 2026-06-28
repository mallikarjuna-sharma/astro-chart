import { useCallback, useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Info, Loader2 } from "lucide-react";
import { pyjhora } from "@/lib/pyjhora/client";
import { ageFromConsolidated, patchChartSession } from "@/lib/pyjhora/session";
import { useChartSession } from "@/hooks/use-chart-session";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CareerContextForm } from "@/components/career/CareerContextForm";
import { CareerTimelineReport } from "@/components/career/CareerTimelineReport";
import type { CareerContextInput } from "@/lib/pyjhora/types";

const MIN_CAREER_AGE = 20;

export function CareerTimelineSection() {
  const session = useChartSession();
  const [loading, setLoading] = useState(false);
  const [enrichLlm, setEnrichLlm] = useState(true);

  const data = session?.careerTimeline;
  const error = session?.careerTimelineError ?? null;
  const consolidated = session?.consolidated;
  const currentAge = useMemo(() => ageFromConsolidated(consolidated), [consolidated]);
  const isUnderAge = typeof currentAge === "number" && currentAge < MIN_CAREER_AGE;

  const run = useCallback(
    async (ctx: CareerContextInput) => {
      if (!consolidated) {
        patchChartSession({
          careerTimelineError:
            "Consolidated chart JSON is not available. Regenerate charts from Birth Data.",
        });
        return;
      }
      setLoading(true);
      patchChartSession({
        careerTimelineError: undefined,
        careerContextInput: ctx,
      });
      try {
        const result = await pyjhora.careerTimeline(consolidated, {
          careerContext: ctx,
          enrichLlm,
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
    },
    [consolidated, enrichLlm],
  );

  if (!session) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No chart session. Generate charts from Birth Data first.
        </CardContent>
      </Card>
    );
  }

  if (isUnderAge) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Info className="h-5 w-5 text-amber-600" />
            Career Timeline is for adult charts
          </CardTitle>
          <CardDescription>
            This chart is currently age {currentAge!.toFixed(1)}. The JyotishAI Career
            Timeline engine activates from age {MIN_CAREER_AGE}+ when there is a real working
            career to plot. For students (under {MIN_CAREER_AGE}), use the Education
            Analysis / Field Selection module instead — it picks aptitudes,
            field recommendations, and the right timing for studies.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <Link to="/education-analysis">
            <Button>Go to Education Analysis</Button>
          </Link>
          <Link to="/birth-data">
            <Button variant="outline">Switch chart</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Career Context</CardTitle>
              <CardDescription>
                Defaults are pre-filled from your chart
                {typeof currentAge === "number" ? ` (age ${currentAge.toFixed(1)})` : ""}.
                Adjust if you want, or click <em>Build</em> to run with these values.
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={loading}
              onClick={() => void run({ employment_status: "employed" })}
            >
              Quick run with defaults
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <CareerContextForm
            initial={session.careerContextInput}
            currentAge={currentAge}
            loading={loading}
            enrichLlm={enrichLlm}
            onEnrichLlmChange={setEnrichLlm}
            onSubmit={run}
          />
        </CardContent>
      </Card>

      {loading && !data ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin mx-auto mb-3" />
            Building the timeline{enrichLlm ? " with LLM narrative enrichment" : ""}…
            {enrichLlm ? <div className="text-xs mt-1">This may take 20-60 seconds.</div> : null}
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {data ? <CareerTimelineReport data={data} /> : null}
    </div>
  );
}
