import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/kn-rao")({
  head: () => ({ meta: [{ title: "KN Rao System — JyotishAI" }] }),
  component: KNRaoPage,
});

function EmptyState() {
  return (
    <Card>
      <CardContent className="py-8 text-center text-muted-foreground">
        <p className="mb-3">Jaimini data loads after Save & generate charts.</p>
        <Link to="/birth-data">
          <Button variant="outline">Enter birth data</Button>
        </Link>
      </CardContent>
    </Card>
  );
}

function KNRaoPage() {
  const session = useChartSession();
  const jaimini = session?.jaimini;

  if (!session?.birthInput) return (
    <div>
      <PageHeader title="KN Rao + Jaimini" subtitle="Chara karakas, special lagnas, chara dasha from PyJHora." />
      <EmptyState />
    </div>
  );

  return (
    <div>
      <PageHeader title="KN Rao + Jaimini" subtitle="From /api/jaimini — karakas, Karakamsa, Arudha/Upapada, Chara dasha." />
      <Tabs defaultValue="karakas">
        <TabsList>
          <TabsTrigger value="karakas">Chara Karakas</TabsTrigger>
          <TabsTrigger value="points">Special points</TabsTrigger>
          <TabsTrigger value="dasha">Chara Dasha</TabsTrigger>
        </TabsList>

        <TabsContent value="karakas" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Chara Karakas</CardTitle>
            </CardHeader>
            <CardContent>
              {jaimini?.karakas?.length ? (
                <table className="w-full text-sm">
                  <thead className="text-xs text-muted-foreground uppercase">
                    <tr>
                      <th className="text-left py-1">Karaka</th>
                      <th>Planet</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jaimini.karakas.map((k) => (
                      <tr key={k.karaka} className="border-t border-border">
                        <td className="py-1.5">{k.karaka}</td>
                        <td className="text-gold font-medium">{k.planet}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-muted-foreground text-sm">No karaka data.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="points" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Special points</CardTitle>
            </CardHeader>
            <CardContent className="grid sm:grid-cols-3 gap-4 text-sm">
              <div className="p-3 border border-border rounded-md">
                <div className="text-xs text-muted-foreground">Karakamsa</div>
                <div className="text-gold font-semibold">{jaimini?.karakamsa ?? "—"}</div>
              </div>
              <div className="p-3 border border-border rounded-md">
                <div className="text-xs text-muted-foreground">Arudha Lagna (AL)</div>
                <div className="text-gold font-semibold">{jaimini?.arudha_lagna ?? "—"}</div>
              </div>
              <div className="p-3 border border-border rounded-md">
                <div className="text-xs text-muted-foreground">Upapada Lagna (UL)</div>
                <div className="text-gold font-semibold">{jaimini?.upapada_lagna ?? "—"}</div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="dasha" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Chara Dasha (rasi maha periods)</CardTitle>
              {jaimini?.chara_dasha_error && (
                <CardDescription className="text-destructive">{jaimini.chara_dasha_error}</CardDescription>
              )}
            </CardHeader>
            <CardContent>
              {jaimini?.chara_dasha?.length ? (
                <table className="w-full text-sm">
                  <thead className="text-xs text-muted-foreground uppercase">
                    <tr>
                      <th className="text-left py-1">Rasi</th>
                      <th>Start</th>
                      <th>End</th>
                      <th>Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jaimini.chara_dasha.map((c, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="py-1.5 text-gold">{c.rasi}</td>
                        <td>{c.start_year}</td>
                        <td>{c.end_year}</td>
                        <td>{c.years}y</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-muted-foreground text-sm">Chara dasha unavailable.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
