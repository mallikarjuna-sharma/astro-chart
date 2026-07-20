import { useMemo, type ReactNode } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Dot,
} from "recharts";
import {
  Globe2,
  MapPin,
  TrendingUp,
  Calendar,
  Sparkles,
  Briefcase,
  CalendarClock,
  Users,
  Timer,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Callout,
  Meter,
  Panel,
  ProseBlock,
  ReportShell,
  SectionTitle,
  StatTile,
  Tag,
  type Tone,
} from "@/components/report/primitives";
import { useDisplayName } from "@/hooks/use-display-name";
import type {
  CareerForeignOpportunity,
  CareerTimelineBlock,
  CareerTimelineResponse,
  CareerTrajectoryPoint,
} from "@/lib/pyjhora/types";

interface Props {
  data: CareerTimelineResponse;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function toneFromColour(c?: string): Tone {
  switch ((c ?? "").toLowerCase()) {
    case "peak":
    case "green":
    case "favourable":
    case "favorable":
    case "high":
      return "success";
    case "neutral":
    case "amber":
    case "moderate":
    case "caution":
      return "warn";
    case "avoid":
    case "red":
    case "low":
      return "danger";
    default:
      return "muted";
  }
}

function fmtDate(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

// ─── Root ────────────────────────────────────────────────────────────────────

export function CareerTimelineReport({ data }: Props) {
  const s = data.student;
  const displayName = useDisplayName(s.name);
  const generated = data.generated_at
    ? new Date(data.generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : "";
  const warnings = (data.career_context?.warnings as string[] | undefined) ?? [];

  const foreignCount = data.foreign_opportunities?.length ?? 0;
  const mt = data.micro_timing ?? {};
  const hasTiming = !!(
    mt.negotiation_heatmap ||
    mt.stakeholder_radar ||
    mt.whatif_scenarios ||
    mt.hora_timing
  );

  return (
    <ReportShell>
      {/* Hero */}
      <Panel>
        <div className="text-[11px] font-bold tracking-[0.22em] text-gold uppercase mb-2">
          JyotishAI · Working-Career Engine
        </div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="font-serif text-2xl md:text-[2rem] font-semibold text-foreground leading-tight">
              {displayName} · Job Timeline
            </h2>
            <p className="text-sm text-muted-foreground mt-1.5">
              {s.dob ? `Born ${s.dob}` : null}
              {s.birth_place ? ` · ${s.birth_place}` : null}
              {typeof s.current_age === "number" ? ` · age ${Math.round(s.current_age)}` : null}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 justify-end">
            {data.llm_enriched ? (
              <Tag tone="gold">AI-enriched narratives</Tag>
            ) : (
              <Tag tone="muted">Deterministic narratives</Tag>
            )}
            {s.active_dasha_lord ? <Tag tone="royal">Active MD: {s.active_dasha_lord}</Tag> : null}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-1.5">
          {s.lagna_sign ? <Tag>Lagna: {s.lagna_sign}{s.lagna_lord ? ` (${s.lagna_lord})` : ""}</Tag> : null}
          {s.h10_lord ? <Tag>10H lord: {s.h10_lord}</Tag> : null}
          {s.atmakaraka ? <Tag>Atmakaraka: {s.atmakaraka}</Tag> : null}
          {s.amatyakaraka ? <Tag>Amatyakaraka: {s.amatyakaraka}</Tag> : null}
        </div>

        {warnings.length > 0 ? (
          <Callout tone="warn" label="Please note" className="mt-4">
            {warnings.map((w, i) => (
              <div key={i}>· {w}</div>
            ))}
          </Callout>
        ) : null}
      </Panel>

      {/* At-a-glance outcome */}
      <OutcomeStats data={data} />

      {/* Grouped detail */}
      <Tabs defaultValue="trajectory" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="trajectory">Trajectory</TabsTrigger>
          <TabsTrigger value="timeline">Timeline detail</TabsTrigger>
          <TabsTrigger value="windows">
            Windows & timing{foreignCount ? ` (${foreignCount})` : ""}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="trajectory" className="mt-5 space-y-5">
          <TrajectoryChart points={data.trajectory} />
          <AnnualCalendar entries={data.calendar} />
        </TabsContent>

        <TabsContent value="timeline" className="mt-5 space-y-5">
          <TimelineBlocks blocks={data.blocks} />
          <MDArcs arcs={data.md_arcs} />
        </TabsContent>

        <TabsContent value="windows" className="mt-5 space-y-5">
          <ForeignOpportunities items={data.foreign_opportunities} meta={data.foreign_meta} />
          {hasTiming ? <MicroTiming mt={mt} /> : null}
          {!foreignCount && !hasTiming ? (
            <Panel>
              <p className="text-sm text-muted-foreground text-center py-4">
                No foreign windows or micro-timing signals were computed for this chart.
              </p>
            </Panel>
          ) : null}
        </TabsContent>
      </Tabs>

      <footer className="text-center text-xs text-muted-foreground py-4 border-t border-border">
        JyotishAI Engine · {generated} · {data.engine_version} · For guidance only.
      </footer>
    </ReportShell>
  );
}

// ─── Outcome stats ───────────────────────────────────────────────────────────

function OutcomeStats({ data }: { data: CareerTimelineResponse }) {
  const o = data.outcome;
  const items: Array<{ label: string; value: string; icon: typeof TrendingUp }> = [
    { label: "Primary opportunity", value: o.primary_opportunity, icon: TrendingUp },
    { label: "Peak dasha lord", value: o.peak_md_lord, icon: Sparkles },
    { label: "Peak years", value: o.peak_years, icon: Calendar },
    { label: "Growth arc", value: o.growth_arc, icon: Briefcase },
  ];
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {items.map(({ label, value, icon: Icon }) => (
        <div key={label} className="rounded-xl border border-border bg-surface-soft/60 px-4 py-3.5">
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            <Icon className="h-3.5 w-3.5" />
            {label}
          </div>
          <div className="text-[0.98rem] font-semibold text-gold mt-1.5 leading-snug">{value || "—"}</div>
        </div>
      ))}
    </div>
  );
}

// ─── Trajectory line chart ───────────────────────────────────────────────────

function TrajectoryChart({ points }: { points: CareerTrajectoryPoint[] }) {
  const chartData = useMemo(
    () =>
      points.map((p) => ({
        label: p.label,
        score: p.score,
        color: p.color,
        event: p.event_type.replace(/_/g, " ").toLowerCase(),
      })),
    [points],
  );

  if (!points.length) return null;

  return (
    <Panel>
      <SectionTitle title="Career trajectory" chip="Antardasha score %" chipTone="gold" icon={<TrendingUp className="h-5 w-5 text-gold" />} />
      <p className="text-xs text-muted-foreground -mt-2 mb-4">
        How favourable each Antardasha period is for your career, across the projected window. Dot colour marks the
        dominant event type.
      </p>
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <LineChart data={chartData} margin={{ top: 16, right: 24, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} stroke="var(--border)" interval={0} angle={-12} dy={6} height={50} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} stroke="var(--border)" />
            <Tooltip
              contentStyle={{ borderRadius: 10, border: "1px solid var(--border)", background: "var(--popover)", color: "var(--popover-foreground)" }}
              labelStyle={{ color: "var(--popover-foreground)" }}
              itemStyle={{ color: "var(--popover-foreground)" }}
              formatter={(v: number) => [`${v}`, "Score"]}
              labelFormatter={(label: string, p) => {
                const evt = p && p[0] ? (p[0].payload as { event?: string }).event : "";
                return `${label}${evt ? ` · ${evt}` : ""}`;
              }}
            />
            <Line
              type="monotone"
              dataKey="score"
              stroke="var(--gold)"
              strokeWidth={2.5}
              dot={(props) => {
                const { cx, cy, payload, index } = props as {
                  cx: number;
                  cy: number;
                  payload: { color: string };
                  index: number;
                };
                return <Dot key={index} cx={cx} cy={cy} r={5} fill={payload.color} stroke="var(--background)" strokeWidth={1.5} />;
              }}
              activeDot={{ r: 7 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

// ─── Annual Calendar ─────────────────────────────────────────────────────────

function AnnualCalendar({ entries }: { entries: CareerTimelineResponse["calendar"] }) {
  if (!entries.length) return null;
  return (
    <Panel>
      <SectionTitle title="Year-by-year calendar" chip="Best period per year" icon={<CalendarClock className="h-5 w-5 text-gold" />} />
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {entries.map((e) => (
          <div
            key={e.year}
            className="rounded-xl border bg-surface-soft/60 p-3 text-center"
            style={{ borderColor: e.color + "55" }}
          >
            <div className="text-xs text-muted-foreground">{e.year}</div>
            <div className="text-2xl font-bold tabular-nums" style={{ color: e.color }}>
              {e.score}
            </div>
            <div className="text-[11px] font-medium leading-tight mt-1 capitalize">
              {e.event_type.replace(/_/g, " ").toLowerCase()}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">AD: {e.ad_lord}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ─── Timeline blocks (AD level) ──────────────────────────────────────────────

function TimelineBlocks({ blocks }: { blocks: CareerTimelineBlock[] }) {
  if (!blocks.length) return null;
  return (
    <Panel>
      <SectionTitle title="Period-by-period breakdown" chip="Antardasha detail" chipTone="info" />
      <p className="text-xs text-muted-foreground -mt-2 mb-4">
        Each row is a sub-period (Antardasha). Expand one to see what it means in plain language, the astrology
        behind it, and the finer sub-periods inside it.
      </p>
      <Accordion type="multiple" className="space-y-2">
        {blocks.map((b, i) => (
          <BlockItem key={`${b.md_lord}-${b.ad_lord}-${i}`} block={b} idx={i} />
        ))}
      </Accordion>
    </Panel>
  );
}

function BlockItem({ block, idx }: { block: CareerTimelineBlock; idx: number }) {
  const score = Math.round((block.career_score ?? 0) * 100);
  const eventLabel = (block.event_type ?? "STABILITY").replace(/_/g, " ").toLowerCase();
  const isCurrent = !!block.is_current;
  const isPrimary = !!block.is_primary_opportunity;
  const pds = block.pratyantardashas ?? [];

  return (
    <AccordionItem value={`b-${idx}`} className="border border-border rounded-xl px-4 bg-surface-soft/30">
      <AccordionTrigger className="hover:no-underline py-3">
        <div className="flex flex-1 items-center gap-3 text-left">
          <div className="text-xs tabular-nums text-muted-foreground w-28 shrink-0">
            {fmtDate(block.start_date)} → {fmtDate(block.end_date)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {block.md_lord} – {block.ad_lord}
              </span>
              <Tag tone="muted" className="capitalize">{eventLabel}</Tag>
              {isCurrent ? <Tag tone="gold">Current</Tag> : null}
              {isPrimary ? <Tag tone="royal">Primary opportunity</Tag> : null}
              {block.foreign_opportunity ? (
                <Tag tone="info"><Globe2 className="w-3 h-3" /> Foreign</Tag>
              ) : null}
            </div>
            {block.domain_tag ? (
              <div className="text-xs text-muted-foreground mt-1">{block.domain_tag}</div>
            ) : null}
          </div>
          <div className="w-28 shrink-0 hidden sm:block">
            <div className="flex items-center justify-between text-xs mb-0.5">
              <span className="text-muted-foreground">Score</span>
              <span className="font-medium tabular-nums">{score}%</span>
            </div>
            <Meter value={score} tone="gold" className="h-1.5" />
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="pt-2 pb-4 space-y-4">
        {block.narrative_hint ? (
          <p className="text-sm text-muted-foreground leading-relaxed border-l-2 border-gold/40 pl-3">
            {block.narrative_hint}
          </p>
        ) : null}

        {block.llm_plain_language_html || block.llm_astro_explanation_html ? (
          <div className="space-y-3">
            {block.llm_plain_language_html ? (
              <Callout tone="success" label="In plain language">
                <ProseBlock html={block.llm_plain_language_html} />
              </Callout>
            ) : null}
            {block.llm_astro_explanation_html ? (
              <details className="rounded-xl border border-border bg-muted/40 p-3 group">
                <summary className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground cursor-pointer select-none">
                  Astrological explanation
                </summary>
                <ProseBlock className="mt-2" html={block.llm_astro_explanation_html} />
              </details>
            ) : null}
          </div>
        ) : block.llm_ad_narrative_html ? (
          <ProseBlock html={block.llm_ad_narrative_html} />
        ) : null}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {block.confidence ? <Meta label="Confidence" value={block.confidence} /> : null}
          {block.career_track ? <Meta label="Track" value={block.career_track} /> : null}
          {block.secondary_event_type && block.secondary_event_type !== block.event_type ? (
            <Meta label="Secondary" value={block.secondary_event_type.replace(/_/g, " ")} />
          ) : null}
          {block.active_houses && block.active_houses.length ? (
            <Meta label="Houses" value={block.active_houses.join(", ")} />
          ) : null}
        </div>

        {block.skill_recommendations && block.skill_recommendations.length ? (
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1.5 font-bold">Skills to build</div>
            <div className="flex flex-wrap gap-1.5">
              {block.skill_recommendations.map((sk, i) => (
                <Tag key={i} tone="muted">{sk}</Tag>
              ))}
            </div>
          </div>
        ) : null}

        {pds.length ? (
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1.5 font-bold">
              Sub-periods ({pds.length})
            </div>
            <div className="space-y-1.5">
              {pds.map((pd, i) => (
                <div key={i} className="rounded-lg border border-border bg-background/40 p-2.5">
                  <div className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="font-medium">{pd.pd_lord as string}</span>
                    <span className="text-muted-foreground tabular-nums">
                      {fmtDate(pd.start_date as string)} → {fmtDate(pd.end_date as string)}
                    </span>
                    {typeof pd.pd_score === "number" ? (
                      <span className="tabular-nums font-medium">{Math.round(pd.pd_score * 100)}%</span>
                    ) : null}
                  </div>
                  {pd.llm_narrative_html ? (
                    <ProseBlock className="mt-1 text-xs text-muted-foreground" html={pd.llm_narrative_html as string} />
                  ) : pd.hint ? (
                    <p className="mt-1 text-xs text-muted-foreground">{pd.hint as string}</p>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </AccordionContent>
    </AccordionItem>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}

// ─── Mahadasha arcs ──────────────────────────────────────────────────────────

function MDArcs({ arcs }: { arcs: CareerTimelineResponse["md_arcs"] }) {
  if (!arcs.length) return null;
  return (
    <Panel>
      <SectionTitle title="Major life-chapter themes" chip="Mahadasha arcs" />
      <div className="space-y-3">
        {arcs.map((a, i) => (
          <div key={i} className="rounded-xl border border-border bg-surface-soft/50 p-4">
            <div className="flex items-baseline justify-between mb-2 gap-3">
              <h4 className="font-semibold text-foreground">{a.md_lord} chapter</h4>
              <span className="text-xs text-muted-foreground tabular-nums shrink-0">
                {fmtDate(a.start_date)} → {fmtDate(a.end_date)}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">{a.narrative}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ─── Foreign opportunities ───────────────────────────────────────────────────

function ForeignOpportunities({
  items,
  meta,
}: {
  items: CareerForeignOpportunity[];
  meta: CareerTimelineResponse["foreign_meta"];
}) {
  if (!items.length) return null;
  return (
    <Panel>
      <SectionTitle
        title="Foreign opportunity windows"
        chip={`${meta.total} window${meta.total === 1 ? "" : "s"}`}
        chipTone="info"
        icon={<Globe2 className="h-5 w-5 text-info" />}
      />
      <p className="text-xs text-muted-foreground -mt-2 mb-4">
        Periods that favour work abroad, relocation, or international exposure.
        {meta.peak_period ? ` Peak: ${meta.peak_period} (${meta.peak_score.toFixed(2)}).` : ""}
        {meta.geo_summary ? ` ${meta.geo_summary}.` : ""}
      </p>
      <div className="flex gap-2 mb-4">
        <Tag tone="success">High: {meta.high}</Tag>
        <Tag tone="warn">Moderate: {meta.moderate}</Tag>
        <Tag tone="muted">Mild: {meta.mild}</Tag>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {items.map((fo, i) => (
          <ForeignCard key={i} fo={fo} />
        ))}
      </div>
    </Panel>
  );
}

function ForeignCard({ fo }: { fo: CareerForeignOpportunity }) {
  const score = Math.round((fo.foreign_score ?? 0) * 100);
  const tone: Tone = score >= 65 ? "success" : score >= 45 ? "warn" : "muted";
  return (
    <div className="rounded-xl border border-border bg-surface-soft/40 p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-medium">{fo.md_lord} – {fo.ad_lord}</div>
          <div className="text-xs text-muted-foreground tabular-nums">
            {fmtDate(fo.start_date)} → {fmtDate(fo.end_date)}
          </div>
        </div>
        <Tag tone={tone}>{score}%</Tag>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {fo.duration_type ? <Tag tone="muted">{String(fo.duration_type).replace(/_/g, " ")}</Tag> : null}
        {fo.geo_affinity ? (
          <Tag tone="muted"><MapPin className="w-3 h-3" /> {fo.geo_affinity}</Tag>
        ) : null}
      </div>
      {fo.narrative ? <p className="text-sm text-muted-foreground leading-relaxed">{fo.narrative}</p> : null}
      {fo.drivers && fo.drivers.length ? (
        <div className="text-xs text-muted-foreground">
          <span className="uppercase tracking-wide font-semibold">Drivers:</span> {fo.drivers.join(", ")}
        </div>
      ) : null}
    </div>
  );
}

// ─── Micro-timing (readable) ─────────────────────────────────────────────────

interface NegWindow {
  date_start?: string;
  date_end?: string;
  score?: number;
  label?: string;
  colour?: string;
  advice?: string;
}
interface NegHeatmap {
  windows?: NegWindow[];
  best_window?: NegWindow;
  current_month_label?: string;
  caution_periods?: Array<{ date_start?: string; date_end?: string; reason?: string }>;
}
interface Radar {
  climate_label?: string;
  climate_colour?: string;
  advice?: string;
  quarter_label?: string;
  h6_afflicted?: boolean;
  h10_afflicted?: boolean;
  h7_afflicted?: boolean;
  malefic_houses?: number[];
}
interface WhatIf {
  action_label?: string;
  advisability?: string;
  advisability_colour?: string;
  timing_note?: string;
  earliest_opportunity_date?: string;
  risk_factors?: string[];
  opportunity_factors?: string[];
  recommendation?: string;
  risk_score?: number;
  opp_score?: number;
}
interface HabitWeek {
  week_label?: string;
  title?: string;
  detail?: string;
  frequency?: string;
  is_current?: boolean;
  pd_note?: string;
}

function MicroTiming({ mt }: { mt: Record<string, unknown> }) {
  const heatmap = mt.negotiation_heatmap as NegHeatmap | undefined;
  const radar = mt.stakeholder_radar as Radar | undefined;
  const whatif = mt.whatif_scenarios as Record<string, WhatIf> | undefined;
  const hora = mt.hora_timing as { weeks?: HabitWeek[] } | undefined;

  const hasHeatmap = !!heatmap?.windows?.length;
  const hasRadar = !!radar?.climate_label;
  const hasWhatif = !!whatif && Object.keys(whatif).length > 0;
  const hasHora = !!hora?.weeks?.length;

  if (!hasHeatmap && !hasRadar && !hasWhatif && !hasHora) return null;

  return (
    <Panel>
      <SectionTitle title="Micro-timing" chip="Short-term signals" icon={<Timer className="h-5 w-5 text-gold" />} />
      <p className="text-xs text-muted-foreground -mt-2 mb-4">
        Near-term day/week guidance derived from current transits and your active dasha — best used for scheduling
        conversations and decisions.
      </p>

      <div className="space-y-5">
        {hasWhatif ? <WhatIfGrid scenarios={whatif!} /> : null}
        {hasHeatmap ? <NegotiationHeatmap heatmap={heatmap!} /> : null}
        {hasRadar ? <StakeholderRadar radar={radar!} /> : null}
        {hasHora ? <HabitPlan weeks={hora!.weeks!} /> : null}
      </div>
    </Panel>
  );
}

function WhatIfGrid({ scenarios }: { scenarios: Record<string, WhatIf> }) {
  const list = Object.values(scenarios);
  if (!list.length) return null;
  return (
    <div>
      <SubHead icon={<CheckCircle2 className="h-4 w-4" />} text="Should I…? — scenario advice" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {list.map((w, i) => {
          const tone = toneFromColour(w.advisability_colour ?? w.advisability);
          return (
            <div key={i} className="rounded-xl border border-border bg-surface-soft/40 p-4 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-foreground">{w.action_label ?? "Scenario"}</div>
                {w.advisability ? <Tag tone={tone}>{w.advisability}</Tag> : null}
              </div>
              {w.timing_note ? <p className="text-sm text-muted-foreground leading-relaxed">{w.timing_note}</p> : null}
              {w.recommendation ? (
                <p className="text-[13px] text-foreground/85 leading-relaxed">{w.recommendation}</p>
              ) : null}
              <div className="flex flex-wrap gap-1.5">
                {w.opportunity_factors?.slice(0, 4).map((f, j) => (
                  <Tag key={`o-${j}`} tone="success">{f}</Tag>
                ))}
                {w.risk_factors?.slice(0, 4).map((f, j) => (
                  <Tag key={`r-${j}`} tone="danger">{f}</Tag>
                ))}
              </div>
              {w.earliest_opportunity_date ? (
                <div className="text-[11px] text-muted-foreground">
                  Next strong window: <span className="font-medium text-foreground">{fmtDate(w.earliest_opportunity_date)}</span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function NegotiationHeatmap({ heatmap }: { heatmap: NegHeatmap }) {
  const windows = heatmap.windows ?? [];
  const cautions = heatmap.caution_periods ?? [];
  return (
    <div>
      <SubHead
        icon={<CalendarClock className="h-4 w-4" />}
        text={`Negotiation & interview windows${heatmap.current_month_label ? ` · ${heatmap.current_month_label}` : ""}`}
      />
      {heatmap.best_window ? (
        <Callout tone="success" label="Best window" className="mb-3">
          <span className="font-medium text-foreground">
            {fmtDate(heatmap.best_window.date_start)} → {fmtDate(heatmap.best_window.date_end)}
          </span>
          {heatmap.best_window.advice ? ` — ${heatmap.best_window.advice}` : ""}
        </Callout>
      ) : null}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {windows.map((w, i) => {
          const tone = toneFromColour(w.colour);
          return (
            <div key={i} className="rounded-lg border border-border bg-surface-soft/40 p-3">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-xs tabular-nums text-muted-foreground">
                  {fmtDate(w.date_start)} → {fmtDate(w.date_end)}
                </span>
                {w.label ? <Tag tone={tone}>{w.label}</Tag> : null}
              </div>
              {w.advice ? <p className="text-[12.5px] text-muted-foreground leading-snug">{w.advice}</p> : null}
            </div>
          );
        })}
      </div>
      {cautions.length ? (
        <div className="mt-3 space-y-1.5">
          {cautions.map((c, i) => (
            <div key={i} className="flex gap-2 text-xs text-warn">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              <span>
                <span className="tabular-nums">{fmtDate(c.date_start)} → {fmtDate(c.date_end)}</span>
                {c.reason ? ` — ${c.reason}` : ""}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StakeholderRadar({ radar }: { radar: Radar }) {
  const tone = toneFromColour(radar.climate_colour);
  const houses: Array<[string, boolean | undefined]> = [
    ["Team / colleagues (H6)", radar.h6_afflicted],
    ["Boss / authority (H10)", radar.h10_afflicted],
    ["Clients / partners (H7)", radar.h7_afflicted],
  ];
  return (
    <div>
      <SubHead
        icon={<Users className="h-4 w-4" />}
        text={`Workplace climate${radar.quarter_label ? ` · ${radar.quarter_label}` : ""}`}
      />
      <div className="rounded-xl border border-border bg-surface-soft/40 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Overall climate:</span>
          {radar.climate_label ? <Tag tone={tone}>{radar.climate_label}</Tag> : null}
        </div>
        {radar.advice ? <p className="text-sm text-muted-foreground leading-relaxed">{radar.advice}</p> : null}
        <div className="flex flex-wrap gap-1.5">
          {houses.map(([label, afflicted]) => (
            <Tag key={label} tone={afflicted ? "warn" : "success"}>
              {afflicted ? "⚠ " : "✓ "}
              {label}
            </Tag>
          ))}
        </div>
      </div>
    </div>
  );
}

function HabitPlan({ weeks }: { weeks: HabitWeek[] }) {
  return (
    <div>
      <SubHead icon={<Timer className="h-4 w-4" />} text="Four-week focus plan" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {weeks.map((w, i) => (
          <div
            key={i}
            className={
              "rounded-xl border p-3.5 " +
              (w.is_current ? "border-gold/40 bg-gold/5" : "border-border bg-surface-soft/40")
            }
          >
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{w.week_label}</span>
              {w.is_current ? <Tag tone="gold">Now</Tag> : null}
            </div>
            {w.title ? <div className="font-semibold text-foreground text-sm mb-1">{w.title}</div> : null}
            {w.detail ? <p className="text-[12px] text-muted-foreground leading-snug">{w.detail}</p> : null}
            {w.frequency ? <p className="text-[11px] text-gold mt-1.5">{w.frequency}</p> : null}
            {w.pd_note ? <p className="text-[10.5px] text-muted-foreground italic mt-1">{w.pd_note}</p> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function SubHead({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-wider text-muted-foreground mb-2.5">
      <span className="text-gold">{icon}</span>
      {text}
    </div>
  );
}
