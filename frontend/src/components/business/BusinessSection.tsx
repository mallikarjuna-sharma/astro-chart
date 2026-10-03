import { useCallback, useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { pyjhora } from "@/lib/pyjhora/client";
import { ensureConsolidatedForEngine } from "@/lib/pyjhora/ensure-consolidated";
import { profilesApi } from "@/lib/profiles/client";
import { patchChartSession } from "@/lib/pyjhora/session";
import { useChartSession } from "@/hooks/use-chart-session";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { BusinessReport } from "@/components/business/BusinessReport";
import type { BusinessPredictionResponse } from "@/lib/pyjhora/types";

export function useBusinessPrediction() {
  const session = useChartSession();
  const [loading, setLoading] = useState(false);

  const data = session?.businessPrediction;
  const error = session?.businessPredictionError ?? null;
  const consolidated = session?.consolidated;
  const profileId = session?.chartId;

  const run = useCallback(async (forceRefresh = false) => {
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
      const result = profileId
        ? await profilesApi.businessPrediction(profileId, { refresh: forceRefresh })
        : await pyjhora.businessPrediction(
            await ensureConsolidatedForEngine(
              session.birthInput,
              session.studentContext,
              consolidated,
              session.careerContextInput,
            ),
          );
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
  }, [consolidated, profileId, session?.birthInput, session?.careerContextInput, session?.studentContext]);

  useEffect(() => {
    if (!data && !loading && !error && session?.birthInput) {
      void run();
    }
  }, [data, loading, error, session?.birthInput, run]);

  return { session, loading, error, data, run };
}

type BusinessSectionProps = {
  loading: boolean;
  error: string | null;
  data?: BusinessPredictionResponse;
  hasSession: boolean;
};

export function BusinessSection({ loading, error, data, hasSession }: BusinessSectionProps) {
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
    <div className="space-y-4">
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
