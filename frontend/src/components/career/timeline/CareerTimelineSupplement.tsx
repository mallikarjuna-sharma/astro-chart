import { useMemo, type ReactNode } from "react";
import {
  CartesianGrid,
  Dot,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Globe2,
  MapPin,
  Timer,
  TrendingUp,
  Users,
} from "lucide-react";
import { Callout, Panel, SectionTitle, Tag, type Tone } from "@/components/report/primitives";
import { fmtDate } from "@/lib/career-timeline/helpers";
import type {
  CareerForeignOpportunity,
  CareerTimelineResponse,
  CareerTrajectoryPoint,
} from "@/lib/pyjhora/types";

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

export function CareerTimelineSupplement({ data }: { data: CareerTimelineResponse }) {
  const foreignCount = data.foreign_opportunities?.length ?? 0;
  const mt = data.micro_timing ?? {};
  const hasTiming = !!(
    mt.negotiation_heatmap ||
    mt.stakeholder_radar ||
    mt.whatif_scenarios ||
    mt.hora_timing
  );

  return (
    <div className="w-full space-y-5 text-left">
      <TrajectoryChart points={data.trajectory} />
      <AnnualCalendar entries={data.calendar} />
      <MDArcs arcs={data.md_arcs} />
      <ForeignOpportunities items={data.foreign_opportunities} meta={data.foreign_meta} />
      {hasTiming ? <MicroTiming mt={mt} /> : null}
      {!foreignCount && !hasTiming ? null : null}
    </div>
  );
}

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
