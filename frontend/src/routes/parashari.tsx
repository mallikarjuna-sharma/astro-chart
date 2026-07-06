import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { PageSection } from "@/components/PageSection";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/parashari")({
  head: () => ({ meta: [{ title: "Parashari Strength — JyotishAI" }] }),
  component: ParashariPage,
});

function EmptyState() {
  return (
    <Card>
      <CardContent className="py-8 text-center text-muted-foreground">
        <p className="mb-3">Shadbala and Ashtakavarga load after Save & generate charts.</p>
        <Link to="/">
          <Button variant="outline">Go to Profiles</Button>
        </Link>
      </CardContent>
    </Card>
  );
}

function ParashariPage() {
  const session = useChartSession();
  const shadbala = session?.shadbala;
  const ashtaka = session?.ashtakavarga;

  if (!session?.birthInput) {
    return (
      <div>
        <PageHeader title="Parashari Strength Analysis" subtitle="Shadbala · Ashtakavarga from PyJHora." />
        <EmptyState />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <PageHeader
        title="Parashari Strength Analysis"
        subtitle="Shadbala and Ashtakavarga on one page."
      />

      <PageSection
        title="Shadbala"
        description={
          shadbala
            ? `Strongest: ${shadbala.strongest ?? "—"} · Weakest: ${shadbala.weakest ?? "—"} · 100% = minimum required`
            : undefined
        }
      >
        <Card>
          <CardContent className="pt-6">
            {shadbala?.rows?.length ? (
              <table className="w-full text-sm max-w-xl">
                <thead className="text-xs text-muted-foreground uppercase">
                  <tr>
                    <th className="text-left py-1">Planet</th>
                    <th>Rupas</th>
                    <th className="text-right">Strength %</th>
                  </tr>
                </thead>
                <tbody>
                  {shadbala.rows.map((r) => {
                    const strong = r.planet === shadbala.strongest;
                    const weak = r.planet === shadbala.weakest;
                    return (
                      <tr key={r.planet} className="border-t border-border">
                        <td
                          className={`py-1.5 ${strong ? "text-green-600 font-bold" : weak ? "text-destructive font-bold" : "text-gold"}`}
                        >
                          {r.planet}
                        </td>
                        <td className="tabular-nums">{r.rupas}</td>
                        <td className="text-right tabular-nums">{r.percentage}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="text-muted-foreground text-sm">No shadbala data.</p>
            )}
          </CardContent>
        </Card>
      </PageSection>

      <PageSection
        title="Ashtakavarga"
        description={
          ashtaka?.sav_total != null ? `Sarvashtakavarga total: ${ashtaka.sav_total}` : undefined
        }
      >
        <Card>
          <CardContent className="pt-6 space-y-6">
            {ashtaka?.sav?.length ? (
              <table className="w-full text-sm max-w-md">
                <thead className="text-xs text-muted-foreground uppercase">
                  <tr>
                    <th className="text-left py-1">House</th>
                    <th>Rasi</th>
                    <th className="text-right">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {ashtaka.sav.map((s) => (
                    <tr key={s.house} className="border-t border-border">
                      <td className="py-1">H{s.house}</td>
                      <td>{s.rasi}</td>
                      <td className="text-right tabular-nums font-semibold">{s.points}</td>
                    </tr>
                  ))}
                  <tr className="border-t-2 border-gold font-bold">
                    <td colSpan={2}>Total</td>
                    <td className="text-right">{ashtaka.sav_total}</td>
                  </tr>
                </tbody>
              </table>
            ) : null}

            {ashtaka?.bav?.length ? (
              <div className="overflow-x-auto max-h-80 border border-border rounded-md">
                <table className="text-xs w-full min-w-[40rem]">
                  <thead>
                    <tr>
                      <th className="text-left p-2">Contributor</th>
                      {Array.from({ length: 12 }, (_, i) => (
                        <th key={i} className="px-1 py-2">
                          H{i + 1}
                        </th>
                      ))}
                      <th className="px-2">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ashtaka.bav.map((b) => (
                      <tr key={b.contributor} className="border-t border-border">
                        <td className="p-2 text-gold">{b.contributor}</td>
                        {b.houses.map((pts, i) => (
                          <td key={i} className="px-1 py-1 text-center tabular-nums">
                            {pts}
                          </td>
                        ))}
                        <td className="px-2 font-semibold">{b.total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">No ashtakavarga data.</p>
            )}
          </CardContent>
        </Card>
      </PageSection>
    </div>
  );
}
