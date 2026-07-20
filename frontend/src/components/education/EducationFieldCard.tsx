import type { ReactNode } from "react";
import type { EducationFieldResult } from "@/lib/pyjhora/types";
import {
  astroReason,
  burnoutBadgeClass,
  geoBadgeClass,
  institutionExamples,
  parentReason,
  parseVerifiedFactors,
  stageBoxClass,
  wealthBadgeClass,
} from "@/lib/education-report/card-helpers";
import { domainColor, domainIcon } from "@/lib/education-report/utils";
import { cn } from "@/lib/utils";

interface Props {
  rank: number;
  field: EducationFieldResult;
}

const CONF_BARS = [
  { key: "knrao_pct" as const, label: "KN Rao (Classical)", color: "#818cf8" },
  { key: "kp_pct" as const, label: "KP (Micro-Timing)", color: "#a78bfa" },
  { key: "jaimini_pct" as const, label: "Jaimini (Aptitude)", color: "#22d3ee" },
  { key: "parashara_pct" as const, label: "Parashara (Strength)", color: "#34d399" },
  { key: "sbc_pct" as const, label: "SBC", color: "#fbbf24" },
];

function InsightBadge({
  className,
  title,
  children,
}: {
  className: string;
  title?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 text-[10.5px] font-bold tracking-wide px-2.5 py-0.5 rounded-full border",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function EducationFieldCard({ rank, field }: Props) {
  const color = domainColor(field.domain);
  const icon = domainIcon(field.domain);
  const cm = field.confidence_matrix ?? {};
  const alignment = cm.alignment_confidence ?? 0;
  const isCluster = field.chart_type?.is_cluster ?? false;
  const confLabel = isCluster ? "Distributed Fit" : "Alignment Confidence";

  const wp = field.wealth_potential ?? {};
  const geo = field.geo_suitability ?? {};
  const br = field.burnout_risk ?? {};
  const mn = field.micro_niches ?? {};
  const em = field.explainability_matrix ?? {};
  const sbc = field.sbc_detail ?? {};
  const ap = field.academic_path ?? {};
  const it = field.institutional_tier ?? {};
  const reg = field.registry ?? {};

  const vf = parseVerifiedFactors(field.verified_factors);
  const sbcScore = field.sbc_event_score ?? field.smi;
  const instExamples = institutionExamples(it, reg);

  const progMap: Record<string, string> = {
    UG: reg.ug_program ?? "",
    PG: reg.pg_program ?? "",
    PhD: reg.phd_program ?? "",
  };
  const nicheMap: Record<string, string> = {
    UG: reg.ug_niche ?? "",
    PG: reg.pg_niche ?? "",
    PhD: reg.phd_niche ?? "",
  };

  const wealthLevel = wp.wealth_potential ?? "";
  const geoLabel =
    geo.geo_suitability ??
    ((geo.geo_foreign_pct ?? 0) >= 60
      ? "International"
      : (geo.geo_domestic_pct ?? 0) >= 60
        ? "Domestic"
        : "Hybrid");
  const burnoutLevel = br.burnout_risk ?? "";

  return (
    <article className="panel panel-hover p-5">
      <header className="flex flex-wrap justify-between items-start gap-3 mb-4">
        <div className="flex items-center gap-2.5 text-lg font-semibold text-foreground">
          <span className="w-8 h-8 rounded-full gradient-gold text-primary-foreground flex items-center justify-center text-sm font-bold shrink-0">
            {rank}
          </span>
          {field.field_label}
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="text-[0.8rem] font-semibold text-white px-2.5 py-1 rounded-md shadow-sm" style={{ background: color }}>
            {icon} {field.domain.charAt(0).toUpperCase() + field.domain.slice(1)}
          </span>
          <span className="text-[0.8rem] font-semibold px-2.5 py-1 rounded-md bg-secondary text-secondary-foreground">
            {field.final_score.toFixed(1)} pts
          </span>
          {alignment > 0 ? (
            <span className="text-[10px] font-semibold px-2.5 py-1 rounded-md bg-royal/15 text-royal border border-royal/25">
              {alignment}% Aligned
            </span>
          ) : null}
        </div>
      </header>

      <div className="space-y-3">
        <section className="bg-success/8 border border-success/25 rounded-xl px-4 py-3.5">
          <div className="text-[11px] font-bold text-success uppercase tracking-wider mb-2">
            Why this field suits your child
          </div>
          <p className="text-[0.98rem] text-foreground leading-relaxed whitespace-pre-line">{parentReason(field)}</p>
        </section>

        <section className="bg-muted/60 border-l-2 border-gold rounded-r-lg px-4 py-3">
          <div className="text-[0.8rem] uppercase tracking-wide font-bold text-muted-foreground mb-1">
            Astrological Signature
          </div>
          <p className="text-[0.9rem] font-mono text-foreground/75">{astroReason(field)}</p>
        </section>

        {vf.positive.length || vf.negative.length ? (
          <div className="flex flex-wrap gap-1 items-center">
            <span className="text-[9px] font-extrabold uppercase tracking-wider text-muted-foreground mr-1">Boosts</span>
            {vf.positive.map((p) => (
              <span key={p} className="text-[9.5px] font-semibold px-2 py-0.5 rounded-lg bg-success/12 text-success border border-success/25">
                {p}
              </span>
            ))}
            {vf.negative.map((p) => (
              <span key={p} className="text-[9.5px] font-semibold px-2 py-0.5 rounded-lg bg-danger/12 text-danger border border-danger/25">
                {p}
              </span>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-1.5">
          {field.boost_pct ? (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-success/12 text-success border border-success/25">
              +{Math.round(field.boost_pct)}% gap boost
            </span>
          ) : null}
          {field.timing_band ? (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-info/12 text-info border border-info/25">
              ⏱ {field.timing_band}
            </span>
          ) : null}
          {sbcScore != null ? (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-royal/12 text-royal border border-royal/25">
              SBC {Math.round(sbcScore)}
            </span>
          ) : null}
          {field.pre_norm_score != null ? (
            <span
              title={field.norm_note}
              className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-muted text-muted-foreground border border-border cursor-help"
            >
              pre-norm {field.pre_norm_score.toFixed(1)}
            </span>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-1.5 pt-2.5 border-t border-border/60">
          {wealthLevel ? (
            <InsightBadge className={wealthBadgeClass(wealthLevel)} title={wp.wealth_note}>
              {wealthLevel === "High" ? "▲" : wealthLevel === "Low" ? "▼" : "●"} Wealth: {wealthLevel}
            </InsightBadge>
          ) : null}
          {(geo.geo_foreign_pct ?? 0) > 0 || geoLabel ? (
            <InsightBadge className={geoBadgeClass(geoLabel)} title={geo.geo_note}>
              ✈ {geoLabel.includes("International") ? "International" : geoLabel.includes("Domestic") ? "Domestic" : "Hybrid"}
            </InsightBadge>
          ) : null}
          {burnoutLevel ? (
            <InsightBadge className={burnoutBadgeClass(burnoutLevel)} title={br.burnout_note}>
              ● Burnout: {burnoutLevel}
            </InsightBadge>
          ) : null}
        </div>

        {(wp.wealth_connections?.length || geo.geo_foreign_pct != null || br.stress_flags?.length) ? (
          <div className="flex flex-wrap gap-2 pt-2 border-t border-border/60">
            {wp.wealth_connections?.length || wp.wealth_note ? (
              <div className="flex-1 min-w-[150px] bg-surface-soft/60 rounded-lg p-2.5 border border-border">
                <div className="text-[9px] font-extrabold uppercase tracking-wider text-muted-foreground mb-1">Wealth Drivers</div>
                {wp.wealth_connections?.length ? (
                  <p className="text-[10.5px] text-foreground/80 leading-snug">
                    {wp.wealth_connections.slice(0, 4).join(" • ")}
                  </p>
                ) : null}
                {wp.wealth_note ? <p className="text-[10px] text-muted-foreground italic mt-1">{wp.wealth_note}</p> : null}
              </div>
            ) : null}
            {(geo.geo_foreign_pct ?? 0) > 0 || (geo.geo_domestic_pct ?? 0) > 0 ? (
              <div className="flex-1 min-w-[150px] bg-surface-soft/60 rounded-lg p-2.5 border border-border">
                <div className="text-[9px] font-extrabold uppercase tracking-wider text-muted-foreground mb-1">Geography Split</div>
                <div className="flex items-center gap-1.5 text-[9.5px] text-muted-foreground">
                  <span className="min-w-[55px]">🌍 {geo.geo_foreign_pct ?? 0}% intl</span>
                  <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-info rounded-full" style={{ width: `${geo.geo_foreign_pct ?? 0}%` }} />
                  </div>
                  <span>🏠 {geo.geo_domestic_pct ?? 0}%</span>
                </div>
                {geo.geo_note ? <p className="text-[10px] text-muted-foreground italic mt-1">{geo.geo_note}</p> : null}
              </div>
            ) : null}
            {br.stress_flags?.length || br.burnout_note ? (
              <div className="flex-1 min-w-[150px] bg-surface-soft/60 rounded-lg p-2.5 border border-border">
                <div className="text-[9px] font-extrabold uppercase tracking-wider text-muted-foreground mb-1">Stress Flags</div>
                {br.stress_flags?.slice(0, 3).map((f) => (
                  <p key={f} className="text-[10px] text-warn leading-snug">
                    ⚡ {f}
                  </p>
                ))}
                {br.burnout_note ? (
                  <p className="text-[10px] text-warn/80 italic mt-1">{br.burnout_note}</p>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {field.top_karakas?.length ? (
          <div className="flex flex-wrap gap-1.5">
            {field.top_karakas.map((k) => (
              <span
                key={k}
                className="text-[10.5px] font-bold px-2.5 py-0.5 rounded-xl bg-info/12 text-info border border-info/25"
              >
                {k}
              </span>
            ))}
          </div>
        ) : null}

        {em.structural_friction_flag ? (
          <div className="flex gap-2 bg-warn/8 border-l-2 border-warn rounded-r-lg px-3 py-2 text-[11px] text-warn">
            <span className="shrink-0">⚠</span>
            <span>
              {em.structural_friction_flag}
              {em.paradigm_spread ? (
                <span className="text-warn/70 text-[9.5px] font-semibold ml-1">
                  (paradigm spread {em.paradigm_spread.toFixed(1)})
                </span>
              ) : null}
            </span>
          </div>
        ) : null}

        {mn.micro_niches?.length ? (
          <div>
            <div className="flex flex-wrap gap-1.5">
              {mn.micro_niches.map((n) => (
                <span
                  key={n}
                  className="text-[10.5px] font-semibold px-2.5 py-0.5 rounded-xl bg-warn/10 text-warn border border-warn/25"
                >
                  {n}
                </span>
              ))}
            </div>
            {mn.niche_driver ? (
              <p className="text-[10px] text-muted-foreground mt-1">Sub-specialisation driver: {mn.niche_driver}</p>
            ) : null}
          </div>
        ) : null}

        {Object.keys(cm).length > 0 ? (
          <div className="bg-surface-soft/60 rounded-lg p-3 border border-border">
            <div className="text-xs font-bold text-muted-foreground mb-1.5">
              {confLabel}: <span className="text-royal text-sm">{alignment}%</span>
            </div>
            <div className="flex flex-col gap-1.5">
              {CONF_BARS.map(({ key, label, color: barColor }) => {
                const pct = cm[key] ?? 0;
                const sbcLabel =
                  key === "sbc_pct" && field.sbc_exam_date
                    ? `SBC (${field.sbc_exam_date})`
                    : label;
                return (
                  <div key={key} className="flex items-center gap-2">
                    <span className="text-[10.5px] font-semibold text-muted-foreground w-[110px] shrink-0">
                      {sbcLabel}
                    </span>
                    <div className="flex-1 h-[7px] bg-muted rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: barColor }} />
                    </div>
                    <span className="text-[10.5px] font-bold text-muted-foreground w-8 text-right shrink-0">{pct}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {sbc.career_nakshatras?.length || sbc.key_protections?.length || sbc.key_obstructions?.length ? (
          <details className="rounded-lg bg-royal/8 border border-royal/25 px-3 py-2 text-[10.5px]">
            <summary className="font-bold text-royal cursor-pointer list-none flex items-center gap-1.5">
              SBC Timing Detail — {field.sbc_exam_date ?? "Boards"}
            </summary>
            {sbc.career_nakshatras?.length ? (
              <p className="text-royal font-semibold mt-1.5">
                Career Nakshatras: {sbc.career_nakshatras.join(" • ")}
              </p>
            ) : null}
            {sbc.key_protections?.map((p) => (
              <p key={p} className="text-success pl-1">
                ✓ {p}
              </p>
            ))}
            {sbc.key_obstructions?.map((o) => (
              <p key={o} className="text-danger pl-1">
                ✗ {o}
              </p>
            ))}
          </details>
        ) : null}

        {ap.path_stages?.length ? (
          <div className="pt-3 border-t border-border/60">
            <div className="text-[10.5px] font-bold text-gold uppercase tracking-wider mb-2">
              🎓 Academic Execution Path
            </div>
            <div className="flex flex-wrap items-center gap-0">
              {ap.path_stages.map((stage, i) => {
                const stg = stage.stage;
                const rec = stage.recommended ?? false;
                const progName = progMap[stg] || stage.label || stg;
                const subNiche = nicheMap[stg];
                return (
                  <div key={stg} className="flex items-center">
                    {i > 0 ? <span className="text-muted-foreground px-1 text-sm">→</span> : null}
                    <div
                      className={cn(
                        "px-3 py-1.5 rounded-lg border text-center text-[11px]",
                        stageBoxClass(stg, rec),
                      )}
                    >
                      <div className="font-bold leading-snug">
                        {progName}
                        {rec ? " ✓" : ""}
                      </div>
                      {stage.strength_label ? (
                        <small className="block text-[9px] font-normal opacity-75">{stage.strength_label}</small>
                      ) : null}
                      {subNiche ? (
                        <div className="text-[9.5px] text-muted-foreground italic mt-0.5 leading-snug">{subNiche}</div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
            {ap.depth_label ? <p className="text-[10px] text-muted-foreground mt-1.5">{ap.depth_label}</p> : null}
          </div>
        ) : null}

        {it.tier ? (
          <div className="flex gap-2 items-start bg-warn/8 rounded-lg border border-warn/25 px-3 py-2.5">
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-warn bg-warn/15 rounded-md px-2 py-0.5 shrink-0 whitespace-nowrap">
              {it.tier}
            </span>
            <div className="text-[11px] text-foreground/80 leading-snug">
              {it.archetype ? <strong className="text-foreground">{it.archetype}</strong> : null}
              {instExamples.length ? (
                <>
                  <br />
                  <span className="text-muted-foreground">{instExamples.join(" • ")}</span>
                </>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </article>
  );
}
