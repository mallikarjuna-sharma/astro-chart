import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { SouthIndianChart } from "@/components/charts/SouthIndianChart";
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
            <p className="mb-4">Charts load from your saved profile. Open or create one on the Profiles page.</p>
            <Link to="/">
              <Button className="gradient-gold text-primary-foreground">Go to Profiles</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100dvh-10.5rem)] max-h-[calc(100dvh-10.5rem)] overflow-hidden">
      <PageHeader
        compact
        title="Divisional Charts"
        subtitle={
          session.chartId
            ? `Chart ${session.chartId} · ${displayName} · ${allCharts.length} vargas`
            : `Generated via PyJHora · ${allCharts.length} vargas`
        }
      />

      <Tabs value={activeKey} onValueChange={setActive} className="flex flex-col flex-1 min-h-0">
        <div className="md:hidden shrink-0 mb-2">
          <label className="text-[10px] text-muted-foreground mb-1 block">Select chart</label>
          <Select value={activeKey} onValueChange={setActive}>
            <SelectTrigger className="h-8 text-xs">
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

        <TabsList className="hidden md:flex shrink-0 w-full h-8 flex-nowrap justify-start overflow-x-auto gap-0.5 p-0.5">
          {allCharts.map((c) => (
            <TabsTrigger
              key={c.factor}
              value={String(c.factor)}
              className="shrink-0 px-2.5 py-1 text-xs h-7"
            >
              D{c.factor}
            </TabsTrigger>
          ))}
        </TabsList>

        {allCharts.map((c) => (
          <TabsContent
            key={c.factor}
            value={String(c.factor)}
            className="flex-1 min-h-0 mt-2 data-[state=inactive]:hidden"
          >
            <Card className="border-border/80 h-full flex flex-col">
              <CardContent className="flex-1 min-h-0 p-3 md:p-4 flex flex-col gap-2">
                <div className="flex flex-col lg:flex-row gap-3 lg:gap-5 items-center lg:items-start flex-1 min-h-0">
                  <div className="shrink-0 w-full max-w-[min(34vh,17rem)] lg:max-w-[min(38vh,18rem)] mx-auto lg:mx-0">
                    <SouthIndianChart chart={c} meta={meta} compact />
                  </div>
                  <div className="w-full lg:flex-1 min-h-0 min-w-0 overflow-hidden">
                    <h3 className="text-[10px] font-medium text-muted-foreground mb-1.5 uppercase tracking-wide">
                      Graha by rasi
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-x-3 gap-y-0 text-[11px] leading-tight">
                      {(c.houses ?? []).map((h) => (
                        <div
                          key={h.rasi}
                          className="flex gap-1.5 border-b border-border/30 py-0.5 min-w-0"
                        >
                          <span className="text-muted-foreground w-14 shrink-0 truncate">
                            {h.rasi_name}
                          </span>
                          <span className="text-gold font-medium truncate">
                            {h.bodies.join(", ") || "—"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <p className="shrink-0 text-[10px] text-muted-foreground leading-snug">
                  Codes: La Lagna · Su Sun · Mo Moon · Ma Mars · Me Mercury · Ju Jupiter · Ve Venus · Sa Saturn · Ra Rahu · Ke Ketu
                </p>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
