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
import { D1BodyTable } from "@/components/charts/D1BodyTable";
import { useChartSession } from "@/hooks/use-chart-session";
import { useDisplayName } from "@/hooks/use-display-name";
import { pyjhora } from "@/lib/pyjhora/client";
import type { DivisionalChart } from "@/lib/pyjhora/types";
import { useQuery } from "@tanstack/react-query";
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

  const birthInput = session?.birthInput;
  const d1Bodies = useQuery({
    queryKey: ["d1-bodies", birthInput],
    queryFn: () => pyjhora.d1Bodies(birthInput!),
    enabled: Boolean(birthInput),
    staleTime: Infinity,
  });

  if (!session?.birthInput || allCharts.length === 0) {
    return (
      <div>
        <PageHeader
          title="Divisional Charts"
          subtitle="D1–D9 plus extended vargas (D10, D16, D24, D60, D81). Enter birth data and generate charts."
        />
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            <p className="mb-4">
              Charts load from your saved profile. Open or create one on the Profiles page.
            </p>
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
            className="flex-1 min-h-0 mt-2 overflow-y-auto pr-1 data-[state=inactive]:hidden"
          >
            <Card className="border-border/80 flex flex-col">
              <CardContent className="p-3 md:p-5 flex flex-col gap-3">
                <div className="flex flex-col lg:flex-row gap-4 lg:gap-6 items-stretch">
                  <div className="w-full lg:w-[48%] xl:w-[50%] shrink-0 min-h-[min(52vh,28rem)] flex">
                    <SouthIndianChart chart={c} meta={meta} size="fit" />
                  </div>
                  <div className="w-full lg:flex-1 min-h-0 min-w-0 flex flex-col">
                    <h3 className="text-xs md:text-sm font-medium text-muted-foreground mb-2 uppercase tracking-wide shrink-0">
                      Graha by rasi
                    </h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-1.5 text-sm md:text-[0.95rem] leading-snug flex-1 content-start">
                      {(c.houses ?? []).map((h) => (
                        <div
                          key={h.rasi}
                          className="flex gap-2 border-b border-border/40 py-1 min-w-0"
                        >
                          <span className="text-muted-foreground w-20 shrink-0">{h.rasi_name}</span>
                          <span className="text-gold font-medium break-words">
                            {h.bodies.join(", ") || "—"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <p className="shrink-0 text-xs text-muted-foreground leading-snug">
                  Codes: La Lagna · Su Sun · Mo Moon · Ma Mars · Me Mercury · Ju Jupiter · Ve Venus
                  · Sa Saturn · Ra Rahu · Ke Ketu
                </p>

                {c.factor === 1 ? (
                  <div className="flex flex-col gap-2 border-t border-border/60 pt-3">
                    <h3 className="text-xs md:text-sm font-medium text-muted-foreground uppercase tracking-wide">
                      Body positions
                    </h3>
                    {d1Bodies.data?.rows?.length ? (
                      <>
                        <D1BodyTable rows={d1Bodies.data.rows} />
                        <p className="text-xs text-muted-foreground leading-snug">
                          Karakas: AK Atma · AmK Amatya · BK Bhratru · MK Matru · PiK Pitru · PK
                          Putra · GK Gnati · DK Dara. (R) marks a retrograde graha.
                        </p>
                      </>
                    ) : d1Bodies.isPending ? (
                      <p className="text-xs text-muted-foreground">Loading body positions…</p>
                    ) : (
                      <p className="text-xs text-destructive">
                        Could not load body positions
                        {d1Bodies.error ? `: ${(d1Bodies.error as Error).message}` : "."}
                      </p>
                    )}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
