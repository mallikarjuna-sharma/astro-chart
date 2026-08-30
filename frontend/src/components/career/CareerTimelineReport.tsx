import { useMemo, type ReactNode } from "react";
import { LineChart } from "lucide-react";
import { CareerRoadmapCard } from "@/components/career/timeline/CareerRoadmapCard";
import { CareerTimelineSidebar } from "@/components/career/timeline/CareerTimelineSidebar";
import { CareerTimelineSupplement } from "@/components/career/timeline/CareerTimelineSupplement";
import { Callout, Panel } from "@/components/report/primitives";
import { useDisplayName } from "@/hooks/use-display-name";
import { strengthColor } from "@/lib/career-timeline/helpers";
import type { CareerTimelineResponse } from "@/lib/pyjhora/types";

interface Props {
  data: CareerTimelineResponse;
}

export function CareerTimelineReport({ data }: Props) {
  const s = data.student;
  const displayName = useDisplayName(s.name);
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
    <div className="w-full max-w-[1680px] mx-auto animate-rise pb-10 text-left">
      {/* Dark header */}
      <header className="relative overflow-hidden rounded-b-2xl bg-[#1A1A2E] text-white px-6 py-10 md:px-12">
        <div className="absolute top-0 right-0 w-72 h-72 rounded-full bg-gold/10 blur-3xl pointer-events-none" />
        <div className="relative z-10 flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="text-[10px] font-semibold tracking-[0.35em] text-gold uppercase mb-3 opacity-85">
              JyotishAI · Working-Career Engine
            </div>
            <h1 className="font-serif text-3xl md:text-[2.5rem] font-semibold leading-tight">{displayName}</h1>
            <p className="text-sm text-white/40 mt-2 tracking-wide">
              {s.dob ? `Born ${s.dob}` : null}
              {s.birth_place ? ` · ${s.birth_place}` : null}
              {typeof s.current_age === "number" ? ` · age ${Math.round(s.current_age)}` : null}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {s.lagna_sign ? <HeaderTag>Lagna: {s.lagna_sign}</HeaderTag> : null}
              {s.h10_lord ? <HeaderTag>10H lord: {s.h10_lord}</HeaderTag> : null}
              {s.atmakaraka ? <HeaderTag>AK: {s.atmakaraka}</HeaderTag> : null}
              {data.llm_enriched ? <HeaderTag>AI-enriched</HeaderTag> : <HeaderTag>Deterministic</HeaderTag>}
            </div>
          </div>
          <div className="shrink-0 sm:text-right">
            <div className="inline-block px-4 py-1.5 rounded-full text-xs font-semibold border border-success/30 bg-success/10 text-success">
              {meta?.display_confidence_label ?? "Moderate"}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-white/30 mt-2">Overall confidence</div>
          </div>
        </div>
      </header>

      <div className="px-4 md:px-5 pt-6 space-y-5 w-full">
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

        {meta?.outcome_strength?.length ? (
          <Panel className="w-full">
            <h2 className="font-semibold text-foreground mb-3 text-left">Title vs. Influence — Outcome Strength</h2>
            <div className="w-full overflow-x-auto">
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
                      <td className="py-2 pr-3 text-left">{row.outcome}</td>
                      <td className="py-2 font-semibold text-left" style={{ color: strengthColor(row.strength) }}>
                        {row.strength}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        ) : null}

        <section className="w-full rounded-xl border border-border bg-card shadow-sm overflow-hidden">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-border">
            {execItems.map(({ label, value, tone }) => (
              <div
                key={label}
                className={
                  "px-4 py-4 sm:px-5 text-left border-l-[3px] " +
                  (tone === "active"
                    ? "border-l-success"
                    : tone === "role"
                      ? "border-l-gold"
                      : tone === "comp"
                        ? "border-l-info"
                        : "border-l-royal")
                }
              >
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {label}
                </div>
                <div className="text-sm font-semibold text-foreground mt-1.5 leading-snug break-words">
                  {value || "—"}
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(280px,380px)_minmax(0,1fr)] gap-6 items-start w-full">
          <aside className="w-full xl:sticky xl:top-5 xl:max-h-[calc(100vh-2rem)] xl:overflow-y-auto">
            <CareerTimelineSidebar insights={data.chart_insights} />
          </aside>

          <main className="w-full min-w-0 space-y-5 text-left">
          {periodLinks.length ? (
            <nav className="w-full rounded-xl border border-border bg-card p-4 flex flex-wrap gap-2 items-center justify-start text-left">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground mr-2">Jump to period</span>
              {periodLinks.map((p) => (
                <a
                  key={p.id}
                  href={`#${p.id}`}
                  className="text-xs px-2.5 py-1 rounded-lg border border-border bg-muted/40 hover:bg-gold/10 hover:border-gold/30 transition-colors"
                  title={p.dates}
                >
                  {p.label}
                </a>
              ))}
            </nav>
          ) : null}

          {/* Multi-year roadmap */}
          <section id="career-roadmap" className="w-full space-y-5 text-left">
            <div className="flex items-center gap-2 text-left">
              <LineChart className="h-5 w-5 text-gold" />
              <h2 className="font-serif text-2xl font-semibold">Multi-Year Career Roadmap</h2>
            </div>
            {data.blocks.map((block, i) => (
              <CareerRoadmapCard key={`${block.md_lord}-${block.ad_lord}-${i}`} block={block} index={i} />
            ))}
          </section>

          <CareerTimelineSupplement data={data} />

          <section className="rounded-2xl border border-border bg-card p-5 md:p-6">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gold mb-2">Career Timing Report</div>
            <h2 className="font-serif text-xl font-semibold mb-2">Start with the action signal, then verify the astrology.</h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              This report separates three reading layers: practical career decision, family/parent guidance, and
              technical astrological evidence.
            </p>
            <div className="grid sm:grid-cols-3 gap-3 text-sm">
              <GuideStep n="1" title="Executive decision" sub="What should be done now" />
              <GuideStep n="2" title="Roadmap windows" sub="When each career phase activates" />
              <GuideStep n="3" title="Astro audit trail" sub="KP, D10, Jaimini, transit evidence" />
            </div>
          </section>

          <footer className="text-center text-xs text-muted-foreground py-4 border-t border-border">
            JyotishAI Engine · {generated} · {data.engine_version} · For guidance only.
          </footer>
          </main>
        </div>
      </div>
    </div>
  );
}

function HeaderTag({ children }: { children: ReactNode }) {
  return (
    <span className="text-[11px] px-2 py-0.5 rounded-full border border-white/15 bg-white/5 text-white/70">
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
