import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { ChartLegend, SouthIndianChart } from "@/components/charts/SouthIndianChart";
import { useChartSession } from "@/hooks/use-chart-session";
import { useDisplayName } from "@/hooks/use-display-name";
import type { DivisionalChart } from "@/lib/pyjhora/types";
import { useMemo, useState } from "react";

export const Route = createFileRoute("/charts")({
  head: () => ({ meta: [{ title: "Charts — JyotishAI" }] }),
  component: ChartsPage,
});

function mergeCharts(session: ReturnType<typeof useChartSession>): DivisionalChart[] {
  const basic = session?.divisionalBasic?.charts ?? [];
  const ext = session?.divisionalExtended?.charts ?? [];
  const byFactor = new Map<number, DivisionalChart>();
  for (const c of [...basic, ...ext]) byFactor.set(c.factor, c);
  return [...byFactor.values()].sort((a, b) => a.factor - b.factor);
}

function ChartsPage() {
  const session = useChartSession();
  const displayName = useDisplayName();
  const allCharts = useMemo(() => mergeCharts(session), [session]);
  const meta = session?.divisionalBasic?.meta ?? session?.divisionalExtended?.meta;
  const [active, setActive] = useState(String(allCharts[0]?.factor ?? "1"));

  const activeKey = allCharts.some((c) => String(c.factor) === active)
    ? active
    : String(allCharts[0]?.factor ?? "1");

  if (!session?.birthInput || allCharts.length === 0) {
    return (
      <div>
        <PageHeader
          title="Divisional Charts"
          subtitle="D1–D9 plus extended vargas (D10, D16, D24, D60, D81). Enter birth data and generate charts."
        />
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            <p className="mb-4">Charts load from the PyJHora API after birth data is saved.</p>
            <Link to="/birth-data">
              <Button className="gradient-gold text-primary-foreground">Go to Birth Data</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-none w-full overflow-x-hidden">
      <PageHeader
        title="Divisional Charts"
        subtitle={
          session.chartId
            ? `Chart ${session.chartId} · ${displayName} · ${allCharts.length} vargas`
            : `Generated via PyJHora · ${allCharts.length} vargas`
        }
      />

      <Tabs value={activeKey} onValueChange={setActive} className="w-full">
        {/* Mobile: dropdown picker */}
        <div className="md:hidden mb-4">
          <label className="text-xs text-muted-foreground mb-1.5 block">Select chart</label>
          <Select value={activeKey} onValueChange={setActive}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select chart" />
            </SelectTrigger>
            <SelectContent>
              {allCharts.map((c) => (
                <SelectItem key={c.factor} value={String(c.factor)}>
                  D{c.factor} — {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Tablet+: horizontally scrollable tab pills */}
        <TabsList className="hidden md:flex w-full h-auto flex-nowrap justify-start overflow-x-auto overflow-y-hidden gap-1 pb-1 scrollbar-thin">
          {allCharts.map((c) => (
            <TabsTrigger
              key={c.factor}
              value={String(c.factor)}
              className="shrink-0 px-3 py-1.5 text-sm"
            >
              D{c.factor}
            </TabsTrigger>
          ))}
        </TabsList>

        {allCharts.map((c) => (
          <TabsContent key={c.factor} value={String(c.factor)} className="mt-4 md:mt-6">
            <Card className="border-border/80">
              <CardHeader className="pb-2">
                <CardTitle className="text-xl">{c.name}</CardTitle>
                <CardDescription>South-Indian style · factor D{c.factor}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex flex-col xl:flex-row gap-8 xl:gap-12 items-center xl:items-start">
                  <SouthIndianChart chart={c} meta={meta} size="large" />
                  <div className="w-full xl:flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">
                      Graha by rasi
                    </h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
                      {(c.houses ?? []).map((h) => (
                        <div
                          key={h.rasi}
                          className="flex gap-2 border-b border-border/40 py-1.5 min-w-0"
                        >
                          <span className="text-muted-foreground w-24 shrink-0 truncate">
                            {h.rasi_name}
                          </span>
                          <span className="text-gold font-medium break-words">
                            {h.bodies.join(", ") || "—"}
                          </span>
                        </div>
                      ))}
                    </div>
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
