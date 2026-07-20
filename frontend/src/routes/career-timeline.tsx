import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CareerTimelineSection } from "@/components/career/CareerTimelineSection";
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
      />
      <CareerTimelineSection />
    </div>
  );
}
