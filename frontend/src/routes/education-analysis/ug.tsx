import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { UgAnalysisSection } from "@/components/education/UgAnalysisSection";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/education-analysis/ug")({
  head: () => ({ meta: [{ title: "UG Career Field — Education Analysis — JyotishAI" }] }),
  component: UgAnalysisPage,
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

function UgAnalysisPage() {
  const session = useChartSession();

  if (!session?.birthInput) {
    return (
      <div>
        <PageHeader
          eyebrow="Education Analysis · UG"
          title="UG Career Field"
          subtitle="Ranked vocational fields and education routes for this chart."
        />
        <EmptyState />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Education Analysis · UG"
        title="UG Career Field"
        subtitle="Deterministic field scoring plus LLM narrative — undergraduate and career-route guidance."
      />
      <UgAnalysisSection />
    </div>
  );
}
