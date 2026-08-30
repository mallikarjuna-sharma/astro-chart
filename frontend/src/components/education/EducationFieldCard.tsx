import type { EducationFieldResult } from "@/lib/pyjhora/types";
import {
  institutionExamples,
  stageBoxClass,
} from "@/lib/education-report/card-helpers";
import { domainColor, domainIcon } from "@/lib/education-report/utils";
import { cn } from "@/lib/utils";

interface Props {
  rank: number;
  field: EducationFieldResult;
}

export function EducationFieldCard({ rank, field }: Props) {
  const color = domainColor(field.domain);
  const icon = domainIcon(field.domain);
  const cm = field.confidence_matrix ?? {};
  const alignment = cm.alignment_confidence ?? 0;

  const ap = field.academic_path ?? {};
  const it = field.institutional_tier ?? {};
  const reg = field.registry ?? {};

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

  const instExamples = institutionExamples(it, reg);

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
        {ap.path_stages?.length ? (
          <div>
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
