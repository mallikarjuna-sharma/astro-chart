import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, notifyStub } from "@/lib/api";

export const Route = createFileRoute("/confidence")({
  head: () => ({ meta: [{ title: "Four-System Score — JyotishAI" }] }),
  component: ConfidencePage,
});

function ConfidencePage() {
  const [topic, setTopic] = useState("Career direction");
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["confidence", topic], queryFn: () => api.getConfidenceScore(topic),
  });

  const sys = [
    { key: "kp", label: "KP — Krishnamurti Paddhati", max: 35 },
    { key: "knRao", label: "KN Rao — Chara Karaka + Jaimini", max: 30 },
    { key: "parashari", label: "Parashari — Ashtakavarga + Shadbala", max: 20 },
    { key: "prashna", label: "Prashna — Horary confirmation", max: 15 },
  ] as const;

  return (
    <div>
      <PageHeader title="Four-System Confidence Score" subtitle="Numerical concordance across KP, KN Rao, Parashari and Prashna." />

      <div className="flex items-end gap-3 mb-6 flex-wrap">
        <div className="w-72">
          <label className="text-xs text-muted-foreground">Topic</label>
          <Select value={topic} onValueChange={(v) => setTopic(v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {["Career direction","MBA vs MS","Start a business in 2027","Foreign job opportunity","Buy property in 2026"].map((t) => (
                <SelectItem key={t} value={t}>{t}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>Recompute</Button>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="bg-card-glass border-gold/30">
          <CardHeader><CardTitle>Score</CardTitle><CardDescription>{data?.badge}</CardDescription></CardHeader>
          <CardContent className="flex justify-center py-6">
            {data && <ConfidenceBadge score={data.total} size="lg" />}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>System Breakdown</CardTitle><CardDescription>Each system contributes independently.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            {data && sys.map((s) => {
              const v = (data.breakdown as any)[s.key] as number;
              const pct = (v / s.max) * 100;
              return (
                <div key={s.key}>
                  <div className="flex justify-between text-sm mb-1">
                    <span>{s.label}</span>
                    <span className="tabular-nums">{v} / {s.max}</span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div className="h-full gradient-gold transition-all" style={{ width: pct + "%" }} />
                  </div>
                </div>
              );
            })}
            {data && (
              <p className="text-sm text-muted-foreground italic pt-3 border-t border-border">{data.explanation}</p>
            )}
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => notifyStub("Open consultation booking")}>Book astrologer</Button>
              <Button size="sm" variant="outline" onClick={() => notifyStub("Export PDF")}>Export PDF</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
