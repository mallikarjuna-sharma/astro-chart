import { createFileRoute, Link } from "@tanstack/react-router";
import { Loader2, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CareerTimelineSection, useCareerTimeline } from "@/components/career/CareerTimelineSection";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/career-timeline")({
  head: () => ({ meta: [{ title: "Job Timeline — JyotishAI" }] }),
  component: CareerTimelinePage,
});

function EmptyState() {
  return (
    <Card>
      <CardContent className="py-8 text-center text-muted-foreground">
        <p className="mb-3">Open a profile from the Profiles page first.</p>
        <Link to="/">
          <Button variant="outline">Go to Profiles</Button>
        </Link>
      </CardContent>
    </Card>
  );
}

function CareerTimelinePage() {
  const session = useChartSession();
  const { loading, error, data, run, isUnderAge, currentAge, MIN_CAREER_AGE } = useCareerTimeline();

  const refreshAction = session?.birthInput ? (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8 shrink-0 text-muted-foreground"
      disabled={loading}
      onClick={() => void run(true)}
      aria-label="Refresh analysis"
      title="Refresh analysis"
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
    </Button>
  ) : undefined;

  if (!session?.birthInput) {
    return (
      <div>
        <PageHeader
          eyebrow="Working career"
          title="Job Timeline"
          subtitle="How your working career unfolds — promotions, moves, foreign windows and timing."
        />
        <EmptyState />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Working career"
        title="Job Timeline"
        subtitle="How your working career unfolds — promotions, moves, foreign windows and timing."
        titleAction={refreshAction}
      />
      <CareerTimelineSection 
        loading={loading}
        error={error}
        data={data}
        hasSession={Boolean(session)}
        isUnderAge={isUnderAge}
        currentAge={currentAge}
        minCareerAge={MIN_CAREER_AGE}
      />
    </div>
  );
}
