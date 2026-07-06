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
        subtitle="Consolidated KP export JSON plus branded PDF templates (PDF generation coming soon)."
      />

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Consolidated KP export (JSON)</CardTitle>
          <CardDescription>
            Same payload as the legacy chart tool — generated via{" "}
            <code className="text-xs">POST /api/consolidated</code> when charts are saved.
          </CardDescription>
        </CardHeader>
        <CardContent>
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
