import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { PucAnalysisSection } from "@/components/education/PucAnalysisSection";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/education-analysis/puc")({
  head: () => ({ meta: [{ title: "PUC Stream — Education Analysis — JyotishAI" }] }),
  component: PucAnalysisPage,
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

function PucAnalysisPage() {
  const session = useChartSession();

  if (!session?.birthInput) {
    return (
      <div>
        <PageHeader
          eyebrow="Education Analysis · PUC"
          title="PUC Stream"
          subtitle="Science, Commerce and Humanities direction for 11th–12th stream selection."
        />
        <EmptyState />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Education Analysis · PUC"
        title="PUC Stream"
        subtitle="Evidence-weighted stream and subject guidance for school-age charts (ages 15–17 default here)."
      />
      <PucAnalysisSection />
    </div>
  );
}
