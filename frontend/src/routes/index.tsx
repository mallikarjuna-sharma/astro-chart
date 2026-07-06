import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { ProfileWizard } from "@/components/profile/ProfileWizard";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Profiles — JyotishAI" },
      { name: "description", content: "Create and manage up to four birth profiles." },
    ],
  }),
  component: HomePage,
});

function HomePage() {
  return (
    <div>
      <PageHeader
        title="Birth profiles"
        subtitle="Create up to four profiles per account. Fill in basic details, career field, and job analysis on one page — saved once, then read-only."
      />
      <ProfileWizard />
    </div>
  );
}
