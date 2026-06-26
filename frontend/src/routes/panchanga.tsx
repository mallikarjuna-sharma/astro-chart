import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { ComingSoonCard } from "@/components/ComingSoonCard";
import { Sun } from "lucide-react";

export const Route = createFileRoute("/panchanga")({
  head: () => ({ meta: [{ title: "Panchanga — JyotishAI" }] }),
  component: PanchangaPage,
});

function PanchangaPage() {
  return (
    <div>
      <PageHeader
        title="Panchanga at birth"
        subtitle="Tithi, Nakshatra, Yoga, Karana, Vara and related birth-time details."
      />
      <ComingSoonCard
        icon={Sun}
        title="Panchanga at birth"
        description="A dedicated panchanga view with tithi, nakshatra, yoga, karana, moon rasi and more is on the way. Chart data is already computed in the background when you generate charts."
        ctaHref="/birth-data"
        ctaLabel="Enter birth data"
      />
    </div>
  );
}
