import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ChevronDown, ChevronUp, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

function highlightJson(jsonStr: string): string {
  const esc = jsonStr
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return esc.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false)\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)/g,
    (match) => {
      let cls = "text-amber-400";
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? "text-sky-400" : "text-sky-200";
      } else if (/true|false/.test(match)) {
        cls = "text-rose-400";
      } else if (/null/.test(match)) {
        cls = "text-violet-400";
      }
      return `<span class="${cls}">${match}</span>`;
    },
  );
}

interface ConsolidatedExportProps {
  data: Record<string, unknown> | undefined;
  chartLabel?: string;
}

export function ConsolidatedExportPanel({ data, chartLabel }: ConsolidatedExportProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [copied, setCopied] = useState(false);

  const rawJson = useMemo(() => (data ? JSON.stringify(data, null, 2) : ""), [data]);
  const html = useMemo(() => (rawJson ? highlightJson(rawJson) : ""), [rawJson]);

  const copy = async () => {
    if (!rawJson) return;
    try {
      await navigator.clipboard.writeText(rawJson);
      setCopied(true);
      toast.success("Copied consolidated JSON");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy to clipboard");
    }
  };

  if (!data) {
    return (
      <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        Consolidated export appears here after you save a profile with charts.
      </div>
    );
  }

  const sys = data.system_config as { ayanamsa?: string; ayanamsa_mode?: string } | undefined;
  const ayanamsaLabel = sys?.ayanamsa ?? sys?.ayanamsa_mode;

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 bg-muted/40 border-b border-border">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm">Consolidated export (JSON)</h3>
          {chartLabel && (
            <p className="text-xs text-muted-foreground truncate">{chartLabel}</p>
          )}
          {ayanamsaLabel && (
            <p className="text-xs text-muted-foreground">Ayanamsa: {ayanamsaLabel}</p>
          )}
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => setCollapsed((c) => !c)}>
          {collapsed ? (
            <>
              <ChevronDown className="w-4 h-4 mr-1" /> Expand
            </>
          ) : (
            <>
              <ChevronUp className="w-4 h-4 mr-1" /> Collapse
            </>
          )}
        </Button>
        <Button
          type="button"
          variant={copied ? "default" : "outline"}
          size="sm"
          className={cn(copied && "bg-green-600 hover:bg-green-600")}
          onClick={copy}
        >
          <Copy className="w-4 h-4 mr-1" />
          {copied ? "Copied!" : "Copy"}
        </Button>
      </div>
      {!collapsed && (
        <pre
          className="m-0 p-4 overflow-auto max-h-[32rem] text-xs leading-relaxed font-mono bg-[#0f1117] text-neutral-200"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )}
    </div>
  );
}
