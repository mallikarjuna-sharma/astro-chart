import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Info, Loader2 } from "lucide-react";
import { defaultCareerContext } from "@/components/career/CareerContextForm";
import { pyjhora } from "@/lib/pyjhora/client";
import { ensureConsolidatedForEngine } from "@/lib/pyjhora/ensure-consolidated";
import { profilesApi } from "@/lib/profiles/client";
import { ageFromConsolidated, patchChartSession } from "@/lib/pyjhora/session";
import { useChartSession } from "@/hooks/use-chart-session";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CareerTimelineReport } from "@/components/career/CareerTimelineReport";
import type { CareerTimelineResponse } from "@/lib/pyjhora/types";

const MIN_CAREER_AGE = 20;

export function useCareerTimeline() {
  const session = useChartSession();
  const [loading, setLoading] = useState(false);

  const data = session?.careerTimeline;
  const error = session?.careerTimelineError ?? null;
  const consolidated = session?.consolidated;
  const profileId = session?.chartId;
  const careerContext = session?.careerContextInput;
  const currentAge = useMemo(() => ageFromConsolidated(consolidated), [consolidated]);
  const isUnderAge = typeof currentAge === "number" && currentAge < MIN_CAREER_AGE;

  const run = useCallback(async (forceRefresh = false) => {
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
      const result = profileId
        ? await profilesApi.careerTimeline(profileId, {
            careerContext: ctx,
            enrichLlm: true,
            refresh: forceRefresh,
          })
        : await pyjhora.careerTimeline(
            await ensureConsolidatedForEngine(
              session.birthInput,
              session.studentContext,
              consolidated,
              ctx,
            ),
            { careerContext: ctx, enrichLlm: true },
          );
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
  }, [careerContext, consolidated, currentAge, profileId, session?.birthInput, session?.studentContext]);

  useEffect(() => {
    if (!data && !loading && !error && session?.birthInput && !isUnderAge) {
      void run();
    }
  }, [data, loading, error, session?.birthInput, isUnderAge, run]);

  return { session, loading, error, data, run, isUnderAge, currentAge, MIN_CAREER_AGE };
}

type CareerTimelineSectionProps = {
  loading: boolean;
  error: string | null;
  data?: CareerTimelineResponse;
  hasSession: boolean;
  isUnderAge: boolean;
  currentAge?: number;
  minCareerAge: number;
};

export function CareerTimelineSection({ loading, error, data, hasSession, isUnderAge, currentAge, minCareerAge }: CareerTimelineSectionProps) {
  if (!hasSession) {
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
            Job Timeline is for adult charts
          </CardTitle>
          <CardDescription>
            This chart is currently age {currentAge?.toFixed(1)}. The Job Timeline engine activates
            from age {minCareerAge}+ when there is a real working career to plot. For students
            (under {minCareerAge}), use Education Analysis → UG instead.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <Link to="/education-analysis/ug">
            <Button>Go to Education Analysis</Button>
          </Link>
          <Link to="/">
            <Button variant="outline">Switch profile</Button>
          </Link>
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
            Building your job timeline (may take 20–60 seconds)…
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {data ? <CareerTimelineReport data={data} /> : null}

      {!loading && !data && !error ? (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground text-center">
            Open a profile from the Profiles page to load chart data first.
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
