import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { pyjhora } from "@/lib/pyjhora/client";
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

  const runAnalysis = useCallback(async () => {
    if (!consolidated) {
      patchChartSession({
        educationAnalysisError:
          "Consolidated chart JSON is not available. Open a profile from the Profiles page.",
      });
      return;
    }
    setLoading(true);
    patchChartSession({ educationAnalysisError: undefined });
    try {
      const result = await pyjhora.educationAnalysis(consolidated);
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
  }, [consolidated]);

  useEffect(() => {
    if (!data && !loading && !error && consolidated) {
      void runAnalysis();
    }
  }, [data, loading, error, consolidated, runAnalysis]);

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
          disabled={loading || !consolidated}
          onClick={() => void runAnalysis()}
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
            Consolidated JSON required. Open a profile from the Profiles page first.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
