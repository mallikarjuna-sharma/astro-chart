import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";
import { api, notifyStub } from "@/lib/api";

export const Route = createFileRoute("/career-timeline")({
  head: () => ({ meta: [{ title: "Career Timeline — JyotishAI" }] }),
  component: TimelinePage,
});

const TONE: Record<string, string> = {
  Growth: "bg-gold text-primary-foreground",
  Stable: "bg-secondary",
  Pivot: "bg-accent text-accent-foreground",
  Peak: "gradient-gold text-primary-foreground",
  Transformation: "bg-destructive text-destructive-foreground",
  Challenging: "bg-muted",
};

function TimelinePage() {
  const { data } = useQuery({ queryKey: ["timeline"], queryFn: api.getCareerTimeline });

  return (
    <div>
      <PageHeader
        title="Career Journey Timeline"
        subtitle="Color intensity = Four-System confidence. Income, job-change and growth windows."
        action={<Button variant="outline" onClick={() => notifyStub("Export timeline PDF")}>Export PDF</Button>}
      />

      <Card>
        <CardHeader><CardTitle>Timeline</CardTitle><CardDescription>Periods based on Dasha + Ashtakavarga + Shadbala concordance.</CardDescription></CardHeader>
        <CardContent>
          <div className="space-y-3">
            {data?.map((p, i) => (
              <div key={i} className="border border-border rounded-md p-4 flex items-start gap-4">
                <div className="w-24 shrink-0 text-sm text-muted-foreground tabular-nums">{p.period}</div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold">{p.title}</span>
                    <Badge className={TONE[p.type] ?? ""}>{p.type}</Badge>
                  </div>
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <span>Income index: <span className="text-gold font-medium">{p.income}/10</span></span>
                    <span>4-system score: <span className="text-gold font-medium">{p.score}</span></span>
                  </div>
                  <div className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full gradient-gold" style={{ width: p.score + "%" }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid md:grid-cols-2 gap-4 mt-6">
        <Card>
          <CardHeader><CardTitle>Job Change Signals</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-1.5">
            <div><Badge variant="outline" className="mr-2">Change</Badge> 3H + 12H sub-period active</div>
            <div><Badge variant="outline" className="mr-2">New opportunity</Badge> 6H + 11H activated</div>
            <div><Badge variant="outline" className="mr-2">Forced change</Badge> 8H + 12H strong</div>
            <div><Badge variant="outline" className="mr-2">Voluntary pivot</Badge> 9H + 10H active</div>
            <div><Badge variant="outline" className="mr-2">Foreign career</Badge> 9H + 12H + Rahu</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Income Windows</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-1.5">
            <div>Income peaks: 2H + 11H Dasha activation with high SAV bindus</div>
            <div>Income stress: 8H + 12H with low SAV</div>
            <div>Wealth accumulation: Jupiter periods + 2/5/11H + Jupiter Shadbala above threshold</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
