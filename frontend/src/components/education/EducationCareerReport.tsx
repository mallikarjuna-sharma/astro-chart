import { useMemo } from "react";
import type {
  ChartType,
  CorporateEntrepreneurial,
  EducationAnalysisResponse,
  EducationFieldResult,
} from "@/lib/pyjhora/types";
import { EducationFieldCard } from "@/components/education/EducationFieldCard";
import { useDisplayName } from "@/hooks/use-display-name";

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

function levelClass(level?: string): string {
  const l = (level ?? "").toLowerCase();
  if (l.includes("primary")) return "bg-teal-100 text-teal-800 border-teal-300";
  if (l.includes("strong") || l.includes("special")) return "bg-indigo-100 text-indigo-800 border-indigo-300";
  if (l.includes("backup") || l.includes("pg")) return "bg-amber-100 text-amber-800 border-amber-300";
  return "bg-slate-100 text-slate-600 border-slate-300";
}

function SectionTitle({ n, title, chip, chipTone = "neutral" }: {
  n?: number;
  title: string;
  chip?: string;
  chipTone?: "neutral" | "strong" | "blue" | "warn";
}) {
  const tone = {
    neutral: "bg-slate-100 text-slate-600 border-slate-200",
    strong: "bg-teal-100 text-teal-800 border-teal-200",
    blue: "bg-blue-100 text-blue-800 border-blue-200",
    warn: "bg-amber-100 text-amber-800 border-amber-200",
  }[chipTone];
  return (
    <div className="flex items-center justify-between gap-3 mb-4">
      <h2 className="text-[1.15rem] font-extrabold text-slate-900 leading-tight">
        {n != null ? <span className="text-slate-400 mr-1.5">{n}.</span> : null}
        {title}
      </h2>
      {chip ? (
        <span className={`text-[10.5px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border shrink-0 ${tone}`}>
          {chip}
        </span>
      ) : null}
    </div>
  );
}

