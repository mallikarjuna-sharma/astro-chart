import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, notifyStub } from "@/lib/api";

export const Route = createFileRoute("/student")({
  head: () => ({ meta: [{ title: "Student / Field Selection — JyotishAI" }] }),
  component: StudentPage,
});

function StudentPage() {
  const [level, setLevel] = useState("Grade 12");
  const { data } = useQuery({ queryKey: ["fields", level], queryFn: () => api.getFieldRecommendations(level) });

  const lastRun = (() => {
    try {
      const raw = sessionStorage.getItem("jyotish:lastFieldRun");
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  })();

  return (
    <div>
      <PageHeader title="Student Field / Branch Selection" subtitle="D24 Siddhamsa — dedicated education chart — integrated into Four-System Score." />

      {lastRun?.result && (
        <Card className="mb-6 border-gold/60">
          <CardHeader>
            <CardDescription>v{lastRun.result.engine_version} Field Determination Engine — last run</CardDescription>
            <CardTitle className="text-gold">{lastRun.result.primary.field}</CardTitle>
            <div className="text-xs text-muted-foreground">
              Reliability {Math.round(lastRun.result.reliability * 100)}% · Prompt {lastRun.promptChars} chars · Prashna used: {String(lastRun.result.prashna_used)}
            </div>
          </CardHeader>
          <CardContent className="grid md:grid-cols-3 gap-4 text-sm">
            {lastRun.result.field_scores.slice(0, 3).map((f: any) => (
              <div key={f.field} className="rounded-md border border-border p-3">
                <div className="text-xs text-muted-foreground">{f.cluster}</div>
                <div className="font-semibold text-gold">{f.field}</div>
                <div className="text-2xl tabular-nums">{f.score}</div>
                <p className="text-xs mt-1 text-muted-foreground">{f.rationale}</p>
              </div>
            ))}
            <div className="md:col-span-3 text-xs text-muted-foreground">
              <span className="text-foreground">Audit:</span> {lastRun.result.audit_trail.join(" • ")}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex items-end gap-3 mb-6">
        <div className="w-64">
          <label className="text-xs text-muted-foreground">Education level</label>
          <Select value={level} onValueChange={setLevel}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {["Grade 10","Grade 12","Undergraduate","Postgraduate"].map((l)=>(
                <SelectItem key={l} value={l}>{l}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" onClick={() => notifyStub("Re-run analysis")}>Re-run analysis</Button>
      </div>

      {data && (
        <div className="grid lg:grid-cols-3 gap-6">
          {[data.primary, data.secondary, data.tertiary].map((r, i) => (
            <Card key={i} className={i === 0 ? "border-gold/60" : ""}>
              <CardHeader>
                <CardDescription>{["Primary","Secondary","Tertiary"][i]} recommendation</CardDescription>
                <CardTitle className="text-gold">{r.field}</CardTitle>
                <div className="text-xs text-muted-foreground">Dominant planet: {r.dominantPlanet}</div>
              </CardHeader>
              <CardContent>
                <ConfidenceBadge score={r.score} />
              </CardContent>
            </Card>
          ))}

          <Card className="lg:col-span-2">
            <CardHeader><CardTitle>Insights</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div><span className="text-muted-foreground">Timing: </span>{data.timing}</div>
              <div><span className="text-muted-foreground">Foreign education: </span>{data.foreignEducation}</div>
              <div><span className="text-muted-foreground">Scholarship/aid: </span>{data.scholarship}</div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Fields to avoid</CardTitle><CardDescription>Multiple systems show challenges.</CardDescription></CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {data.avoid.map((f) => <Badge key={f} variant="destructive">{f}</Badge>)}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
