import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BusinessSection } from "@/components/business/BusinessSection";
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
    <div className="-mx-4 sm:-mx-6 md:-mx-8 max-w-none">
      <PageHeader
        eyebrow="Entrepreneurship"
        title="Business"
        subtitle="Business viability, best-fit sectors, and favorable timing from classical Vedic indicators."
        compact
      />
      <BusinessSection />
    </div>
  );
}
