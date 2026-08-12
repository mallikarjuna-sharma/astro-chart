import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AshtakavargaChart } from "@/components/charts/AshtakavargaChart";
import { useChartSession } from "@/hooks/use-chart-session";
import { RASI_NAMES } from "@/lib/rasi";

export const Route = createFileRoute("/parashari")({
  head: () => ({ meta: [{ title: "Parashari Strength — JyotishAI" }] }),
  component: ParashariPage,
});

/** Grid order and cell labels from the classic pyJHora ashtakavarga view. */
const BAV_GRIDS = [
  { contributor: "Lagna", label: "As", d1Body: "La" },
  { contributor: "Sun", label: "Su", d1Body: "Su" },
  { contributor: "Moon", label: "Mo", d1Body: "Mo" },
  { contributor: "Mars", label: "Ma", d1Body: "Ma" },
  { contributor: "Mercury", label: "Me", d1Body: "Me" },
  { contributor: "Jupiter", label: "Ju", d1Body: "Ju" },
  { contributor: "Venus", label: "Ve", d1Body: "Ve" },
  { contributor: "Saturn", label: "Sa", d1Body: "Sa" },
] as const;

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

  /** SAV bindus re-keyed to rasi index (0 = Aries) for the 4×4 grid. */
  const savPoints = useMemo(() => {
    const out = Array<number>(12).fill(0);
    (ashtaka?.sav ?? []).forEach((row, i) => {
      const rasi = RASI_NAMES.indexOf(String(row.rasi));
      out[rasi >= 0 ? rasi : i] = Number(row.points) || 0;
    });
    return out;
  }, [ashtaka]);

  const bavByContributor = useMemo(
    () => new Map((ashtaka?.bav ?? []).map((row) => [row.contributor, row])),
    [ashtaka],
  );

  /** D-1 rasi of each body short code, used to shade the occupied cell. */
  const d1RasiByBody = useMemo(() => {
    const chart = session?.divisionalBasic?.charts?.find((c) => c.factor === 1);
    const out = new Map<string, number>();
    for (const house of chart?.houses ?? []) {
      for (const body of house.bodies ?? []) out.set(body, house.rasi);
    }
    return out;
  }, [session]);

  const lagnaRasi = d1RasiByBody.get("La");
  const lagnaSign = lagnaRasi != null ? RASI_NAMES[lagnaRasi] : null;

  if (!session?.birthInput) {
    return (
      <div>
        <PageHeader
          title="Parashari Strength Analysis"
          subtitle="Shadbala · Ashtakavarga from PyJHora."
        />
        <EmptyState />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100dvh-10.5rem)] max-h-[calc(100dvh-10.5rem)] overflow-hidden">
      <PageHeader
        compact
        title="Parashari Strength Analysis"
        subtitle="Shadbala and Ashtakavarga on one page."
      />

      <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-3">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <Card className="min-h-0">
            <CardHeader className="py-2 px-3">
              <CardTitle className="text-sm font-semibold">Shadbala</CardTitle>
              {shadbala ? (
                <p className="text-[10px] text-muted-foreground">
                  Strongest: {shadbala.strongest ?? "—"} · Weakest: {shadbala.weakest ?? "—"} · 100%
                  = minimum required
                </p>
              ) : null}
            </CardHeader>
            <CardContent className="px-3 pb-3 pt-0">
              {shadbala?.rows?.length ? (
                <table className="w-full text-[11px]">
                  <thead className="text-[10px] text-muted-foreground uppercase">
                    <tr>
                      <th className="text-left py-0.5">Planet</th>
                      <th className="text-center">Rupas</th>
                      <th className="text-right">Strength %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shadbala.rows.map((r) => {
                      const strong = r.planet === shadbala.strongest;
                      const weak = r.planet === shadbala.weakest;
                      return (
                        <tr key={r.planet} className="border-t border-border/60">
                          <td
                            className={`py-0.5 ${strong ? "text-success font-bold" : weak ? "text-destructive font-bold" : "text-gold"}`}
                          >
                            {r.planet}
                          </td>
                          <td className="tabular-nums text-center">{r.rupas}</td>
                          <td className="text-right tabular-nums">{r.percentage}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <p className="text-muted-foreground text-xs">No shadbala data.</p>
              )}
            </CardContent>
          </Card>

          <Card className="min-h-0">
            <CardHeader className="py-2 px-3">
              <CardTitle className="text-sm font-semibold">Ashtakavarga (SAV)</CardTitle>
              {ashtaka?.sav_total != null ? (
                <p className="text-[10px] text-muted-foreground">
                  Sarvashtakavarga total: {ashtaka.sav_total}
                </p>
              ) : null}
            </CardHeader>
            <CardContent className="px-3 pb-3 pt-0">
              {ashtaka?.sav?.length ? (
                <table className="w-full text-[11px]">
                  <thead className="text-[10px] text-muted-foreground uppercase">
                    <tr>
                      <th className="text-left py-0.5">House</th>
                      <th className="text-center">Rasi</th>
                      <th className="text-right">Points</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ashtaka.sav.map((s, i) => (
                      <tr key={s.rasi ?? i} className="border-t border-border/60">
                        <td className="py-0.5">H{i + 1}</td>
                        <td className="text-center">{s.rasi}</td>
                        <td className="text-right tabular-nums font-semibold">{s.points}</td>
                      </tr>
                    ))}
                    <tr className="border-t-2 border-gold font-bold">
                      <td colSpan={2}>Total</td>
                      <td className="text-right">{ashtaka.sav_total}</td>
                    </tr>
                  </tbody>
                </table>
              ) : (
                <p className="text-muted-foreground text-xs">No ashtakavarga data.</p>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className="py-2 px-3">
            <CardTitle className="text-sm font-semibold">D-1 Ashtakavarga Charts</CardTitle>
            <p className="text-[10px] text-muted-foreground">
              Sarvashtakavarga (SAV) and Bhinnashtakavarga (BAV)
              {lagnaSign ? ` — with reference to ${lagnaSign}` : ""}. Positions in D-1 are
              highlighted.
            </p>
          </CardHeader>
          <CardContent className="px-3 pb-3 pt-0">
            {ashtaka?.sav?.length || ashtaka?.bav?.length ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 sm:gap-3">
                <AshtakavargaChart label="SAV" points={savPoints} total={ashtaka?.sav_total} />
                {BAV_GRIDS.map(({ contributor, label, d1Body }) => {
                  const row = bavByContributor.get(contributor);
                  return (
                    <AshtakavargaChart
                      key={contributor}
                      label={label}
                      points={row?.houses ?? []}
                      total={row?.total}
                      highlightRasi={d1RasiByBody.get(d1Body) ?? null}
                    />
                  );
                })}
              </div>
            ) : (
              <p className="text-muted-foreground text-xs">No ashtakavarga data.</p>
            )}
          </CardContent>
        </Card>

        <Card className="flex flex-col overflow-hidden">
          <CardHeader className="py-2 px-3 shrink-0">
            <CardTitle className="text-sm font-semibold">Bhinnashtakavarga (BAV)</CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-2 pt-0">
            {ashtaka?.bav?.length ? (
              <div className="overflow-auto border border-border rounded-md">
                <table className="text-[10px] w-full min-w-full">
                  <thead className="sticky top-0 bg-card z-10">
                    <tr className="border-b border-border">
                      <th className="text-left p-1.5 font-semibold">Contributor</th>
                      {Array.from({ length: 12 }, (_, i) => (
                        <th key={i} className="px-1 py-1.5 text-center font-semibold">
                          H{i + 1}
                        </th>
                      ))}
                      <th className="px-1.5 py-1.5 text-center font-semibold">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ashtaka.bav.map((b) => (
                      <tr key={b.contributor} className="border-t border-border/60">
                        <td className="p-1.5 text-gold whitespace-nowrap">{b.contributor}</td>
                        {b.houses.map((pts, i) => (
                          <td key={i} className="px-1 py-0.5 text-center tabular-nums">
                            {pts}
                          </td>
                        ))}
                        <td className="px-1.5 py-0.5 text-center font-semibold tabular-nums">
                          {b.total}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-muted-foreground text-xs px-1">No BAV contributor data.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
