import { useMemo, type ReactNode } from "react";
import { useSelectedProfileName } from "@/hooks/use-display-name";
import type { BusinessPredictionResponse } from "@/lib/pyjhora/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BusinessRoadmapTab } from "./BusinessRoadmapTab";
import { BusinessInsightsTab } from "./BusinessInsightsTab";
import { asString, asRecord, verdictLabel, getSectors } from "./business-report-utils";

interface Props {
  data: BusinessPredictionResponse;
}

function HeaderTag({ children }: { children: ReactNode }) {
  return (
    <span className="text-[11px] px-2.5 py-1 rounded-full border border-border bg-muted/40 text-muted-foreground font-medium tracking-wide shadow-sm">
      {children}
    </span>
  );
}

function GuideStep({ n, title, sub }: { n: string; title: string; sub: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface-soft/30 p-4">
      <div className="text-[11px] font-bold text-gold mb-1">{n}</div>
      <div className="font-semibold text-foreground text-[13px]">{title}</div>
      <div className="text-[12px] text-muted-foreground mt-0.5">{sub}</div>
    </div>
  );
}

export function BusinessReport({ data }: Props) {
  const report = data.report;
  const student = data.student;
  const displayName = useSelectedProfileName(student.name ?? report.name);

  const generated = useMemo(() => {
    if (data.generated_at) {
      return new Date(data.generated_at).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    }
    return report.generated;
  }, [data.generated_at, report.generated]);

  return (
    <div className="w-full max-w-[1180px] mx-auto animate-rise pb-10 text-left">
      {/* Clean centered header matching UG/Career Report */}
      <header className="text-center pb-2 mt-4">
        <div className="text-[11px] font-bold tracking-[0.22em] text-gold uppercase mb-3">
          JyotishAI Business Engine
        </div>
        <h2 className="font-serif text-3xl md:text-[2.5rem] font-semibold text-foreground leading-tight">
          {displayName} · Business Report
        </h2>
        
        <p className="text-[0.95rem] text-muted-foreground mt-4 tracking-wide flex items-center justify-center gap-2 flex-wrap">
          {student.dob ? <span>Born {student.dob}</span> : null}
          {student.birth_place ? <span>· {student.birth_place}</span> : null}
          {typeof student.current_age === "number" ? <span>· age {Math.round(student.current_age)}</span> : null}
        </p>

        <div className="mt-6 flex flex-wrap justify-center items-center gap-2.5">
          {student.lagna_sign ? <HeaderTag>Lagna: {student.lagna_sign}</HeaderTag> : null}
          {student.h10_lord ? <HeaderTag>10H lord: {student.h10_lord}</HeaderTag> : null}
          {student.atmakaraka ? <HeaderTag>AK: {student.atmakaraka}</HeaderTag> : null}
          
          <div className="w-px h-4 bg-border mx-2 hidden sm:block" />
          
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-info/30 bg-info/10 text-info text-[11.5px] font-semibold tracking-wide">
            <div className="w-1.5 h-1.5 rounded-full bg-info animate-pulse" />
            Model Status: {asString(data.model_status || data.prediction.model_status)}
          </div>
        </div>
      </header>

      <div className="pt-6 space-y-5 w-full max-w-[1180px] mx-auto">
        {/* ── At a Glance (4-Column Layout) ── */}
        <section className="w-full">
          <div className="mb-3">
            <h3 className="font-serif text-[1.1rem] font-bold text-foreground">At a Glance</h3>
            <p className="text-[12.5px] text-muted-foreground mt-0.5">
              The four headline facts from this report, gathered in one place.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Final Verdict */}
            <div className="bg-card px-4 py-3.5 rounded-xl border border-border shadow-sm flex flex-col justify-center border-l-[3.5px] border-l-gold">
              <div className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                Verdict<br/>Final Verdict
              </div>
              <div className="text-[15px] font-bold text-gold leading-tight mb-1">
                {verdictLabel(asString(asRecord(data.prediction.authoritative_recommendation).final_category) || asString(report.verdict.final_category))}
              </div>
              <div className="text-[10px] text-muted-foreground font-medium">
                Business promise: {(report.verdict.business_promise ?? 0).toFixed(1)}% · Job promise: {(report.verdict.job_promise ?? 0).toFixed(1)}%
              </div>
            </div>
            
            {/* Top-Fit Sector */}
            {(() => {
              const sectors = getSectors(data);
              const top = sectors?.[0];
              return top ? (
                <div className="bg-card px-4 py-3.5 rounded-xl border border-border shadow-sm flex flex-col justify-center border-l-[3.5px] border-l-slate-700">
                  <div className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                    Top-Fit Sector
                  </div>
                  <div className="text-[14px] font-bold text-foreground leading-tight mb-1">
                    {asString(top.label).replace(/_/g, " ")}
                  </div>
                  <div className="text-[11px] font-bold text-slate-500">
                    ({(top.score ?? 0).toFixed(1)}%)
                  </div>
                </div>
              ) : null;
            })()}

            {/* Nearest Favorable Window */}
            {(() => {
              const windows = report.timed_windows || [];
              const bestWindow = windows.find(w => (w.label || "").toUpperCase().includes("FAVORABLE")) || windows[0];
              return bestWindow ? (
                <div className="bg-card px-4 py-3.5 rounded-xl border border-border shadow-sm flex flex-col justify-center border-l-[3.5px] border-l-slate-700">
                  <div className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                    Nearest Favorable Window
                  </div>
                  <div className="text-[14px] font-bold text-foreground leading-tight mb-1">
                    {bestWindow.start_date} → {bestWindow.end_date}
                  </div>
                  <div className="text-[11.5px] font-medium text-slate-600">
                    {bestWindow.md_lord}/{bestWindow.ad_lord}
                  </div>
                </div>
              ) : null;
            })()}

            {/* Biggest Risk Flag */}
            <div className="bg-card px-4 py-3.5 rounded-xl border border-border shadow-sm flex flex-col justify-center border-l-[3.5px] border-l-slate-700">
              <div className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                Biggest Risk Flag
              </div>
              <div className="text-[12.5px] font-medium text-foreground leading-snug">
                {report.top_risk ? (report.top_risk.length > 100 ? `${report.top_risk.slice(0, 100)}…` : report.top_risk) : "None flagged"}
              </div>
            </div>
          </div>
        </section>


        <Tabs 
          id="biz-tabs-container"
          defaultValue="roadmap" 
          className="w-full mt-4"
          onValueChange={() => {
            setTimeout(() => {
              const tabsEl = document.getElementById("biz-tabs-container");
              if (tabsEl) {
                const y = tabsEl.getBoundingClientRect().top + window.scrollY - 80;
                window.scrollTo({ top: y, behavior: "smooth" });
              }
            }, 10);
          }}
        >
          <TabsList id="biz-tabs" className="sticky top-[80px] z-40 w-full max-w-md mx-auto grid grid-cols-2 p-1 bg-muted/95 backdrop-blur-2xl rounded-xl shadow-lg border border-border/50 transition-all duration-300 mb-8">
            <TabsTrigger value="roadmap" className="rounded-lg text-[13px] font-semibold data-[state=active]:bg-card data-[state=active]:shadow-md data-[state=active]:text-gold transition-all duration-300">
              Business Roadmap
            </TabsTrigger>
            <TabsTrigger value="insights" className="rounded-lg text-[13px] font-semibold data-[state=active]:bg-card data-[state=active]:shadow-md data-[state=active]:text-gold transition-all duration-300">
              Astro Insights
            </TabsTrigger>
          </TabsList>

          <TabsContent value="roadmap" className="space-y-6 mt-0 animate-in fade-in-50 duration-500 text-left">
            <BusinessRoadmapTab data={data} />
          </TabsContent>

          <TabsContent value="insights" className="space-y-8 mt-0 animate-in fade-in-50 duration-500">
            <BusinessInsightsTab data={data} />
          </TabsContent>
        </Tabs>

        <footer className="text-center text-xs text-muted-foreground py-6 border-t border-border mt-8">
          JyotishAI Engine · {generated} · For guidance only.
        </footer>
      </div>
    </div>
  );
}
