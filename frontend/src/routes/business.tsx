import { createFileRoute, Link } from "@tanstack/react-router";
import { Loader2, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BusinessSection, useBusinessPrediction } from "@/components/business/BusinessSection";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/business")({
  head: () => ({ meta: [{ title: "Business — JyotishAI" }] }),
  component: BusinessPage,
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

function BusinessPage() {
  const session = useChartSession();
  const { loading, error, data, run } = useBusinessPrediction();

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
          eyebrow="Entrepreneurship"
          title="Business"
          subtitle="Business viability, best-fit sectors, and favorable timing from classical Vedic indicators."
        />
        <EmptyState />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Entrepreneurship"
        title="Business"
        subtitle="Business viability, best-fit sectors, and favorable timing from classical Vedic indicators."
        titleAction={refreshAction}
      />
      <BusinessSection 
        loading={loading}
        error={error}
        data={data}
        hasSession={Boolean(session)}
      />
    </div>
  );
}
