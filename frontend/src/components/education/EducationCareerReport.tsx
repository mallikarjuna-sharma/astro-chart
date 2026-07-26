import { useMemo } from "react";
import type {
  ChartType,
  CorporateEntrepreneurial,
  EducationAnalysisResponse,
  EducationFieldResult,
} from "@/lib/pyjhora/types";
import { EducationFieldCard } from "@/components/education/EducationFieldCard";
import { useDisplayName } from "@/hooks/use-display-name";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Callout,
  DataTable,
  Meter,
  Panel,
  ReportShell,
  SectionTitle,
  StatTile,
  Tag,
} from "@/components/report/primitives";

interface Props {
  data: EducationAnalysisResponse;
}

const TOP_N = 20;

interface FinalIdentity {
  macro_identity?: string;
  one_line_summary?: string;
  confidence?: string;
}

interface Snapshot {
  best_ug_route?: string;
  best_pg_route?: string;
  best_career_cluster?: string;
  strong_backup_route?: string;
  best_working_style?: string;
  avoid_as_primary?: string;
}

interface MacroCluster {
  rank?: number;
  cluster?: string;
  strength_pct?: number;
  member_fields?: string[];
}

function sortMacroClustersByStrength(clusters: MacroCluster[]): MacroCluster[] {
  return [...clusters]
    .sort((a, b) => {
      const byStrength = (b.strength_pct ?? 0) - (a.strength_pct ?? 0);
      if (byStrength !== 0) return byStrength;
      return (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER);
    })
    .map((cluster, index) => ({ ...cluster, rank: index + 1 }));
}

function fieldsInCluster(
  cluster: MacroCluster,
  rankedFields: EducationFieldResult[],
): EducationFieldResult[] {
  const members = new Set(cluster.member_fields ?? []);
  if (!members.size) return [];
  return rankedFields.filter((row) => members.has(row.field_label));
}

interface AstroSignatureRow {
  factor?: string;
  observation?: string;
  career_meaning?: string;
}

interface EducationRoute {
  route_name?: string;
  title?: string;
  best_for?: string;
  ug_options?: string;
  pg_options?: string;
  phd_options?: string;
  careers?: string;
  long_term_value?: string;
  risk_level?: string;
}

interface Top20Field {
  field?: string;
  reason?: string;
  recommended_level?: string;
}

interface EngineComparisonRow {
  engine_field?: string;
  engine_rank?: number | string;
  correct_status?: string;
  action?: string;
}

interface GapAuditItem {
  gap?: string;
  effect?: string;
  fix?: string;
}

interface RouteCaution {
  field?: string;
  status?: string;
  reason?: string;
  assessment?: string;
}

interface ClusterInterp {
  cluster?: string;
  interpretation?: string;
}

interface FieldToAvoid {
  field?: string;
  status?: string;
  reason?: string;
  assessment?: string;
}

interface ReportNarrative {
  final_identity?: FinalIdentity;
  snapshot?: Snapshot;
  astrological_signature?: AstroSignatureRow[];
  macro_cluster_interpretations?: ClusterInterp[];
  education_routes?: EducationRoute[];
  top_20_fields?: Top20Field[];
  engine_output_comparison?: EngineComparisonRow[];
  engine_gap_audit?: GapAuditItem[];
  route_cautions?: RouteCaution[];
  fields_to_avoid?: FieldToAvoid[];
  parent_summary?: string;
  student_summary?: string;
  final_recommendation?: string;
  disclaimer?: string;
}

interface ChartFacts {
  academic_tier_recommendation?: string;
  active_mahadasha_lord?: string;
  arudha_lagna?: string;
  arudha_pada_h10?: string;
  current_age?: number;
  dob?: string;
  edu_stream?: string;
  eff_strengths_top3?: Array<[string, number]>;
  h10_lord?: string;
  lagna_sign?: string;
  peak_career_mahadasha_lord?: string;
  ug_start_year?: number | string;
}

