import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { FileText, Download, Share2 } from "lucide-react";
import { useChartSession } from "@/hooks/use-chart-session";
import { useDisplayName } from "@/hooks/use-display-name";
import { ConsolidatedExportPanel } from "@/components/charts/ConsolidatedExportPanel";

/** Outline of the consolidated JSON shape shown on /reports. */
const CONSOLIDATED_SCHEMA_OUTLINE = `{
  "system_config": { "ayanamsa", "current_date", ... },
  "student_context": { "dob", "tob", "pob", "student_preference", ... },
  "pyhora_calculations": {
    "divisional_charts": {
      "D1_rashi": {
        "factor": 1,
        "lagna": "Sagittarius",
        "lagna_degree": 12.9571,
        "planets": {
          "Sun": { "sign", "degree", "is_retrograde", "latitude", "shadbala_virupas" },
          ...
        }
      },
      "D2_hora": { ... },
      "D3_drekkana": { ... },
      "D4_chaturthamsa": { ... },
      "D5_panchamsa": { ... },
      "D6_shashthamsa": { ... },
      "D7_saptamsa": { ... },
      "D8_ashtamsa": { ... },
      "D9_navamsha": { "factor": 9, "lagna", "lagna_degree", "planets": { ... } },
      "D10_dashamsha": { ... },
      "D16_shodasamsa": { ... },
      "D24_siddhamsam": { ... },
      "D60_shashtiamsam": { ... },
      "D81_ashtottariamsa": { ... }
    },
    "kp_cusp_data": { "H1": { "sign", "degree", "sign_lord", "star_lord", ... }, ... },
    "kp_planetary_significators": { ... },
    "kn_rao_jaimini_data": { ... },
    "ashtakavarga_sav": { ... },
    "vimshottari_dasha_sequence": [ ... ]
  }
}`;

export const Route = createFileRoute("/reports")({
  head: () => ({ meta: [{ title: "Reports — JyotishAI" }] }),
  component: ReportsPage,
});

const TEMPLATES = [
  { id: "premium" as const, name: "Premium", pages: "30+", desc: "Full four-system, all modules, branded." },
  { id: "professional" as const, name: "Professional", pages: "15", desc: "Career + education focus with score breakdown." },
  { id: "summary" as const, name: "Summary", pages: "2", desc: "One-pager + score card. Great for sharing." },
];

function ReportsPage() {
  const session = useChartSession();
  const displayName = useDisplayName();
  const [generated, setGenerated] = useState<{ template: string; url: string; at: string }[]>([
    { template: "professional", url: "/reports/sample-professional.pdf", at: "2026-06-05" },
  ]);

  const gen = async (id: "premium" | "professional" | "summary") => {
    const r = await api.generateReport(id);
    setGenerated((g) => [{ template: r.template, url: r.url, at: r.generatedAt.slice(0, 10) }, ...g]);
    toast.success("Report generated", { description: r.url });
  };

  const chartLabel = session?.chartId ? `Chart ${session.chartId} · ${displayName}` : undefined;

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Consolidated export JSON with unified divisional charts (D1–D9, D10, D16, D24, D60, D81) — each varga includes lagna, degrees, and full planet placements."
      />

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Consolidated export (JSON)</CardTitle>
          <CardDescription>
            Generated via <code className="text-xs">POST /api/consolidated</code> when a profile is saved.
            Ayanamsa follows <code className="text-xs">birth_input.ayanamsa</code> (default Lahiri).
            All divisional charts live under <code className="text-xs">pyhora_calculations.divisional_charts</code> with
            the same structure as D1 (lagna, lagna_degree, planets with sign/degree).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <details className="rounded-md border border-border bg-muted/30 px-4 py-3 text-xs">
            <summary className="cursor-pointer font-medium text-foreground">JSON structure reference</summary>
            <pre className="mt-3 overflow-auto text-[11px] leading-relaxed text-muted-foreground whitespace-pre-wrap">
              {CONSOLIDATED_SCHEMA_OUTLINE}
            </pre>
          </details>
          <ConsolidatedExportPanel data={session?.consolidated} chartLabel={chartLabel} />
          {!session?.consolidated && (
            <div className="mt-4">
              <Link to="/">
                <Button variant="outline" size="sm">
                  Generate from Birth Data
                </Button>
              </Link>
            </div>
          )}
        </CardContent>
      </Card>

      <h2 className="text-lg font-semibold mb-3">PDF templates</h2>
      <div className="grid md:grid-cols-3 gap-4 mb-8">
        {TEMPLATES.map((t) => (
          <Card key={t.id}>
            <CardHeader>
              <CardTitle>{t.name}</CardTitle>
              <CardDescription>
                {t.pages} pages · {t.desc}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button className="w-full gradient-gold text-primary-foreground" onClick={() => gen(t.id)}>
                Generate
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent reports</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {generated.map((g, i) => (
              <div key={i} className="flex items-center gap-3 border border-border rounded-md p-3">
                <FileText className="w-5 h-5 text-gold" />
                <div className="flex-1">
                  <div className="text-sm font-medium">{g.url.split("/").pop()}</div>
                  <div className="text-xs text-muted-foreground">
                    {g.at} ·{" "}
                    <Badge variant="outline" className="ml-1">
                      {g.template}
                    </Badge>
                  </div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => toast("Download started")}>
                  <Download className="w-4 h-4" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => toast("Shared via WhatsApp")}>
                  <Share2 className="w-4 h-4" />
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
