import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/panchanga")({
  head: () => ({ meta: [{ title: "Panchanga — JyotishAI" }] }),
  component: PanchangaPage,
});

function PanchangaPage() {
  const session = useChartSession();
  const items = session?.panchanga?.items ?? [];

  if (!session?.birthInput) {
    return (
      <div>
        <PageHeader
          title="Panchanga at birth"
          subtitle="Tithi, Nakshatra, Yoga, Karana and related details at the moment of birth."
        />
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            <p className="mb-4">Panchanga is computed when you save birth data and generate charts.</p>
            <Link to="/birth-data">
              <Button className="gradient-gold text-primary-foreground">Go to Birth Data</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Panchanga at birth"
        subtitle={
          session.userInfo.display_name
            ? `${session.userInfo.display_name} · ${session.birthInput.place_label}`
            : session.birthInput.place_label
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>Birth-time panchanga</CardTitle>
          <CardDescription>
            From PyJHora <code className="text-xs">/api/panchanga</code>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {items.length > 0 ? (
            <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-3">
              {items.map((item) => (
                <div
                  key={item.label}
                  className="flex justify-between gap-4 border-b border-border/60 pb-2 text-sm"
                >
                  <dt className="text-muted-foreground">{item.label}</dt>
                  <dd className="font-semibold text-right text-gold">{item.value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-muted-foreground text-sm">No panchanga items in session.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
