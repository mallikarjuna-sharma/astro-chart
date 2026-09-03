import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { ComingSoonCard } from "@/components/ComingSoonCard";
import { FileText } from "lucide-react";

export const Route = createFileRoute("/reports")({
  head: () => ({ meta: [{ title: "Reports — JyotishAI" }] }),
  component: ReportsPage,
});

function ReportsPage() {
  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="PDF reports, consolidated exports, and shareable summaries."
      />
      <ComingSoonCard
        icon={FileText}
        title="Reports"
        description="Premium, professional, and summary PDF templates plus consolidated export downloads are on the way. Chart analysis remains available from the sidebar."
        ctaHref="/"
        ctaLabel="Go to Profiles"
      />
    </div>
  );
}
