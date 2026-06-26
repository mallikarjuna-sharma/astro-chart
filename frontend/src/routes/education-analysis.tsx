import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { EducationAnalysisSection } from "@/components/education/EducationAnalysisSection";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/education-analysis")({
  head: () => ({ meta: [{ title: "Education Analysis — JyotishAI" }] }),
  component: EducationAnalysisPage,
});

function EmptyState() {
  return (
    <Card>
      <CardContent className="py-8 text-center text-muted-foreground">
        <p className="mb-3">Run Save &amp; generate charts on Birth Data first.</p>
        <Link to="/birth-data">
          <Button variant="outline">Enter birth data</Button>
        </Link>
      </CardContent>
    </Card>
  );
}

function EducationAnalysisPage() {
  const session = useChartSession();

  if (!session?.birthInput) {
    return (
      <div>
        <PageHeader
          title="Education Analysis"
          subtitle="JyotishAI deterministic engine + Gemini field selection."
        />
        <EmptyState />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Education Analysis"
        subtitle="Ranked career fields from consolidated chart JSON · parent & astrologer views."
      />
      <EducationAnalysisSection />
    </div>
  );
}