function CorporateGauge({ profile }: { profile: CorporateEntrepreneurial }) {
  const corpPct = profile.corporate_pct ?? 50;
  const entrepPct = profile.entrep_pct ?? 50;

  return (
    <Panel>
      <div className="text-[11px] font-bold uppercase tracking-wider text-warn mb-3">
        Working Style Profile — {profile.style_label ?? "Balanced"}
      </div>
      <div className="flex items-center gap-3">
        <span className="text-[11px] text-info font-bold shrink-0">Entrepreneur</span>
        <div className="flex-1 h-2.5 rounded-full overflow-hidden" style={{ background: "linear-gradient(90deg, var(--info), var(--gold))" }}>
          <div className="h-full bg-background/35" style={{ width: `${100 - corpPct}%`, marginLeft: "auto" }} />
        </div>
        <span className="text-[11px] text-gold font-bold shrink-0">Corporate</span>
        <span className="text-xs font-bold text-foreground min-w-[110px] text-right shrink-0">
          {corpPct}% Corp / {entrepPct}% Entrep
        </span>
      </div>
      <div className="flex justify-between text-[10px] text-muted-foreground mt-1.5">
        <span>Founder · Consulting · Independent</span>
        <span>MNC · Enterprise · Government</span>
      </div>
      {profile.style_note ? (
        <p className="text-xs text-muted-foreground mt-2 leading-snug">{profile.style_note}</p>
      ) : null}
    </Panel>
  );
}

