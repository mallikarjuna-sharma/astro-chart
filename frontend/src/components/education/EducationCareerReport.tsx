import { useMemo, useState, type ReactNode } from "react";
import type { EducationAnalysisResponse, EducationFieldResult } from "@/lib/pyjhora/types";
import {
  buildReportLayout,
  domainColor,
  domainIcon,
  formatExam,
  scoreLabel,
  scorePct,
} from "@/lib/education-report/utils";
import { cn } from "@/lib/utils";

interface Props {
  data: EducationAnalysisResponse;
}

function RegistryTable({
  reg,
  view,
}: {
  reg: EducationFieldResult["registry"];
  view: "parent" | "astro";
}) {
  if (!reg) return null;
  const exams = (reg.admission_exams ?? []).map(formatExam);
  const careers = (reg.career_paths ?? []).slice(0, 5).join(", ") || "—";

  const rows: { label: string; value: ReactNode }[] = [];
  if (view === "parent") {
    if (reg.ug_program) rows.push({ label: "UG Programme", value: reg.ug_program });
    if (reg.pg_program) rows.push({ label: "PG Programme", value: reg.pg_program });
    if (reg.phd_program) rows.push({ label: "PhD / Research", value: reg.phd_program });
    rows.push({
      label: "Entrance Exams",
      value: exams.length ? exams.join(" · ") : "—",
    });
    rows.push({ label: "Career Paths", value: careers });
  } else {
    if (reg.ug_program) {
      rows.push({
        label: "UG",
        value: (
          <>
            {reg.ug_program}
            {reg.ug_niche ? <span className="block text-[11px] text-muted-foreground">{reg.ug_niche}</span> : null}
          </>
        ),
      });
    }
    if (reg.pg_program) {
      rows.push({
        label: "PG",
        value: (
          <>
            {reg.pg_program}
            {reg.pg_niche ? <span className="block text-[11px] text-muted-foreground">{reg.pg_niche}</span> : null}
          </>
        ),
      });
    }
    if (reg.phd_program) {
      rows.push({
        label: "PhD",
        value: (
          <>
            {reg.phd_program}
            {reg.phd_niche ? <span className="block text-[11px] text-muted-foreground">{reg.phd_niche}</span> : null}
          </>
        ),
      });
    }
    rows.push({ label: "Entrance", value: exams.length ? exams.join(" · ") : "—" });
    rows.push({ label: "Career", value: careers });
    if (reg.niche) rows.push({ label: "Specialisation", value: reg.niche });
  }

  if (!rows.length) return null;

  return (
    <table className="w-full text-sm mt-3">
      <tbody>
        {rows.map((row) => (
          <tr key={row.label} className="border-t border-border/60">
            <td className="py-1.5 pr-3 font-semibold text-muted-foreground whitespace-nowrap w-32 align-top">
              {row.label}
            </td>
            <td className="py-1.5">{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FieldCard({
  rankLabel,
  field,
  topScore,
  view,
  soul = false,
}: {
  rankLabel: string;
  field: EducationFieldResult;
  topScore: number;
  view: "parent" | "astro";
  soul?: boolean;
}) {
  const color = soul ? "#7b1fa2" : "#5c6bc0";
  const badge = domainColor(field.domain);
  const reason =
    view === "parent"
      ? field.llm_parent_reason?.trim() ||
        `This field aligns well with your child's natural strengths in ${field.domain}.`
      : field.llm_astrological_reason?.trim() ||
        "Score driven by planetary affinity and domain-aptitude convergence.";

  const boosts = Object.entries(field.gap_breakdown ?? {})
    .filter(([, v]) => v > 0.001)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  const penalties = Object.entries(field.gap_breakdown ?? {})
    .filter(([, v]) => v < -0.001)
    .sort((a, b) => a[1] - b[1])
    .slice(0, 3);
  const planets = Object.entries(field.top_affinity_planets ?? {}).slice(0, 3);
  const sc = field.score_components ?? {};

  return (
    <div
      className="rounded-xl p-5 shadow-sm relative"
      style={{
        borderLeft: `5px solid ${color}`,
        background: soul ? "#fdf3ff" : "#f8f9fe",
      }}
    >
      {soul ? (
        <span
          className="absolute top-3 right-4 text-[11px] font-bold text-white px-3 py-0.5 rounded-full"
          style={{ background: "linear-gradient(135deg,#6a1b9a,#ab47bc)" }}
        >
          ✨ Soul-Aligned
        </span>
      ) : null}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <span className="text-2xl font-extrabold" style={{ color: "#283593" }}>
          {rankLabel}
        </span>
        <span className="text-2xl">{domainIcon(field.domain)}</span>
        <div className="flex-1 min-w-[180px]">
          <div className="text-lg font-bold">{field.field_label}</div>
          <span
            className="inline-block text-[10px] font-bold text-white px-2 py-0.5 rounded-full mt-1"
            style={{ background: badge }}
          >
            {field.domain.toUpperCase()}
          </span>
        </div>
        {view === "parent" ? (
          <div className="min-w-[120px] text-right">
            <div className="h-2 w-[120px] bg-muted rounded overflow-hidden ml-auto">
              <div
                className="h-full rounded"
                style={{ width: `${scorePct(field.final_score)}%`, background: color }}
              />
            </div>
            <div className="text-[11px] font-bold mt-1" style={{ color }}>
              {scoreLabel(field.final_score, topScore)}
            </div>
          </div>
        ) : (
          <div className="text-right min-w-[80px]">
            <div className="text-xl font-extrabold text-emerald-800">{field.final_score.toFixed(1)}</div>
            <div className="text-[11px] text-muted-foreground">
              base {(sc.blended ?? 0).toFixed(1)} +{(sc.gap_boost_pct ?? 0).toFixed(0)}% -
              {(sc.gap_penalty_pct ?? 0).toFixed(0)}%
            </div>
          </div>
        )}
      </div>
      <div className="text-sm leading-relaxed bg-white/60 rounded-lg p-3 mb-2">{reason}</div>
      {view === "astro" ? (
        <div className="flex flex-wrap gap-2 text-[11px] mb-2">
          {planets.map(([p, w]) => (
            <span key={p} className="bg-indigo-50 text-indigo-900 px-2 py-0.5 rounded-lg font-semibold">
              {p} {w.toFixed(2)}
            </span>
          ))}
          {boosts.map(([k, v]) => (
            <span key={k} className="bg-emerald-50 text-emerald-800 px-2 py-0.5 rounded-lg font-semibold">
              +{v.toFixed(3)} {k}
            </span>
          ))}
          {penalties.map(([k, v]) => (
            <span key={k} className="bg-rose-50 text-rose-800 px-2 py-0.5 rounded-lg font-semibold">
              {v.toFixed(3)} {k}
            </span>
          ))}
        </div>
      ) : null}
      <RegistryTable reg={field.registry} view={view} />
    </div>
  );
}

function RemainingTable({
  all,
  shownIds,
  topScore,
}: {
  all: EducationFieldResult[];
  shownIds: Set<string>;
  topScore: number;
}) {
  const rest = all.filter((r) => !shownIds.has(r.field_id)).slice(0, 15);
  if (!rest.length) return null;

  return (
    <div className="mt-8">
      <h3 className="text-base font-bold text-indigo-950 mb-3">Other High-Scoring Fields</h3>
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm min-w-[700px]">
          <thead>
            <tr className="bg-indigo-900 text-white">
              <th className="px-3 py-2 text-left w-10">#</th>
              <th className="px-3 py-2 text-left">Field</th>
              <th className="px-3 py-2 text-right">Score</th>
              <th className="px-3 py-2 text-left">Match</th>
              <th className="px-3 py-2 text-left">UG Programme</th>
              <th className="px-3 py-2 text-left">Key Exam</th>
            </tr>
          </thead>
          <tbody>
            {rest.map((r, i) => (
              <tr key={r.field_id} className="border-t border-border hover:bg-indigo-50/40">
                <td className="px-3 py-2 font-extrabold text-indigo-900 text-center">{i + 1}</td>
                <td className="px-3 py-2">
                  {domainIcon(r.domain)} <strong>{r.field_label}</strong>{" "}
                  <span
                    className="text-[9px] font-bold text-white px-1.5 py-0.5 rounded-full align-middle"
                    style={{ background: domainColor(r.domain) }}
                  >
                    {r.domain.toUpperCase()}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-bold text-emerald-800">{r.final_score.toFixed(1)}</td>
                <td className="px-3 py-2 text-muted-foreground">{scoreLabel(r.final_score, topScore)}</td>
                <td className="px-3 py-2 text-muted-foreground">{r.registry?.ug_program ?? "—"}</td>
                <td className="px-3 py-2 text-muted-foreground">
                  {(r.registry?.admission_exams ?? []).slice(0, 2).map(formatExam).join(" · ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function EducationCareerReport({ data }: Props) {
  const [view, setView] = useState<"parent" | "astro">("parent");
  const layout = useMemo(() => buildReportLayout(data), [data]);
  const { student, summary } = data;
  const generated = new Date(data.generated_at).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <div className="rounded-xl overflow-hidden border border-border bg-[#f0f2f8] text-[#1a1a2e]">
      <div
        className="px-6 py-5 text-white"
        style={{ background: "linear-gradient(135deg,#1a237e,#283593)" }}
      >
        <span className="inline-block bg-white/20 rounded-full px-3 py-0.5 text-[11px] font-extrabold tracking-widest mb-2">
          JYOTISHAI
        </span>
        <h2 className="text-xl font-bold">
          Career Guidance Report — {student.name ?? "Student"}
        </h2>
        <p className="text-sm opacity-70 mt-1">
          AI-powered Vedic Astrology Career Analysis · {generated} · {data.engine_version}
        </p>
      </div>

      <div className="mx-5 mt-5 bg-white rounded-xl p-5 shadow-sm flex flex-wrap gap-6">
        <div className="flex-1 min-w-[200px]">
          <div className="text-xl font-extrabold text-indigo-950">{student.name ?? "Student"}</div>
          <div className="text-sm text-muted-foreground mt-1">
            {student.dob ? <>DOB: <strong>{student.dob}</strong> · </> : null}
            {student.current_age != null ? <>Age: <strong>{Math.floor(student.current_age)}</strong> · </> : null}
            Lagna: <strong>{student.lagna_sign ?? "—"}</strong>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-4 text-sm">
            {[
              ["AK · Soul", student.atmakaraka],
              ["AmK · Career", student.amatyakaraka],
              ["H10 Lord", student.h10_lord],
            ].map(([role, planet]) => (
              <div key={role}>
                <div className="text-[10px] font-bold uppercase text-muted-foreground tracking-wide">{role}</div>
                <div className="font-semibold text-indigo-950">{planet ?? "—"}</div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {(student.yogas ?? []).slice(0, 6).map((y) => (
              <span key={y} className="bg-violet-100 text-violet-900 text-[11px] font-semibold px-2 py-0.5 rounded-full">
                {y}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="mx-5 mt-4 inline-flex bg-indigo-100 rounded-lg p-1">
        {(["parent", "astro"] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={cn(
              "px-6 py-2 text-sm font-semibold rounded-md transition-all",
              view === v ? "bg-indigo-900 text-white shadow" : "text-indigo-600",
            )}
          >
            {v === "parent" ? "👨‍👩‍👧 For Parents" : "🔭 For Astrologers"}
          </button>
        ))}
      </div>

      <div className="px-5 pb-8 pt-4">
        {view === "parent" && summary.parent_overview ? (
          <div className="bg-amber-50 border-l-[5px] border-amber-500 rounded-lg p-4 text-sm mb-4">
            {summary.parent_overview}
          </div>
        ) : null}
        {view === "astro" && summary.astro_overview ? (
          <div className="bg-emerald-50 border-l-[5px] border-emerald-600 rounded-lg p-4 text-sm mb-4 text-emerald-950">
            {summary.astro_overview}
          </div>
        ) : null}

        {view === "astro" && summary.active_dasha_lord ? (
          <p className="text-xs text-muted-foreground mb-3">
            Active Mahadasha lord: <strong>{summary.active_dasha_lord}</strong>
          </p>
        ) : null}

        <h3 className="text-base font-bold text-indigo-950 mb-3">
          {view === "parent" ? "Your Child's Top Career Recommendations" : "Top Match Fields"}
        </h3>

        {layout.matchFields.length < 5 ? (
          <p className="text-xs text-muted-foreground italic mb-3">
            Showing {layout.matchFields.length} top recommended field
            {layout.matchFields.length !== 1 ? "s" : ""}. Additional fields appear in the table below.
          </p>
        ) : null}

        <div className="flex flex-col gap-4">
          {layout.matchFields.map((f, i) => (
            <FieldCard
              key={f.field_id}
              rankLabel={`#${i + 1}`}
              field={f}
              topScore={layout.topScore}
              view={view}
            />
          ))}
        </div>

        {layout.soulField ? (
          <>
            <div className="flex items-center gap-3 my-6">
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-purple-500 to-transparent" />
              <span className="text-sm font-bold text-purple-800 whitespace-nowrap">✨ Soul-Aligned Recommendation</span>
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-purple-500 to-transparent" />
            </div>
            <FieldCard
              rankLabel="Soul"
              field={layout.soulField}
              topScore={layout.topScore}
              view={view}
              soul
            />
          </>
        ) : null}

        <RemainingTable all={layout.sorted} shownIds={layout.shownIds} topScore={layout.topScore} />
      </div>

      <div className="text-center text-xs text-muted-foreground py-4 border-t border-border/60">
        JyotishAI Engine · {generated} · For educational guidance only.
      </div>
    </div>
  );
}
