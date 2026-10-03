import { useMemo, type ReactNode } from "react";
import { LineChart } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CareerRoadmapCard } from "@/components/career/timeline/CareerRoadmapCard";
import { CareerTimelineSidebar } from "@/components/career/timeline/CareerTimelineSidebar";
import { CareerTimelineSupplementActionable, CareerTimelineSupplementTechnical } from "@/components/career/timeline/CareerTimelineSupplement";
import { Callout, Panel } from "@/components/report/primitives";
import { useSelectedProfileName } from "@/hooks/use-display-name";
import { strengthColor } from "@/lib/career-timeline/helpers";
import type { CareerTimelineResponse } from "@/lib/pyjhora/types";

interface Props {
  data: CareerTimelineResponse;
}

export function CareerTimelineReport({ data }: Props) {
  const s = data.student;
  const displayName = useSelectedProfileName(s.name);
  const meta = data.report_meta;
  const warnings = (data.career_context?.warnings as string[] | undefined) ?? [];
  const generated = data.generated_at
    ? new Date(data.generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : "";

  const execItems = useMemo(
    () => [
      { label: "Primary opportunity", value: data.outcome.primary_opportunity, tone: "active" as const },
      { label: "Peak dasha lord", value: data.outcome.peak_md_lord, tone: "role" as const },
      { label: "Peak years", value: data.outcome.peak_years, tone: "comp" as const },
      { label: "Growth arc", value: data.outcome.growth_arc, tone: "foreign" as const },
    ],
    [data.outcome],
  );

  const periodLinks = data.blocks.map((b, i) => ({
    id: `period-${i + 1}`,
    label: `${i + 1}. ${(b.event_type ?? "Period").replace(/_/g, " ").replace(/^FORECAST /i, "")}`,
    dates: `${b.start_date?.slice(0, 10) ?? ""} → ${b.end_date?.slice(0, 10) ?? ""}`,
  }));

  return (
    <div className="w-full max-w-[1180px] mx-auto animate-rise pb-10 text-left">
      {/* Clean centered header matching UG Report */}
      <header className="text-center pb-2 mt-4">
        <div className="text-[11px] font-bold tracking-[0.22em] text-gold uppercase mb-3">
          JyotishAI Working-Career Engine
        </div>
        <h2 className="font-serif text-3xl md:text-[2.5rem] font-semibold text-foreground leading-tight">
          {displayName} · Timeline Report
        </h2>
        
        <p className="text-[0.95rem] text-muted-foreground mt-4 tracking-wide flex items-center justify-center gap-2 flex-wrap">
          {s.dob ? <span>Born {s.dob}</span> : null}
          {s.birth_place ? <span>· {s.birth_place}</span> : null}
          {typeof s.current_age === "number" ? <span>· age {Math.round(s.current_age)}</span> : null}
        </p>

        <div className="mt-6 flex flex-wrap justify-center items-center gap-2.5">
          {s.lagna_sign ? <HeaderTag>Lagna: {s.lagna_sign}</HeaderTag> : null}
          {s.h10_lord ? <HeaderTag>10H lord: {s.h10_lord}</HeaderTag> : null}
          {s.atmakaraka ? <HeaderTag>AK: {s.atmakaraka}</HeaderTag> : null}
          {data.llm_enriched ? <HeaderTag>AI-enriched</HeaderTag> : <HeaderTag>Deterministic</HeaderTag>}
          
          <div className="w-px h-4 bg-border mx-2 hidden sm:block" />
          
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-success/30 bg-success/10 text-success text-[11.5px] font-semibold tracking-wide">
            <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
            {meta?.display_confidence_label ?? "Moderate"} Confidence
          </div>
        </div>
      </header>

      <div className="pt-6 space-y-5 w-full max-w-[1180px] mx-auto">
        <section className="rounded-2xl border border-border bg-card p-5 md:p-6 shadow-sm mb-2">
          <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gold mb-2">Career Timing Report</div>
          <h2 className="font-serif text-xl font-semibold mb-2">Start with the action signal, then verify the astrology.</h2>
          <p className="text-[0.95rem] text-muted-foreground leading-relaxed mb-5">
            This report separates the reading into highly actionable career decisions and technical astrological evidence.
          </p>
          <div className="grid sm:grid-cols-3 gap-3 text-sm">
            <GuideStep n="1" title="Executive decision" sub="What should be done now" />
            <GuideStep n="2" title="Roadmap windows" sub="When each career phase activates" />
            <GuideStep n="3" title="Astro audit trail" sub="Astro Insights & Technical evidence" />
          </div>
        </section>

        {/* Full-width banners + executive summary — not confined to the main column */}
        {meta?.confidence_coverage_note ? (
          <Callout tone="warn" label="Confidence note">
            {meta.confidence_coverage_note}
          </Callout>
        ) : null}

        {meta?.retro_validation?.events_provided != null ? (
          <div className="w-full rounded-xl border border-border bg-card px-4 py-3 text-sm text-left">
            <strong>Retro-validation:</strong> {meta.retro_validation.events_matched ?? 0} of{" "}
            {meta.retro_validation.events_provided} provided past event(s) matched
            {meta.retro_validation.confidence_cap
              ? ` · confidence cap: ${meta.retro_validation.confidence_cap}`
              : ""}
            {meta.retro_validation.reason ? ` · ${meta.retro_validation.reason}` : ""}
          </div>
        ) : null}

        {warnings.length > 0 ? (
          <Callout tone="warn" label="Please note">
            {warnings.map((w, i) => (
              <div key={i}>· {w}</div>
            ))}
          </Callout>
        ) : null}

        <div className={`grid grid-cols-1 ${meta?.outcome_strength?.length ? "lg:grid-cols-[1.3fr_1fr]" : ""} gap-5 w-full items-stretch`}>
          {meta?.outcome_strength?.length ? (
            <Panel className="w-full h-full m-0 flex flex-col shadow-sm">
              <h2 className="font-semibold text-foreground mb-3 text-left">Title vs. Influence — Outcome Strength</h2>
              <div className="w-full overflow-x-auto flex-1">
                <table className="w-full min-w-[280px] text-sm border-collapse text-left">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="py-2 pr-3 text-[11px] uppercase tracking-wide text-muted-foreground text-left">
                        Outcome
                      </th>
                      <th className="py-2 text-[11px] uppercase tracking-wide text-muted-foreground text-left">
                        Strength
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {meta.outcome_strength.map((row) => (
                      <tr key={row.outcome} className="border-b border-border/50">
                        <td className="py-2.5 pr-3 text-left">{row.outcome}</td>
                        <td className="py-2.5 font-semibold text-left" style={{ color: strengthColor(row.strength) }}>
                          {row.strength}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          ) : null}

          <section className="w-full rounded-xl border border-border bg-border shadow-sm overflow-hidden flex flex-col">
            <div className="grid grid-cols-1 gap-px flex-1">
              {execItems.map(({ label, value, tone }) => (
                <div
                  key={label}
                  className={
                    "bg-card px-4 py-3 sm:px-5 flex flex-col justify-center text-left border-l-[3.5px] " +
                    (tone === "active"
                      ? "border-l-success"
                      : tone === "role"
                        ? "border-l-gold"
                        : tone === "comp"
                          ? "border-l-info"
                          : "border-l-royal")
                  }
                >
                  <div className="flex flex-row sm:flex-col lg:flex-row justify-between lg:items-center gap-1.5 lg:gap-4">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground whitespace-nowrap">
                      {label}
                    </div>
                    <div className="text-[0.95rem] font-semibold text-foreground leading-snug break-words text-left lg:text-right">
                      {value || "—"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <Tabs 
          id="timeline-tabs-container"
          defaultValue="roadmap" 
          className="w-full mt-4"
          onValueChange={() => {
            setTimeout(() => {
              const tabsEl = document.getElementById("timeline-tabs-container");
              if (tabsEl) {
                const y = tabsEl.getBoundingClientRect().top + window.scrollY - 80;
                window.scrollTo({ top: y, behavior: "smooth" });
              }
            }, 10);
          }}
        >
          <TabsList id="timeline-tabs" className="sticky top-[80px] z-40 w-full max-w-md mx-auto grid grid-cols-2 p-1 bg-muted/95 backdrop-blur-2xl rounded-xl shadow-lg border border-border/50 transition-all duration-300 mb-8">
            <TabsTrigger value="roadmap" className="rounded-lg text-[13px] font-semibold data-[state=active]:bg-card data-[state=active]:shadow-md data-[state=active]:text-gold transition-all duration-300">
              Career Roadmap
            </TabsTrigger>
            <TabsTrigger value="insights" className="rounded-lg text-[13px] font-semibold data-[state=active]:bg-card data-[state=active]:shadow-md data-[state=active]:text-gold transition-all duration-300">
              Astro Insights
            </TabsTrigger>
          </TabsList>

          <TabsContent value="roadmap" className="space-y-6 mt-0 animate-in fade-in-50 duration-500 text-left">
            {periodLinks.length ? (
              <nav className="w-full rounded-xl border border-border bg-card p-4 flex flex-wrap gap-2 items-center justify-start text-left shadow-sm">
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground mr-2">Jump to period</span>
                {periodLinks.map((p) => (
                  <a
                    key={p.id}
                    href={`#${p.id}`}
                    className="text-xs px-2.5 py-1 rounded-lg border border-border bg-muted/40 hover:bg-gold/10 hover:border-gold/30 transition-colors shadow-sm"
                    title={p.dates}
                  >
                    {p.label}
                  </a>
                ))}
              </nav>
            ) : null}

            {/* Multi-year roadmap */}
            <section id="career-roadmap" className="w-full space-y-5 text-left mt-2">
              <div className="flex items-center gap-2 text-left mb-2">
                <LineChart className="h-5 w-5 text-gold" />
                <h2 className="font-serif text-2xl font-semibold">Multi-Year Career Roadmap</h2>
              </div>
              {data.blocks.map((block, i) => (
                <CareerRoadmapCard key={`${block.md_lord}-${block.ad_lord}-${i}`} block={block} index={i} />
              ))}
            </section>

            <CareerTimelineSupplementActionable data={data} />
          </TabsContent>

          <TabsContent value="insights" className="space-y-8 mt-0 animate-in fade-in-50 duration-500">
            <div className="w-full space-y-8">
              <CareerTimelineSidebar insights={data.chart_insights} />
              <CareerTimelineSupplementTechnical data={data} />
            </div>
          </TabsContent>
        </Tabs>

        <footer className="text-center text-xs text-muted-foreground py-6 border-t border-border mt-8">
          JyotishAI Engine · {generated} · {data.engine_version} · For guidance only.
        </footer>
      </div>
    </div>
  );
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
    <div className="rounded-xl border border-border bg-muted/30 p-3">
      <strong className="text-gold">{n}</strong>
      <div className="font-semibold mt-1">{title}</div>
      <em className="text-xs text-muted-foreground not-italic">{sub}</em>
    </div>
  );
}