function ClusterBanner({ chartType }: { chartType: ChartType }) {
  const clusters = chartType.domain_clusters ?? {};
  const entries = Object.entries(clusters).slice(0, 6);
  if (!chartType.is_cluster || !entries.length) return null;

  return (
    <div className="rounded-2xl border border-info/30 bg-info/8 p-5 flex flex-wrap gap-4 items-start">
      <div className="flex gap-3 items-start flex-1 min-w-[260px]">
        <span className="text-2xl leading-none shrink-0">🌟</span>
        <div>
          <div className="font-semibold text-[15px] text-info mb-1">
            {chartType.cluster_label ?? "Polymathic Chart"}
          </div>
          <p className="text-[12px] text-muted-foreground leading-relaxed max-w-md">
            Aptitude is distributed across a cluster of fields — all highlighted fields carry genuine
            astrological fit. No single field dominates; strength lies in cross-domain synthesis.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {entries.map(([dom, fids]) => (
          <div
            key={dom}
            className="flex flex-col items-center bg-card border border-info/25 rounded-xl px-3 py-1.5 min-w-[90px]"
          >
            <span className="text-[11px] font-bold text-info">{dom}</span>
            <span className="text-[10px] text-muted-foreground mt-0.5">{fids.length} fields</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DecisionSnapshot({
  identity,
  snapshot,
  topCluster,
  dominantClusterLabel,
  topScore,
  v12Count,
  v12Total,
  top1,
  top3,
  signaturePills,
  avoidPills,
}: {
  identity: FinalIdentity;
  snapshot: Snapshot;
  topCluster: MacroCluster;
  dominantClusterLabel: string;
  topScore: number;
  v12Count: number;
  v12Total: number;
  top1: string;
  top2: string;
  top3: string;
  signaturePills: string[];
  avoidPills: string[];
}) {
  return (
    <div className="space-y-4">
      <Panel>
        <SectionTitle title="Decision Snapshot" chip="At a glance" chipTone="gold" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <StatTile value={`${Math.round(topCluster.strength_pct ?? 0)}%`} label="Dominant macro-cluster strength" />
          <StatTile value={topScore.toFixed(2)} label="Top normalized field score" />
          <StatTile value={identity.confidence || "—"} label="Final recommendation confidence" tone="success" />
          <StatTile value={`${v12Count}/${v12Total}`} label="Top-20 rows with v12 registry data" tone="info" />
        </div>
        <Callout tone="gold" label="Plain answer">
          <strong className="text-foreground">{top1}</strong> is the cleanest starting point in{" "}
          <strong className="text-foreground">{dominantClusterLabel}</strong> (
          {Math.round(topCluster.strength_pct ?? 0)}% cluster strength).
          {top3 ? <> {top3} is the best specialization direction.</> : null}
        </Callout>
      </Panel>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Panel>
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-3">Best Choices</div>
          <div className="space-y-1.5 text-sm text-foreground">
            <p><span className="font-semibold text-muted-foreground">UG:</span> {top1}</p>
            <p><span className="font-semibold text-muted-foreground">PG:</span> {top3 || "—"}</p>
            <p><span className="font-semibold text-muted-foreground">Cluster:</span> {dominantClusterLabel}</p>
            <p><span className="font-semibold text-muted-foreground">Work style:</span> {snapshot.best_working_style || "—"}</p>
          </div>
        </Panel>
        <Panel>
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-3">Chart Signature</div>
          <div className="flex flex-wrap gap-1.5">
            {signaturePills.length
              ? signaturePills.map((p) => <Tag key={p} tone="royal">{p}</Tag>)
              : <span className="text-xs text-muted-foreground">No chart anchors available.</span>}
          </div>
          <p className="text-[11px] text-muted-foreground mt-3 leading-snug">
            Factual chart anchors passed to the interpretation layer.
          </p>
        </Panel>
        <Panel>
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-3">Avoid As Primary</div>
          <div className="flex flex-wrap gap-1.5">
            {avoidPills.length
              ? avoidPills.map((p) => <Tag key={p} tone="danger">{p}</Tag>)
              : <span className="text-xs text-muted-foreground">No fields flagged to avoid.</span>}
          </div>
          <p className="text-[11px] text-muted-foreground mt-3 leading-snug">
            Use these only as backups or interest areas unless there is strong independent motivation.
          </p>
        </Panel>
      </div>
    </div>
  );
}

function ClusterScorePanels({
  clusters,
  labelToRow,
}: {
  clusters: MacroCluster[];
  labelToRow: Map<string, EducationFieldResult>;
}) {
  if (!clusters.length) return null;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {clusters.map((c, i) => {
        const rows = (c.member_fields ?? [])
          .map((name) => labelToRow.get(name))
          .filter((r): r is EducationFieldResult => Boolean(r))
          .sort((a, b) => (b.final_score ?? 0) - (a.final_score ?? 0));
        return (
          <div key={c.cluster ?? i} className="rounded-xl border border-border bg-surface-soft/50 p-4">
            <div className="flex items-baseline justify-between gap-2 mb-3">
              <h3 className="font-semibold text-foreground text-[0.95rem] leading-snug">
                {c.rank ? `#${c.rank} · ` : ""}
                {c.cluster}
              </h3>
              <span className="text-[11px] font-bold text-gold shrink-0">
                {Math.round(c.strength_pct ?? 0)}% strength
              </span>
            </div>
            <div className="space-y-2.5">
              {rows.length ? (
                rows.map((r, idx) => {
                  const sc = r.final_score ?? 0;
                  return (
                    <div key={r.field_id} className="flex items-center gap-2.5">
                      <span className="w-5 text-[11px] font-bold text-muted-foreground shrink-0 text-right">{idx + 1}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12.5px] font-medium text-foreground truncate">{r.field_label}</div>
                        <Meter value={Math.max(0, Math.min(100, sc))} tone="gold" className="mt-1 h-1.5" />
                      </div>
                      <span className="text-[11.5px] font-bold text-muted-foreground w-12 text-right shrink-0">
                        {sc.toFixed(2)}
                      </span>
                    </div>
                  );
                })
              ) : (
                <p className="text-xs text-muted-foreground">No top-20 fields in this cluster.</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function EducationCareerReport({ data }: Props) {
  const { student, summary } = data;
  const displayName = useDisplayName(student.name);
  const generated = data.generated_at
    ? new Date(data.generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : "";

  const rows = data.results?.length ? data.results : data.fields;
  const topFields = useMemo(
    () =>
      [...(rows ?? [])]
        .sort((a, b) => b.final_score - a.final_score || a.field_id.localeCompare(b.field_id))
        .slice(0, TOP_N),
    [rows],
  );

  const report = (data.report ?? {}) as ReportNarrative;
  const identity = report.final_identity ?? {};
  const snapshot = report.snapshot ?? {};
  const macroClusters = useMemo(
    () => sortMacroClustersByStrength((data.macro_clusters ?? []) as MacroCluster[]),
    [data.macro_clusters],
  );
  const chartFacts = (data.chart_facts ?? {}) as ChartFacts;

  const payload = data.report_bundle?.payload as Record<string, unknown> | undefined;
  const corpProfile = payload?.corporate_entrepreneurial as CorporateEntrepreneurial | undefined;
  const chartType =
    (topFields[0]?.chart_type as ChartType | undefined) ??
    (payload?.chart_type as ChartType | undefined) ??
    {};

  const topCluster = macroClusters[0] ?? { cluster: identity.macro_identity, strength_pct: 0 };
  const topClusterFields = useMemo(
    () => fieldsInCluster(topCluster, topFields),
    [topCluster, topFields],
  );

  const top1Label =
    topClusterFields[0]?.field_label ??
    topFields[0]?.field_label ??
    snapshot.best_ug_route ??
    "Undetermined";
  const top2Label =
    topClusterFields[1]?.field_label ??
    topFields[1]?.field_label ??
    snapshot.strong_backup_route ??
    "";
  const top3Label =
    topClusterFields.find((field) => {
      const realism = field.registry as { education_realism?: { pg_required_for_good_outcome?: boolean } } | undefined;
      return realism?.education_realism?.pg_required_for_good_outcome;
    })?.field_label ??
    snapshot.best_pg_route ??
    topClusterFields[2]?.field_label ??
    topFields[2]?.field_label ??
    "";
  const topScore = topClusterFields[0]?.final_score ?? topFields[0]?.final_score ?? 0;
  const dominantClusterLabel = topCluster.cluster ?? identity.macro_identity ?? "Undetermined";

  const activeLord = summary.active_dasha_lord ?? chartFacts.active_mahadasha_lord ?? "";
  const peakLord = summary.peak_career_dasha ?? chartFacts.peak_career_mahadasha_lord ?? "";
  const careerPhase = summary.career_phase ?? "";

  const labelToRow = useMemo(() => {
    const m = new Map<string, EducationFieldResult>();
    for (const r of topFields) m.set(r.field_label, r);
    return m;
  }, [topFields]);

  const v12Count = topFields.filter(
    (r) => r.registry && Object.keys(r.registry).length > 0,
  ).length;

  const signaturePills = useMemo(() => {
    const pills: string[] = [];
    if (chartFacts.lagna_sign) pills.push(chartFacts.lagna_sign);
    if (chartFacts.h10_lord) pills.push(`H10 lord: ${chartFacts.h10_lord}`);
    if (activeLord) pills.push(`Active: ${activeLord}`);
    if (peakLord) pills.push(`Peak: ${peakLord}`);
    for (const pair of chartFacts.eff_strengths_top3 ?? []) {
      if (Array.isArray(pair) && pair[0]) pills.push(String(pair[0]));
    }
    return pills;
  }, [chartFacts, activeLord, peakLord]);

  const avoidPills = (report.fields_to_avoid ?? [])
    .map((a) => a.field)
    .filter((f): f is string => Boolean(f));

  const clusterInterp = new Map(
    (report.macro_cluster_interpretations ?? []).map((i) => [i.cluster, i.interpretation]),
  );

  const routeCautions = report.route_cautions?.length ? report.route_cautions : report.fields_to_avoid ?? [];

  const ugStartYear = Number(chartFacts.ug_start_year);
  const timelinePhases = Number.isFinite(ugStartYear) && ugStartYear > 0
    ? [
        [ugStartYear - 1, ugStartYear, "Strengthen fundamentals aligned with the recommended UG route."],
        [ugStartYear, ugStartYear + 2, "Build the core technical base, tools, projects, and disciplined study rhythm."],
        [ugStartYear + 2, ugStartYear + 4, "Use internships, projects, and electives to test the strongest specializations."],
        [ugStartYear + 4, ugStartYear + 7, "Move toward the PG route and career cluster identified by this report."],
      ] as Array<[number, number, string]>
    : [];

  const jsonPayload = useMemo(
    () => ({
      final_identity: identity,
      snapshot,
      macro_clusters: macroClusters,
      top_20_fields: report.top_20_fields ?? [],
      education_routes: report.education_routes ?? [],
      route_cautions: report.route_cautions ?? [],
      engine_output_comparison: report.engine_output_comparison ?? [],
      engine_gap_audit: report.engine_gap_audit ?? [],
      parent_summary: report.parent_summary ?? "",
      student_summary: report.student_summary ?? "",
      final_recommendation: report.final_recommendation ?? "",
      chart_facts: chartFacts,
    }),
    [identity, snapshot, macroClusters, report, chartFacts],
  );

  return (
    <ReportShell>
      {/* Hero header */}
      <header className="text-center pb-2">
        <div className="text-[11px] font-bold tracking-[0.22em] text-gold uppercase mb-3">
          JyotishAI Career Engine
        </div>
        <h2 className="font-serif text-3xl md:text-[2.5rem] font-semibold text-foreground mb-3 leading-tight">
          {displayName} · Career Field Report
        </h2>
        {identity.one_line_summary ? (
          <p className="text-[1.02rem] leading-relaxed text-muted-foreground max-w-3xl mx-auto mb-4">
            {identity.one_line_summary}
          </p>
        ) : null}
        <div className="flex justify-center flex-wrap gap-2">
          {dominantClusterLabel ? <Tag tone="gold">{dominantClusterLabel}</Tag> : null}
          {topCluster.strength_pct != null ? (
            <Tag tone="gold">{Math.round(topCluster.strength_pct)}% cluster strength</Tag>
          ) : null}
          {careerPhase ? <Tag tone="info">Phase: {careerPhase}</Tag> : null}
          {activeLord ? <Tag tone="royal">Active MD: {activeLord}</Tag> : null}
          {peakLord ? <Tag tone="royal">Peak MD: {peakLord}</Tag> : null}
          {student.lagna_sign ? <Tag>Lagna: {student.lagna_sign}</Tag> : null}
          {student.atmakaraka ? <Tag>AK: {student.atmakaraka}</Tag> : null}
        </div>
      </header>

      <DecisionSnapshot
        identity={identity}
        snapshot={snapshot}
        topCluster={topCluster}
        dominantClusterLabel={dominantClusterLabel}
        topScore={topScore}
        v12Count={v12Count}
        v12Total={topFields.length}
        top1={top1Label}
        top2={top2Label}
        top3={top3Label}
        signaturePills={signaturePills}
        avoidPills={avoidPills}
      />

      {corpProfile?.style_label || corpProfile?.corporate_pct != null ? (
        <CorporateGauge profile={corpProfile} />
      ) : null}

      <ClusterBanner chartType={chartType} />

      {/* Grouped detail — keeps the wall of sections digestible */}
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="grid w-full grid-cols-2 sm:grid-cols-4">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="fields">Top fields</TabsTrigger>
          <TabsTrigger value="routes">Routes & plan</TabsTrigger>
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
        </TabsList>

        {/* ── Overview ─────────────────────────────────────────────── */}
        <TabsContent value="overview" className="mt-5 space-y-5">
          <Panel>
            <SectionTitle title="Recommendation snapshot" chip="Actionable" chipTone="success" />
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {[
                ["Best UG Route", top1Label, "Main education decision."],
                ["Strong Backup", top2Label || "—", "Keep available, but secondary to the primary identity."],
                ["Best PG Route", top3Label || "—", "Specialization direction after the core UG base."],
                ["Career Cluster", dominantClusterLabel, `Dominant macro identity (${Math.round(topCluster.strength_pct ?? 0)}% strength).`],
              ].map(([label, value, note]) => (
                <div key={label} className="rounded-xl border border-border bg-surface-soft/50 px-4 py-3.5">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1">{label}</div>
                  <div className="text-[0.98rem] font-semibold text-foreground leading-snug mb-1.5">{value}</div>
                  <p className="text-[11px] text-muted-foreground leading-snug">{note}</p>
                </div>
              ))}
            </div>
          </Panel>

          {report.final_recommendation ? (
            <Panel>
              <SectionTitle title="Final recommendation" chip="Summary" chipTone="gold" />
              <div className="rounded-xl bg-primary/8 border-l-4 border-gold px-5 py-4 text-[1.02rem] text-foreground leading-relaxed">
                {report.final_recommendation}
              </div>
            </Panel>
          ) : null}

          {report.parent_summary || report.student_summary ? (
            <Panel>
              <SectionTitle title="Parent & student versions" />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {report.parent_summary ? (
                  <Callout tone="success" label="Parent version">{report.parent_summary}</Callout>
                ) : null}
                {report.student_summary ? (
                  <Callout tone="info" label="Student version">{report.student_summary}</Callout>
                ) : null}
              </div>
            </Panel>
          ) : null}
        </TabsContent>

        {/* ── Top fields ───────────────────────────────────────────── */}
        <TabsContent value="fields" className="mt-5 space-y-5">
          {macroClusters.length ? (
            <Panel>
              <SectionTitle title="Field scores by cluster" chip="Engine normalized scale" />
              <ClusterScorePanels clusters={macroClusters} labelToRow={labelToRow} />
              <p className="text-[11px] text-muted-foreground mt-3 leading-snug">
                Cluster panels are ordered highest to lowest by engine-normalized strength; fields inside
                each panel are ranked highest to lowest by score.
              </p>
            </Panel>
          ) : null}

          <Panel>
            <SectionTitle title="Top 20 field matrix" chip="Full detail" />
            {summary.parent_overview ? (
              <Callout tone="success" className="mb-5">{summary.parent_overview}</Callout>
            ) : null}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
              {topFields.map((field, i) => (
                <EducationFieldCard key={field.field_id} rank={i + 1} field={field} />
              ))}
            </div>
          </Panel>

          {macroClusters.length ? (
            <Panel>
              <SectionTitle title="Macro-cluster ranking" chip="Deterministic + interpretation" chipTone="success" />
              <DataTable
                head={
                  <>
                    <th className="py-2 pr-3">Rank</th>
                    <th className="py-2 pr-3">Macro Cluster</th>
                    <th className="py-2 pr-3">Strength</th>
                    <th className="py-2 pr-3">Member Fields</th>
                    <th className="py-2">Career Meaning</th>
                  </>
                }
              >
                {macroClusters.map((c, i) => (
                  <tr key={c.cluster ?? i} className="border-b border-border/60 align-top">
                    <td className="py-2.5 pr-3 font-bold text-muted-foreground">{c.rank}</td>
                    <td className="py-2.5 pr-3 font-semibold text-foreground">{c.cluster}</td>
                    <td className="py-2.5 pr-3 font-bold text-gold">{Math.round(c.strength_pct ?? 0)}%</td>
                    <td className="py-2.5 pr-3 text-muted-foreground text-[12.5px]">
                      {(c.member_fields ?? []).slice(0, 6).join(", ")}
                    </td>
                    <td className="py-2.5 text-muted-foreground text-[12.5px]">{clusterInterp.get(c.cluster) ?? ""}</td>
                  </tr>
                ))}
              </DataTable>
            </Panel>
          ) : null}
        </TabsContent>

        {/* ── Routes & plan ────────────────────────────────────────── */}
        <TabsContent value="routes" className="mt-5 space-y-5">
          {report.education_routes?.length ? (
            <Panel>
              <SectionTitle title="Education route map" chip="UG to PG to career" chipTone="info" />
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {report.education_routes.map((route, i) => (
                  <article key={route.route_name ?? i} className="rounded-xl border border-border bg-surface-soft/50 p-4">
                    <div className="mb-2">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-gold">
                        {route.route_name}
                      </div>
                      <h3 className="font-semibold text-foreground text-[0.98rem] leading-snug">{route.title}</h3>
                    </div>
                    <div className="space-y-1 text-[12.5px] text-muted-foreground">
                      {route.ug_options ? <p><span className="font-semibold text-foreground/70">UG:</span> {route.ug_options}</p> : null}
                      {route.pg_options ? <p><span className="font-semibold text-foreground/70">PG:</span> {route.pg_options}</p> : null}
                      {route.phd_options ? <p><span className="font-semibold text-foreground/70">PhD:</span> {route.phd_options}</p> : null}
                      {route.careers ? <p><span className="font-semibold text-foreground/70">Careers:</span> {route.careers}</p> : null}
                      {route.best_for ? <p><span className="font-semibold text-foreground/70">Best for:</span> {route.best_for}</p> : null}
                    </div>
                    <div className="flex flex-wrap gap-1.5 mt-3">
                      {route.risk_level ? <Tag>{route.risk_level}</Tag> : null}
                      {route.long_term_value ? <Tag>{route.long_term_value}</Tag> : null}
                    </div>
                  </article>
                ))}
              </div>
            </Panel>
          ) : null}

          {timelinePhases.length ? (
            <Panel>
              <SectionTitle title="Execution timeline" chip="Student-friendly" chipTone="info" />
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                {timelinePhases.map(([a, b, txt]) => (
                  <div key={`${a}-${b}`} className="rounded-xl border border-border bg-surface-soft/50 p-4">
                    <div className="font-bold text-gold text-sm mb-1.5">{a}–{b}</div>
                    <p className="text-[12.5px] text-muted-foreground leading-snug">{txt}</p>
                  </div>
                ))}
              </div>
            </Panel>
          ) : null}

          {!report.education_routes?.length && !timelinePhases.length ? (
            <Panel>
              <p className="text-sm text-muted-foreground text-center py-4">
                No education route map was generated for this chart.
              </p>
            </Panel>
          ) : null}
        </TabsContent>

        {/* ── Evidence ─────────────────────────────────────────────── */}
        <TabsContent value="evidence" className="mt-5 space-y-5">
          {report.astrological_signature?.length ? (
            <Panel>
              <SectionTitle title="Evidence from chart data" chip="Why this direction" />
              <DataTable
                head={
                  <>
                    <th className="py-2 pr-3">Factor</th>
                    <th className="py-2 pr-3">Observation</th>
                    <th className="py-2">Career Meaning</th>
                  </>
                }
              >
                {report.astrological_signature.map((r, i) => (
                  <tr key={i} className="border-b border-border/60 align-top">
                    <td className="py-2.5 pr-3 font-semibold text-foreground">{r.factor}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground text-[12.5px]">{r.observation}</td>
                    <td className="py-2.5 text-muted-foreground text-[12.5px]">{r.career_meaning}</td>
                  </tr>
                ))}
              </DataTable>
              {report.engine_output_comparison?.length ? (
                <div className="mt-5">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
                    Engine Output Comparison
                  </div>
                  <DataTable
                    head={
                      <>
                        <th className="py-2 pr-3">Rank</th>
                        <th className="py-2 pr-3">Engine Field</th>
                        <th className="py-2 pr-3">Status</th>
                        <th className="py-2">Action</th>
                      </>
                    }
                  >
                    {report.engine_output_comparison.map((r, i) => (
                      <tr key={i} className="border-b border-border/60 align-top">
                        <td className="py-2.5 pr-3 font-bold text-muted-foreground">{r.engine_rank}</td>
                        <td className="py-2.5 pr-3 font-semibold text-foreground">{r.engine_field}</td>
                        <td className="py-2.5 pr-3 text-muted-foreground text-[12.5px]">{r.correct_status}</td>
                        <td className="py-2.5 text-muted-foreground text-[12.5px]">{r.action}</td>
                      </tr>
                    ))}
                  </DataTable>
                </div>
              ) : null}
            </Panel>
          ) : null}

          {report.engine_gap_audit?.length ? (
            <Panel>
              <SectionTitle title="Engine gap diagnosis" chip="Audit" chipTone="warn" />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {report.engine_gap_audit.map((g, i) => (
                  <div key={i} className="rounded-xl border border-warn/25 bg-warn/8 p-4">
                    <div className="font-semibold text-foreground text-sm mb-1">{g.gap}</div>
                    <p className="text-[12.5px] text-muted-foreground leading-snug mb-1.5">{g.effect}</p>
                    {g.fix ? (
                      <p className="text-[12.5px] text-foreground/80 leading-snug">
                        <strong className="text-warn">Fix:</strong> {g.fix}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            </Panel>
          ) : null}

          {routeCautions.length ? (
            <Panel>
              <SectionTitle title="Route suitability cautions" chip="Conditional pathways" chipTone="warn" />
              <DataTable
                head={
                  <>
                    <th className="py-2 pr-3">Field</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2">Reason</th>
                  </>
                }
              >
                {routeCautions.map((a, i) => (
                  <tr key={i} className="border-b border-border/60 align-top">
                    <td className="py-2.5 pr-3 font-semibold text-foreground">{a.field}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground text-[12.5px]">{a.status}</td>
                    <td className="py-2.5 text-muted-foreground text-[12.5px]">{a.reason ?? a.assessment}</td>
                  </tr>
                ))}
              </DataTable>
            </Panel>
          ) : null}

          <Panel>
            <SectionTitle title="Machine-readable JSON" chip="v12 preserved" />
            <details className="group">
              <summary className="cursor-pointer text-sm font-semibold text-gold select-none">
                View compact JSON output
              </summary>
              <pre className="mt-3 max-h-[420px] overflow-auto rounded-xl bg-background border border-border text-foreground/80 text-[11px] leading-relaxed p-4">
                {JSON.stringify(jsonPayload, null, 2)}
              </pre>
            </details>
          </Panel>
        </TabsContent>
      </Tabs>

      <footer className="text-center text-xs text-muted-foreground py-6 border-t border-border">
        JyotishAI Engine · {generated} · {data.engine_version} ·{" "}
        {report.disclaimer ?? "For educational guidance only."}
      </footer>
    </ReportShell>
  );
}
