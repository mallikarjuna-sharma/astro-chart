import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { BirthChartTable } from "@/components/charts/BirthChartTable";
import { ChartLegend, SouthIndianChart } from "@/components/charts/SouthIndianChart";
import { loadChartSession } from "@/lib/pyjhora/session";
import type { DivisionalChart } from "@/lib/pyjhora/types";
import { useMemo } from "react";

export const Route = createFileRoute("/charts")({
  head: () => ({ meta: [{ title: "Charts — JyotishAI" }] }),
  component: ChartsPage,
});

function ChartsPage() {
  const session = useMemo(() => loadChartSession(), []);

  const allCharts = useMemo(() => {
    const basic = session?.divisionalBasic?.charts ?? [];
    const ext = session?.divisionalExtended?.charts ?? [];
    const byFactor = new Map<number, DivisionalChart>();
    for (const c of [...basic, ...ext]) byFactor.set(c.factor, c);
    return [...byFactor.values()].sort((a, b) => a.factor - b.factor);
  }, [session]);

  const meta = session?.divisionalBasic?.meta ?? session?.divisionalExtended?.meta;

  if (!session?.d1Table) {
    return (
      <div>
        <PageHeader
          title="Divisional Charts"
          subtitle="No chart data yet. Enter birth data and run Save & generate charts."
        />
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            <p className="mb-4">Charts are loaded from the PyJHora API after birth data is saved.</p>
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
        title="Divisional Charts"
        subtitle={
          session.chartId
            ? `Chart ${session.chartId} · ${session.userInfo.display_name}`
            : "Generated via PyJHora Swiss Ephemeris"
        }
      />

      <div className="mb-8">
        <BirthChartTable data={session.d1Table} />
      </div>

      <Tabs defaultValue={String(allCharts[0]?.factor ?? "1")}>
        <TabsList className="flex-wrap h-auto">
          {allCharts.map((c) => (
            <TabsTrigger key={c.factor} value={String(c.factor)}>
              D{c.factor}
            </TabsTrigger>
          ))}
        </TabsList>
        {allCharts.map((c) => (
          <TabsContent key={c.factor} value={String(c.factor)} className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>{c.name}</CardTitle>
                <CardDescription>South-Indian style grid from PyJHora</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col lg:flex-row gap-8 items-start">
                  <SouthIndianChart chart={c} meta={meta} />
                  <div className="flex-1 text-sm space-y-2">
                    {(c.houses ?? []).map((h) => (
                      <div key={h.rasi} className="flex gap-2 border-b border-border/40 py-1">
                        <span className="text-muted-foreground w-24 shrink-0">{h.rasi_name}</span>
                        <span className="text-gold font-medium">{h.bodies.join(", ") || "—"}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <ChartLegend />
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