function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white shadow-sm p-6 mb-6 ${className}`}>
      {children}
    </section>
  );
}

function Pill({ children, tone = "primary" }: { children: React.ReactNode; tone?: "primary" | "alt" | "avoid" }) {
  const cls = {
    primary: "bg-teal-50 text-teal-800 border-teal-200",
    alt: "bg-slate-100 text-slate-600 border-slate-200",
    avoid: "bg-rose-50 text-rose-800 border-rose-200",
  }[tone];
  return (
    <span className={`inline-block text-[11px] font-semibold px-2.5 py-1 rounded-full border ${cls}`}>
      {children}
    </span>
  );
}

function CorporateGauge({ profile }: { profile: CorporateEntrepreneurial }) {
  const corpPct = profile.corporate_pct ?? 50;
  const entrepPct = profile.entrep_pct ?? 50;
  const entrepMask = 100 - corpPct;

  return (
    <div className="my-4 px-4 py-3.5 rounded-xl border border-amber-300/40 bg-white/55 backdrop-blur-sm">
      <div className="text-[11px] font-bold uppercase tracking-wider text-amber-800 mb-2">
        Working Style Profile — {profile.style_label ?? "Balanced"}
      </div>
      <div className="flex items-center gap-2.5">
        <span className="text-[10px] text-blue-600 font-bold shrink-0">Entrepreneur</span>
        <div className="flex-1 h-2.5 rounded-full bg-linear-to-r from-blue-500 to-amber-400 relative overflow-hidden">
          <div className="absolute right-0 top-0 h-full bg-white/35" style={{ width: `${entrepMask}%` }} />
        </div>
        <span className="text-[10px] text-amber-800 font-bold shrink-0">Corporate</span>
        <span className="text-xs font-bold text-slate-900 min-w-[100px] text-right shrink-0">
          {corpPct}% Corp / {entrepPct}% Entrep
        </span>
      </div>
      <div className="flex justify-between text-[10px] text-slate-500 mt-1">
        <span>Founder · Consulting · Independent</span>
        <span>MNC · Enterprise · Government</span>
      </div>
      {profile.style_note ? (
        <p className="text-xs text-slate-600 mt-1.5 leading-snug">{profile.style_note}</p>
      ) : null}
    </div>
  );
}

function ClusterBanner({ chartType }: { chartType: ChartType }) {
  const clusters = chartType.domain_clusters ?? {};
  const entries = Object.entries(clusters).slice(0, 6);
  if (!chartType.is_cluster || !entries.length) return null;

  return (
    <div className="flex flex-wrap gap-4 items-start bg-linear-to-br from-sky-50 to-sky-100 border-[1.5px] border-sky-400 rounded-2xl p-5 mb-6">
      <div className="flex gap-3 items-start flex-1 min-w-[260px]">
        <span className="text-2xl leading-none shrink-0">🌟</span>
        <div>
          <div className="font-bold text-[15px] text-sky-800 mb-1">
            {chartType.cluster_label ?? "Polymathic Chart"}
          </div>
          <p className="text-[11.5px] text-sky-950 leading-relaxed max-w-md">
            Aptitude is distributed across a cluster of fields — all highlighted fields carry genuine
            astrological fit. No single field dominates; strength lies in cross-domain synthesis.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {entries.map(([dom, fids]) => (
          <div
            key={dom}
            className="flex flex-col items-center bg-white border border-sky-300 rounded-[10px] px-3 py-1.5 min-w-[90px]"
          >
            <span className="text-[10.5px] font-bold text-sky-800">{dom}</span>
            <span className="text-[9.5px] text-slate-500 mt-0.5">{fids.length} fields</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Decision Snapshot metrics band + Best Choices / Chart Signature / Avoid rail. */
function DecisionSnapshot({
  identity,
  snapshot,
  topCluster,
  topScore,
  v12Count,
  v12Total,
  top1,
  top2,
  top3,
  signaturePills,
  avoidPills,
}: {
  identity: FinalIdentity;
  snapshot: Snapshot;
  topCluster: MacroCluster;
  topScore: number;
  v12Count: number;
  v12Total: number;
  top1: string;
  top2: string;
  top3: string;
  signaturePills: string[];
  avoidPills: string[];
}) {
  const metrics: Array<[string, string]> = [
    [`${Math.round(topCluster.strength_pct ?? 0)}%`, "Dominant macro-cluster strength"],
    [topScore.toFixed(2), "Top normalized field score"],
    [identity.confidence || "—", "Final recommendation confidence"],
    [`${v12Count}/${v12Total}`, "Top-20 rows with v12 registry data"],
  ];
  return (
    <div className="mb-6">
      <Panel>
        <SectionTitle title="Decision Snapshot" chip="At a glance" chipTone="strong" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          {metrics.map(([value, label]) => (
            <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-center">
              <div className="text-2xl font-extrabold text-teal-700 leading-none">{value}</div>
              <div className="text-[10.5px] text-slate-500 mt-1.5 leading-snug">{label}</div>
            </div>
          ))}
        </div>
        <div className="rounded-xl bg-teal-50 border border-teal-200 px-4 py-3 text-sm text-slate-800 leading-relaxed">
          <strong className="text-teal-800">Plain answer:</strong> {top1} is the cleanest starting point.
          {top3 ? <> {top3} is the best specialization direction.</> : null}
        </div>
      </Panel>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-3">Best Choices</div>
          <div className="space-y-1.5 text-sm text-slate-800">
            <p><span className="font-bold text-slate-500">UG:</span> {top1}</p>
            <p><span className="font-bold text-slate-500">PG:</span> {top3 || "—"}</p>
            <p><span className="font-bold text-slate-500">Backup:</span> {top2 || "—"}</p>
            <p><span className="font-bold text-slate-500">Work style:</span> {snapshot.best_working_style || "—"}</p>
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-3">Chart Signature</div>
          <div className="flex flex-wrap gap-1.5">
            {signaturePills.length
              ? signaturePills.map((p) => <Pill key={p}>{p}</Pill>)
              : <span className="text-xs text-slate-400">No chart anchors available.</span>}
          </div>
          <p className="text-[11px] text-slate-400 mt-3 leading-snug">
            Factual chart anchors passed to the interpretation layer.
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-3">Avoid As Primary</div>
          <div className="flex flex-wrap gap-1.5">
            {avoidPills.length
              ? avoidPills.map((p) => <Pill key={p} tone="avoid">{p}</Pill>)
              : <span className="text-xs text-slate-400">No fields flagged to avoid.</span>}
          </div>
          <p className="text-[11px] text-slate-400 mt-3 leading-snug">
            Use these only as backups or interest areas unless there is strong independent motivation.
          </p>
        </div>
      </div>
    </div>
  );
}

/** 2. Top Field Scores by Cluster — score bars grouped by macro-cluster. */
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
      {clusters.slice(0, 4).map((c, i) => {
        const rows = (c.member_fields ?? [])
          .map((name) => labelToRow.get(name))
          .filter((r): r is EducationFieldResult => Boolean(r))
          .sort((a, b) => (b.final_score ?? 0) - (a.final_score ?? 0));
        return (
          <div key={c.cluster ?? i} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
            <div className="flex items-baseline justify-between gap-2 mb-3">
              <h3 className="font-bold text-slate-900 text-[0.95rem] leading-snug">{c.cluster}</h3>
              <span className="text-[10.5px] font-bold text-teal-700 shrink-0">
                {Math.round(c.strength_pct ?? 0)}% strength
              </span>
            </div>
            <div className="space-y-2">
              {rows.length ? (
                rows.map((r, idx) => {
                  const sc = r.final_score ?? 0;
                  return (
                    <div key={r.field_id} className="flex items-center gap-2.5">
                      <span className="w-5 text-[11px] font-bold text-slate-400 shrink-0 text-right">{idx + 1}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12.5px] font-semibold text-slate-800 truncate">{r.field_label}</div>
                        <div className="h-1.5 rounded-full bg-slate-200 overflow-hidden mt-1">
                          <div
                            className="h-full rounded-full bg-linear-to-r from-teal-500 to-blue-500"
                            style={{ width: `${Math.max(0, Math.min(100, sc))}%` }}
                          />
                        </div>
                      </div>
                      <span className="text-[11.5px] font-bold text-slate-600 w-12 text-right shrink-0">
                        {sc.toFixed(2)}
                      </span>
                    </div>
                  );
                })
              ) : (
                <p className="text-xs text-slate-400">No top-20 fields in this cluster.</p>
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
  const macroClusters = (data.macro_clusters ?? []) as MacroCluster[];
  const chartFacts = (data.chart_facts ?? {}) as ChartFacts;

  const payload = data.report_bundle?.payload as Record<string, unknown> | undefined;
  const corpProfile = payload?.corporate_entrepreneurial as CorporateEntrepreneurial | undefined;
  const chartType =
    (topFields[0]?.chart_type as ChartType | undefined) ??
    (payload?.chart_type as ChartType | undefined) ??
    {};

  // Derived headline routes (mirrors render_report_html_rich).
  const top1Label = topFields[0]?.field_label ?? snapshot.best_ug_route ?? "Undetermined";
  const top2Label = topFields[1]?.field_label ?? snapshot.strong_backup_route ?? "";
  const top3Label = snapshot.best_pg_route ?? topFields[2]?.field_label ?? "";
  const topCluster = macroClusters[0] ?? { cluster: identity.macro_identity, strength_pct: 0 };
  const topScore = topFields[0]?.final_score ?? 0;

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
    <div className="max-w-[1280px] mx-auto text-slate-800">
      <header className="text-center mb-6 pb-5 border-b-2 border-slate-200">
        <div className="text-[0.9rem] font-bold tracking-[0.2em] text-slate-500 uppercase mb-2.5">
          JyotishAI Career Engine
        </div>
        <h2 className="text-[2.5rem] font-extrabold text-slate-900 mb-2 leading-tight">
          {displayName} Career Field Report
        </h2>
        {identity.one_line_summary ? (
          <p className="text-[1.05rem] leading-relaxed text-slate-600 max-w-3xl mx-auto mb-4">
            {identity.one_line_summary}
          </p>
        ) : null}
        <div className="flex justify-center flex-wrap gap-2 text-[0.85rem]">
          {identity.macro_identity ? (
            <span className="bg-teal-100 text-teal-800 px-3 py-1 rounded-full font-semibold">
              {identity.macro_identity}
            </span>
          ) : null}
          {careerPhase ? (
            <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full font-semibold">
              Phase: {careerPhase}
            </span>
          ) : null}
          {activeLord ? (
            <span className="bg-slate-200 text-slate-700 px-3 py-1 rounded-full font-medium">
              Active MD: {activeLord}
            </span>
          ) : null}
          {peakLord ? (
            <span className="bg-slate-200 text-slate-700 px-3 py-1 rounded-full font-medium">
              Peak MD: {peakLord}
            </span>
          ) : null}
          {student.lagna_sign ? (
            <span className="bg-slate-200 text-slate-700 px-3 py-1 rounded-full font-medium">
              Lagna: {student.lagna_sign}
            </span>
          ) : null}
          {student.atmakaraka ? (
            <span className="bg-slate-200 text-slate-700 px-3 py-1 rounded-full font-medium">
              AK: {student.atmakaraka}
            </span>
          ) : null}
        </div>
      </header>

      <DecisionSnapshot
        identity={identity}
        snapshot={snapshot}
        topCluster={topCluster}
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

      {/* 1. Final Recommendation Snapshot */}
      <Panel>
        <SectionTitle n={1} title="Final Recommendation Snapshot" chip="Actionable" chipTone="strong" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {[
            ["Best UG Route", top1Label, "Main education decision."],
            ["Strong Backup", top2Label || "—", "Keep available, but secondary to the primary identity."],
            ["Best PG Route", top3Label || "—", "Specialization direction after the core UG base."],
            ["Career Cluster", topCluster.cluster || "—", "Dominant macro identity from engine cluster ranking."],
          ].map(([label, value, note]) => (
            <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3.5">
              <div className="text-[0.7rem] font-bold uppercase tracking-wider text-slate-400 mb-1">{label}</div>
              <div className="text-[0.98rem] font-bold text-slate-900 leading-snug mb-1.5">{value}</div>
              <p className="text-[11px] text-slate-500 leading-snug">{note}</p>
            </div>
          ))}
        </div>
      </Panel>

      {/* 2. Top Field Scores by Cluster */}
      {macroClusters.length ? (
        <Panel>
          <SectionTitle n={2} title="Top Field Scores by Cluster" chip="Engine normalized scale" />
          <ClusterScorePanels clusters={macroClusters} labelToRow={labelToRow} />
          <p className="text-[11px] text-slate-400 mt-3 leading-snug">
            Each panel is one macro-cluster; fields inside a panel are ranked highest to lowest by engine-normalized
            score.
          </p>
        </Panel>
      ) : null}

      {/* 3. Education Route Map */}
      {report.education_routes?.length ? (
        <Panel>
          <SectionTitle n={3} title="Education Route Map" chip="UG to PG to career" chipTone="blue" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {report.education_routes.map((route, i) => (
              <article key={route.route_name ?? i} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
                <div className="mb-2">
                  <div className="text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                    {route.route_name}
                  </div>
                  <h3 className="font-bold text-slate-900 text-[0.98rem] leading-snug">{route.title}</h3>
                </div>
                <div className="space-y-1 text-[12.5px] text-slate-700">
                  {route.ug_options ? <p><span className="font-bold text-slate-500">UG:</span> {route.ug_options}</p> : null}
                  {route.pg_options ? <p><span className="font-bold text-slate-500">PG:</span> {route.pg_options}</p> : null}
                  {route.phd_options ? <p><span className="font-bold text-slate-500">PhD:</span> {route.phd_options}</p> : null}
                  {route.careers ? <p><span className="font-bold text-slate-500">Careers:</span> {route.careers}</p> : null}
                  {route.best_for ? <p><span className="font-bold text-slate-500">Best for:</span> {route.best_for}</p> : null}
                </div>
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {route.risk_level ? <Pill tone="alt">{route.risk_level}</Pill> : null}
                  {route.long_term_value ? <Pill tone="alt">{route.long_term_value}</Pill> : null}
                </div>
              </article>
            ))}
          </div>
        </Panel>
      ) : null}

      {/* 4. Full Top 20 Field Matrix */}
      <Panel>
        <SectionTitle n={4} title="Full Top 20 Field Matrix" chip="v12 registry visible" />
        {summary.parent_overview ? (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-4 text-sm text-slate-800 mb-5 leading-relaxed">
            {summary.parent_overview}
          </div>
        ) : null}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
          {topFields.map((field, i) => (
            <EducationFieldCard key={field.field_id} rank={i + 1} field={field} />
          ))}
        </div>
      </Panel>

      {/* 5. Macro-Cluster Ranking */}
      {macroClusters.length ? (
        <Panel>
          <SectionTitle n={5} title="Macro-Cluster Ranking" chip="Deterministic + interpretation" chipTone="strong" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-200">
                  <th className="py-2 pr-3">Rank</th>
                  <th className="py-2 pr-3">Macro Cluster</th>
                  <th className="py-2 pr-3">Strength</th>
                  <th className="py-2 pr-3">Member Fields</th>
                  <th className="py-2">Career Meaning</th>
                </tr>
              </thead>
              <tbody>
                {macroClusters.map((c, i) => (
                  <tr key={c.cluster ?? i} className="border-b border-slate-100 align-top">
                    <td className="py-2.5 pr-3 font-bold text-slate-500">{c.rank}</td>
                    <td className="py-2.5 pr-3 font-semibold text-slate-900">{c.cluster}</td>
                    <td className="py-2.5 pr-3 font-extrabold text-teal-700">{Math.round(c.strength_pct ?? 0)}%</td>
                    <td className="py-2.5 pr-3 text-slate-600 text-[12.5px]">
                      {(c.member_fields ?? []).slice(0, 6).join(", ")}
                    </td>
                    <td className="py-2.5 text-slate-600 text-[12.5px]">{clusterInterp.get(c.cluster) ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {/* 6. Evidence From Chart Data */}
      {report.astrological_signature?.length ? (
        <Panel>
          <SectionTitle n={6} title="Evidence From Chart Data" chip="Why this direction" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-200">
                  <th className="py-2 pr-3">Factor</th>
                  <th className="py-2 pr-3">Observation</th>
                  <th className="py-2">Career Meaning</th>
                </tr>
              </thead>
              <tbody>
                {report.astrological_signature.map((r, i) => (
                  <tr key={i} className="border-b border-slate-100 align-top">
                    <td className="py-2.5 pr-3 font-semibold text-slate-900">{r.factor}</td>
                    <td className="py-2.5 pr-3 text-slate-600 text-[12.5px]">{r.observation}</td>
                    <td className="py-2.5 text-slate-600 text-[12.5px]">{r.career_meaning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {report.engine_output_comparison?.length ? (
            <div className="mt-5">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
                Engine Output Comparison
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-200">
                      <th className="py-2 pr-3">Rank</th>
                      <th className="py-2 pr-3">Engine Field</th>
                      <th className="py-2 pr-3">Status</th>
                      <th className="py-2">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.engine_output_comparison.map((r, i) => (
                      <tr key={i} className="border-b border-slate-100 align-top">
                        <td className="py-2.5 pr-3 font-bold text-slate-500">{r.engine_rank}</td>
                        <td className="py-2.5 pr-3 font-semibold text-slate-900">{r.engine_field}</td>
                        <td className="py-2.5 pr-3 text-slate-600 text-[12.5px]">{r.correct_status}</td>
                        <td className="py-2.5 text-slate-600 text-[12.5px]">{r.action}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </Panel>
      ) : null}

      {/* 7. Execution Timeline */}
      {timelinePhases.length ? (
        <Panel>
          <SectionTitle n={7} title="Execution Timeline" chip="Student-friendly" chipTone="blue" />
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {timelinePhases.map(([a, b, txt]) => (
              <div key={`${a}-${b}`} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="font-extrabold text-teal-700 text-sm mb-1.5">{a}–{b}</div>
                <p className="text-[12.5px] text-slate-600 leading-snug">{txt}</p>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      {/* 8. Parent and Student Versions */}
      {report.parent_summary || report.student_summary ? (
        <Panel>
          <SectionTitle n={8} title="Parent and Student Versions" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {report.parent_summary ? (
              <div className="rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-3.5 text-sm text-slate-800 leading-relaxed">
                <strong className="text-emerald-800">Parent version:</strong> {report.parent_summary}
              </div>
            ) : null}
            {report.student_summary ? (
              <div className="rounded-xl bg-blue-50 border border-blue-200 px-4 py-3.5 text-sm text-slate-800 leading-relaxed">
                <strong className="text-blue-800">Student version:</strong> {report.student_summary}
              </div>
            ) : null}
          </div>
        </Panel>
      ) : null}

      {/* 9. Engine Gap Diagnosis */}
      {report.engine_gap_audit?.length ? (
        <Panel>
          <SectionTitle n={9} title="Engine Gap Diagnosis" chip="Audit" chipTone="warn" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {report.engine_gap_audit.map((g, i) => (
              <div key={i} className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
                <div className="font-bold text-slate-900 text-sm mb-1">{g.gap}</div>
                <p className="text-[12.5px] text-slate-600 leading-snug mb-1.5">{g.effect}</p>
                {g.fix ? (
                  <p className="text-[12.5px] text-slate-700 leading-snug">
                    <strong>Fix:</strong> {g.fix}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      {/* 10. Route Suitability Cautions */}
      {routeCautions.length ? (
        <Panel>
          <SectionTitle n={10} title="Route Suitability Cautions" chip="Conditional pathways" chipTone="warn" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-200">
                  <th className="py-2 pr-3">Field</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {routeCautions.map((a, i) => (
                  <tr key={i} className="border-b border-slate-100 align-top">
                    <td className="py-2.5 pr-3 font-semibold text-slate-900">{a.field}</td>
                    <td className="py-2.5 pr-3 text-slate-600 text-[12.5px]">{a.status}</td>
                    <td className="py-2.5 text-slate-600 text-[12.5px]">{a.reason ?? a.assessment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {/* 11. Final Recommendation */}
      {report.final_recommendation ? (
        <Panel>
          <SectionTitle n={11} title="Final Recommendation" chip="Summary" chipTone="strong" />
          <div className="rounded-xl bg-teal-50 border-l-4 border-teal-500 px-5 py-4 text-[1.02rem] text-slate-800 leading-relaxed">
            {report.final_recommendation}
          </div>
        </Panel>
      ) : null}

      {/* 12. Machine-Readable JSON */}
      <Panel>
        <SectionTitle n={12} title="Machine-Readable JSON" chip="v12 preserved" />
        <details className="group">
          <summary className="cursor-pointer text-sm font-semibold text-teal-700 select-none">
            View compact JSON output
          </summary>
          <pre className="mt-3 max-h-[420px] overflow-auto rounded-xl bg-slate-900 text-slate-100 text-[11px] leading-relaxed p-4">
            {JSON.stringify(jsonPayload, null, 2)}
          </pre>
        </details>
      </Panel>

      <footer className="text-center text-xs text-slate-500 py-6 mt-2 border-t border-slate-200">
        JyotishAI Engine · {generated} · {data.engine_version} ·{" "}
        {report.disclaimer ?? "For educational guidance only."}
      </footer>
    </div>
  );
}
