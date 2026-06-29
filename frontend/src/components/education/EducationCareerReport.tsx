import { useMemo } from "react";
import type { ChartType, CorporateEntrepreneurial, EducationAnalysisResponse } from "@/lib/pyjhora/types";
import { EducationFieldCard } from "@/components/education/EducationFieldCard";
import { useDisplayName } from "@/hooks/use-display-name";

interface Props {
  data: EducationAnalysisResponse;
}

const TOP_N = 20;

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
        <div className="flex-1 h-2.5 rounded-full bg-gradient-to-r from-blue-500 to-amber-400 relative overflow-hidden">
          <div
            className="absolute right-0 top-0 h-full bg-white/35"
            style={{ width: `${entrepMask}%` }}
          />
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
    <div className="flex flex-wrap gap-4 items-start bg-gradient-to-br from-sky-50 to-sky-100 border-[1.5px] border-sky-400 rounded-2xl p-5 mb-5">
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

export function EducationCareerReport({ data }: Props) {
  const { student, summary } = data;
  const displayName = useDisplayName(student.name);
  const generated = new Date(data.generated_at).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

  const topFields = useMemo(
    () =>
      [...data.fields]
        .sort((a, b) => b.final_score - a.final_score || a.field_id.localeCompare(b.field_id))
        .slice(0, TOP_N),
    [data.fields],
  );

  const payload = data.report?.payload as Record<string, unknown> | undefined;
  const corpProfile = payload?.corporate_entrepreneurial as CorporateEntrepreneurial | undefined;
  const chartType =
    (topFields[0]?.chart_type as ChartType | undefined) ??
    (payload?.chart_type as ChartType | undefined) ??
    {};

  return (
    <div className="max-w-[1280px] mx-auto text-slate-800">
      <header className="text-center mb-10 pb-5 border-b-2 border-slate-200">
        <div className="text-[0.9rem] font-bold tracking-[0.2em] text-slate-500 uppercase mb-2.5">
          JyotishAI Career Engine
        </div>
        <h2 className="text-[2.5rem] font-extrabold text-slate-900 mb-4 leading-tight">
          {displayName}
        </h2>
        <div className="flex justify-center flex-wrap gap-3 text-[0.95rem] text-slate-500">
          {student.dob ? (
            <span className="bg-slate-200 px-3 py-1 rounded-full font-medium">DOB: {student.dob}</span>
          ) : null}
          {student.lagna_sign ? (
            <span className="bg-slate-200 px-3 py-1 rounded-full font-medium">Lagna: {student.lagna_sign}</span>
          ) : null}
          {student.atmakaraka ? (
            <span className="bg-slate-200 px-3 py-1 rounded-full font-medium">AK: {student.atmakaraka}</span>
          ) : null}
          {student.amatyakaraka ? (
            <span className="bg-slate-200 px-3 py-1 rounded-full font-medium">AmK: {student.amatyakaraka}</span>
          ) : null}
          <span className="bg-slate-200 px-3 py-1 rounded-full font-medium">Generated: {generated}</span>
        </div>
      </header>

      {corpProfile?.style_label || corpProfile?.corporate_pct != null ? (
        <CorporateGauge profile={corpProfile} />
      ) : null}

      <ClusterBanner chartType={chartType} />

      {summary.parent_overview ? (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-4 text-sm text-slate-800 mb-6 leading-relaxed">
          {summary.parent_overview}
        </div>
      ) : null}

      <div className="text-center text-[0.85rem] font-bold tracking-widest uppercase text-slate-500 mb-6">
        Top {Math.min(TOP_N, data.fields.length)} Fields
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
        {topFields.map((field, i) => (
          <EducationFieldCard key={field.field_id} rank={i + 1} field={field} />
        ))}
      </div>

      <footer className="text-center text-xs text-slate-500 py-6 mt-8 border-t border-slate-200">
        JyotishAI Engine · {generated} · {data.engine_version} · For educational guidance only.
      </footer>
    </div>
  );
}
