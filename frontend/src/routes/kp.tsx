import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { PageSection } from "@/components/PageSection";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/kp")({
  head: () => ({ meta: [{ title: "KP Analysis — JyotishAI" }] }),
  component: KPPage,
});

function EmptyState() {
  return (
    <Card>
      <CardContent className="py-8 text-center text-muted-foreground">
        <p className="mb-3">KP data loads after you open a profile.</p>
        <Link to="/">
          <Button variant="outline">Go to Profiles</Button>
        </Link>
      </CardContent>
    </Card>
  );
}

function KPPage() {
  const session = useChartSession();
  const kp = session?.kp;
  const vim = session?.vimshottari;

  if (!session?.birthInput) {
    return (
      <div>
        <PageHeader title="KP Analysis" subtitle="Sign lords, star lords, sub lords from PyJHora." />
        <EmptyState />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <PageHeader
        title="KP Analysis"
        subtitle="KP system lords and Vimshottari dasha on one page."
      />

      <PageSection
        title="KP Lords"
        description="Body · Rasi · KP # · Sign / Star / Sub / Sub-sub lord"
      >
        <Card>
          <CardContent className="pt-6 overflow-x-auto">
            {kp?.rows?.length ? (
              <table className="w-full text-sm min-w-[36rem] border-collapse">
                <thead className="text-xs text-muted-foreground uppercase">
                  <tr>
                    <th className="text-left py-1 px-2">Body</th>
                    <th className="text-left py-1 px-2">Rasi</th>
                    <th className="text-right py-1 px-2">KP #</th>
                    <th className="text-left py-1 px-2">Sign lord</th>
                    <th className="text-left py-1 px-2">Star lord</th>
                    <th className="text-left py-1 px-2">Sub lord</th>
                    <th className="text-left py-1 px-2">Sub-sub</th>
                  </tr>
                </thead>
                <tbody>
                  {kp.rows.map((r) => (
                    <tr key={r.body} className="border-t border-border">
                      <td className="py-1.5 px-2 text-gold">{r.body}</td>
                      <td className="py-1.5 px-2">{r.rasi}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{r.kp_number}</td>
                      <td className="py-1.5 px-2">{r.sign_lord}</td>
                      <td className="py-1.5 px-2">{r.star_lord}</td>
                      <td className="py-1.5 px-2 text-gold">{r.sub_lord}</td>
                      <td className="py-1.5 px-2 text-muted-foreground">{r.sub_sub_lord}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-muted-foreground text-sm">No KP rows in session.</p>
            )}
          </CardContent>
        </Card>
      </PageSection>

      <PageSection
        title="Vimshottari Dasha"
        description={
          vim
            ? `Current mahadasha: ${vim.current_mahadasha ?? "—"} · Antardasha: ${vim.current_antardasha ?? "—"}`
            : undefined
        }
      >
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Mahadasha periods</CardTitle>
          </CardHeader>
          <CardContent>
            {vim?.periods?.length ? (
              <table className="w-full text-sm border-collapse">
                <thead className="text-xs text-muted-foreground uppercase">
                  <tr>
                    <th className="text-left py-1 px-2">Mahadasha</th>
                    <th className="text-left py-1 px-2">Start</th>
                    <th className="text-left py-1 px-2">End</th>
                  </tr>
                </thead>
                <tbody>
                  {vim.periods.map((p, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="py-1.5 px-2 text-gold">{p.planet}</td>
                      <td className="py-1.5 px-2 tabular-nums">{p.start}</td>
                      <td className="py-1.5 px-2 tabular-nums">{p.end ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-muted-foreground text-sm">No dasha periods in session.</p>
            )}
          </CardContent>
        </Card>
      </PageSection>
    </div>
  );
}
