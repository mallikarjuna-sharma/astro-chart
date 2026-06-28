import { useMemo } from "react";
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
import { Globe2, MapPin, TrendingUp, Calendar, Sparkles, Briefcase } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import type {
  CareerForeignOpportunity,
  CareerTimelineBlock,
  CareerTimelineResponse,
  CareerTrajectoryPoint,
} from "@/lib/pyjhora/types";

interface Props {
  data: CareerTimelineResponse;
}

export function CareerTimelineReport({ data }: Props) {
  return (
    <div className="space-y-6">
      <ReportHeader data={data} />
      <OutcomeBar data={data} />
      <TrajectoryChart points={data.trajectory} />
      <AnnualCalendar entries={data.calendar} />
      <TimelineBlocks blocks={data.blocks} />
      <MDArcs arcs={data.md_arcs} />
      <ForeignOpportunities
        items={data.foreign_opportunities}
        meta={data.foreign_meta}
      />
      <MicroTiming mt={data.micro_timing} />
    </div>
  );
}

// ─── Header ──────────────────────────────────────────────────────────────────

function ReportHeader({ data }: { data: CareerTimelineResponse }) {
  const s = data.student;
  const warnings = (data.career_context?.warnings as string[] | undefined) ?? [];
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-xl">{s.name ?? "Career Timeline"}</CardTitle>
            <CardDescription className="mt-1">
              {s.dob ? `Born ${s.dob}` : null}
              {s.birth_place ? ` · ${s.birth_place}` : null}
              {typeof s.current_age === "number" ? ` · age ${Math.round(s.current_age)}` : null}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.llm_enriched ? (
              <Badge className="bg-amber-500/15 text-amber-700 border-amber-500/30">
                LLM-enriched narratives
              </Badge>
            ) : (
              <Badge variant="secondary">Deterministic narratives</Badge>
            )}
            {s.active_dasha_lord ? (
              <Badge variant="outline">
                <Sparkles className="w-3 h-3 mr-1" />
                Active MD: {s.active_dasha_lord}
              </Badge>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-sm">
          {s.lagna_sign ? <Meta label="Lagna" value={`${s.lagna_sign}${s.lagna_lord ? ` (lord: ${s.lagna_lord})` : ""}`} /> : null}
          {s.atmakaraka ? <Meta label="Atmakaraka" value={s.atmakaraka} /> : null}
          {s.amatyakaraka ? <Meta label="Amatyakaraka" value={s.amatyakaraka} /> : null}
          {s.h10_lord ? <Meta label="10H Lord" value={s.h10_lord} /> : null}
        </div>
        {warnings.length > 0 ? (
          <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700">
            {warnings.map((w, i) => (
              <div key={i}>· {w}</div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}

// ─── Outcome Bar ─────────────────────────────────────────────────────────────

function OutcomeBar({ data }: { data: CareerTimelineResponse }) {
  const o = data.outcome;
  const items = [
    { label: "Primary Opportunity", value: o.primary_opportunity, icon: TrendingUp },
    { label: "Peak MD Lord", value: o.peak_md_lord, icon: Sparkles },
    { label: "Peak Years", value: o.peak_years, icon: Calendar },
    { label: "Growth Arc", value: o.growth_arc, icon: Briefcase },
  ];
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {items.map(({ label, value, icon: Icon }) => (
        <Card key={label} className="border-gold/30 bg-linear-to-br from-amber-50/80 to-transparent dark:from-amber-950/20">
          <CardContent className="py-4">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
              <Icon className="h-3.5 w-3.5" />
              {label}
            </div>
            <div className="text-lg font-semibold text-gold mt-1">{value}</div>
          </CardContent>
        </Card>
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
    <Card>
      <CardHeader>
        <CardTitle>Career Trajectory</CardTitle>
        <CardDescription>
          Antardasha-level career score (%) across the projected window. Color indicates event type.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div style={{ width: "100%", height: 280 }}>
          <ResponsiveContainer>
            <LineChart data={chartData} margin={{ top: 16, right: 24, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e8e2d4" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} angle={-12} dy={6} height={50} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: "1px solid #e8e2d4" }}
                formatter={(v: number) => [`${v}`, "Score"]}
                labelFormatter={(label: string, p) => {
                  const evt = p && p[0] ? (p[0].payload as { event?: string }).event : "";
                  return `${label}${evt ? ` · ${evt}` : ""}`;
                }}
              />
              <Line
                type="monotone"
                dataKey="score"
                stroke="#C9A84C"
                strokeWidth={2}
                dot={(props) => {
                  const { cx, cy, payload, index } = props as {
                    cx: number;
                    cy: number;
                    payload: { color: string };
                    index: number;
                  };
                  return <Dot key={index} cx={cx} cy={cy} r={5} fill={payload.color} stroke="#fff" strokeWidth={1.5} />;
                }}
                activeDot={{ r: 7 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Annual Calendar ─────────────────────────────────────────────────────────

function AnnualCalendar({ entries }: { entries: CareerTimelineResponse["calendar"] }) {
  if (!entries.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Annual Career Calendar</CardTitle>
        <CardDescription>Best Antardasha per calendar year (peak event + score).</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {entries.map((e) => (
            <div
              key={e.year}
              className="rounded-lg border bg-surface-warm p-3 text-center"
              style={{ borderColor: e.color + "55" }}
            >
              <div className="text-xs text-muted-foreground">{e.year}</div>
              <div className="text-2xl font-bold tabular-nums" style={{ color: e.color }}>
                {e.score}
              </div>
              <div className="text-[11px] font-medium leading-tight mt-1">{e.event_type}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">AD: {e.ad_lord}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Timeline blocks (AD level) ──────────────────────────────────────────────

function TimelineBlocks({ blocks }: { blocks: CareerTimelineBlock[] }) {
  if (!blocks.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Career Timeline · Antardasha Detail</CardTitle>
        <CardDescription>
          Per-AD block: dasha lords, event signature, score, narrative, pratyantardashas.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Accordion type="multiple" className="space-y-2">
          {blocks.map((b, i) => (
            <BlockItem key={`${b.md_lord}-${b.ad_lord}-${i}`} block={b} idx={i} />
          ))}
        </Accordion>
      </CardContent>
    </Card>
  );
}

function BlockItem({ block, idx }: { block: CareerTimelineBlock; idx: number }) {
  const score = Math.round((block.career_score ?? 0) * 100);
  const eventLabel = (block.event_type ?? "STABILITY").replace(/_/g, " ").toLowerCase();
  const isCurrent = !!block.is_current;
  const isPrimary = !!block.is_primary_opportunity;
  const pds = block.pratyantardashas ?? [];

  return (
    <AccordionItem value={`b-${idx}`} className="border rounded-lg px-4">
      <AccordionTrigger className="hover:no-underline py-3">
        <div className="flex flex-1 items-center gap-3 text-left">
          <div className="text-xs tabular-nums text-muted-foreground w-28 shrink-0">
            {block.start_date} → {block.end_date}
          </div>
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {block.md_lord} – {block.ad_lord}
              </span>
              <Badge variant="outline" className="capitalize text-xs">
                {eventLabel}
              </Badge>
              {isCurrent ? <Badge className="bg-gold text-primary-foreground text-xs">Current</Badge> : null}
              {isPrimary ? <Badge className="bg-purple-600/20 text-purple-700 border-purple-600/30 text-xs">Primary opportunity</Badge> : null}
              {block.foreign_opportunity ? (
                <Badge className="bg-blue-500/15 text-blue-700 border-blue-500/30 text-xs">
                  <Globe2 className="w-3 h-3 mr-1" />
                  Foreign
                </Badge>
              ) : null}
            </div>
            {block.domain_tag ? (
              <div className="text-xs text-muted-foreground mt-1">{block.domain_tag}</div>
            ) : null}
          </div>
          <div className="w-32 shrink-0">
            <div className="flex items-center justify-between text-xs mb-0.5">
              <span className="text-muted-foreground">Score</span>
              <span className="font-medium tabular-nums">{score}%</span>
            </div>
            <Progress value={score} className="h-1.5" />
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="pt-2 pb-4 space-y-4">
        {block.narrative_hint ? (
          <p className="text-sm text-muted-foreground leading-relaxed border-l-2 border-gold/40 pl-3">
            {block.narrative_hint}
          </p>
        ) : null}

        {block.llm_ad_narrative_html ? (
          <div
            className="prose prose-sm max-w-none [&_h4]:text-sm [&_h4]:font-semibold [&_h4]:mt-3 [&_h4]:mb-1 [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0.5"
            // eslint-disable-next-line react/no-danger
            dangerouslySetInnerHTML={{ __html: block.llm_ad_narrative_html }}
          />
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
            <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Skills to build</div>
            <div className="flex flex-wrap gap-1.5">
              {block.skill_recommendations.map((s, i) => (
                <Badge key={i} variant="secondary" className="text-xs">{s}</Badge>
              ))}
            </div>
          </div>
        ) : null}

        {pds.length ? (
          <div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5">
              Pratyantardashas ({pds.length})
            </div>
            <div className="space-y-1.5">
              {pds.map((pd, i) => (
                <div key={i} className="rounded border bg-surface-warm/50 p-2">
                  <div className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="font-medium">{pd.pd_lord as string}</span>
                    <span className="text-muted-foreground tabular-nums">
                      {pd.start_date as string} → {pd.end_date as string}
                    </span>
                    {typeof pd.pd_score === "number" ? (
                      <span className="tabular-nums">
                        {Math.round(pd.pd_score * 100)}%
                      </span>
                    ) : null}
                  </div>
                  {pd.llm_narrative_html ? (
                    <div
                      className="mt-1 text-xs text-muted-foreground [&_p]:m-0"
                      // eslint-disable-next-line react/no-danger
                      dangerouslySetInnerHTML={{ __html: pd.llm_narrative_html }}
                    />
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

// ─── Mahadasha arcs ──────────────────────────────────────────────────────────

function MDArcs({ arcs }: { arcs: CareerTimelineResponse["md_arcs"] }) {
  if (!arcs.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Mahadasha Narrative Arcs</CardTitle>
        <CardDescription>Theme of each Mahadasha intersecting the timeline.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {arcs.map((a, i) => (
          <div key={i} className="rounded-lg border bg-surface-warm p-4">
            <div className="flex items-baseline justify-between mb-2">
              <h4 className="font-semibold">MD Arc: {a.md_lord}</h4>
              <span className="text-xs text-muted-foreground tabular-nums">
                {a.start_date} → {a.end_date}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">{a.narrative}</p>
          </div>
        ))}
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Globe2 className="h-5 w-5 text-blue-600" />
          Foreign Opportunity Windows
        </CardTitle>
        <CardDescription>
          {meta.total} window{meta.total === 1 ? "" : "s"} detected
          {meta.peak_period ? ` · peak ${meta.peak_period} (score ${meta.peak_score.toFixed(2)})` : ""}
          {meta.geo_summary ? ` · ${meta.geo_summary}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex gap-2 mb-4 text-xs">
          <Badge className="bg-green-600/15 text-green-700 border-green-600/30">High: {meta.high}</Badge>
          <Badge className="bg-amber-500/15 text-amber-700 border-amber-500/30">Moderate: {meta.moderate}</Badge>
          <Badge variant="secondary">Mild: {meta.mild}</Badge>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {items.map((fo, i) => (
            <ForeignCard key={i} fo={fo} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function ForeignCard({ fo }: { fo: CareerForeignOpportunity }) {
  const score = Math.round((fo.foreign_score ?? 0) * 100);
  const tone =
    score >= 65 ? "bg-green-600/15 text-green-700 border-green-600/30" :
    score >= 45 ? "bg-amber-500/15 text-amber-700 border-amber-500/30" :
                  "bg-muted text-muted-foreground";
  return (
    <div className="rounded-lg border p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-medium">{fo.md_lord} – {fo.ad_lord}</div>
          <div className="text-xs text-muted-foreground tabular-nums">
            {fo.start_date} → {fo.end_date}
          </div>
        </div>
        <Badge className={tone}>{score}%</Badge>
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        {fo.duration_type ? (
          <Badge variant="outline" className="text-xs">{String(fo.duration_type).replace(/_/g, " ")}</Badge>
        ) : null}
        {fo.geo_affinity ? (
          <Badge variant="outline" className="text-xs">
            <MapPin className="w-3 h-3 mr-1" />
            {fo.geo_affinity}
          </Badge>
        ) : null}
      </div>
      {fo.narrative ? (
        <p className="text-sm text-muted-foreground leading-relaxed">{fo.narrative}</p>
      ) : null}
      {fo.drivers && fo.drivers.length ? (
        <div className="text-xs text-muted-foreground">
          <span className="uppercase tracking-wide font-medium">Drivers:</span> {fo.drivers.join(", ")}
        </div>
      ) : null}
    </div>
  );
}

// ─── Micro-timing dashboard ──────────────────────────────────────────────────

function MicroTiming({ mt }: { mt: Record<string, unknown> }) {
  const hasAny =
    mt && (mt.hora_timing || mt.negotiation_heatmap || mt.stakeholder_radar || mt.whatif_scenarios);
  if (!hasAny) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Micro-Timing Dashboard</CardTitle>
        <CardDescription>
          Day-of-week and hour-of-day signals derived from Hora cycles + AD activation.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="negotiation">
          <TabsList className="grid grid-cols-2 sm:grid-cols-4 w-full">
            <TabsTrigger value="negotiation">Negotiation</TabsTrigger>
            <TabsTrigger value="hora">Hora plan</TabsTrigger>
            <TabsTrigger value="stakeholders">Stakeholders</TabsTrigger>
            <TabsTrigger value="whatif">What-if</TabsTrigger>
          </TabsList>
          <TabsContent value="negotiation" className="mt-4">
            <JsonPreview data={mt.negotiation_heatmap} fallback="No negotiation heatmap computed." />
          </TabsContent>
          <TabsContent value="hora" className="mt-4">
            <JsonPreview data={mt.hora_timing} fallback="No weekly hora plan computed." />
          </TabsContent>
          <TabsContent value="stakeholders" className="mt-4">
            <JsonPreview data={mt.stakeholder_radar} fallback="No stakeholder radar computed." />
          </TabsContent>
          <TabsContent value="whatif" className="mt-4">
            <JsonPreview data={mt.whatif_scenarios} fallback="No what-if scenarios computed." />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function JsonPreview({ data, fallback }: { data: unknown; fallback: string }) {
  if (data == null || (typeof data === "object" && data && Object.keys(data).length === 0)) {
    return <p className="text-sm text-muted-foreground">{fallback}</p>;
  }
  return (
    <pre className="text-xs bg-muted/40 p-3 rounded-md overflow-auto max-h-96">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
