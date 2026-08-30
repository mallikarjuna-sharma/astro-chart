import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Callout, Meter, ProseBlock, Tag } from "@/components/report/primitives";
import type { CareerTimelineBlock } from "@/lib/pyjhora/types";
import {
  asHtmlString,
  careerWeather,
  contradictionCheck,
  d10Subscores,
  d10Verdict,
  familyGuidance,
  fmtDate,
  formatConfidence,
  periodBadge,
  scoreMatrix,
  yearLabel,
} from "@/lib/career-timeline/helpers";
import { Globe2 } from "lucide-react";

export function CareerRoadmapCard({ block, index }: { block: CareerTimelineBlock; index: number }) {
  const score = block.career_score ?? 0;
  const weather = careerWeather(score);
  const badge = periodBadge(block);
  const matrix = scoreMatrix(block);
  const cx = contradictionCheck(block);
  const d10 = d10Verdict(block);
  const d10Subs = d10Subscores(block);
  const family = familyGuidance(block.event_type);
  const sub = (block.sub_scores ?? {}) as Record<string, unknown>;
  const yogas = (sub.active_yogas as string[] | undefined) ?? [];
  const eventLabel = (block.event_type ?? "STABILITY").replace(/_/g, " ").replace(/^FORECAST /i, "");
  const netColor =
    cx.net === "Favorable" ? "text-success" : cx.net === "Challenging" ? "text-danger" : "text-warn";

  const careerRisk = block.career_risk as Record<string, unknown> | undefined;
  const severity = careerRisk?.severity as string | undefined;

  return (
    <article
      id={`period-${index + 1}`}
      className="w-full rounded-2xl border border-border bg-card p-5 md:p-6 shadow-sm scroll-mt-24 text-left"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-2">
        <span
          className={
            "text-[10px] font-bold uppercase tracking-[0.08em] px-2 py-0.5 rounded-full " +
            (badge === "Current"
              ? "bg-gold/15 text-gold border border-gold/30"
              : "bg-muted text-muted-foreground border border-border")
          }
        >
          {badge}
        </span>
        <h3 className="font-serif text-xl font-bold text-foreground">{yearLabel(block.start_date, block.end_date)}</h3>
        <span className="w-full sm:w-auto sm:ml-auto text-sm text-muted-foreground text-left">
          {weather.emoji} {weather.label}
        </span>
      </div>

      <p className="text-sm text-muted-foreground mb-4">
        {block.md_lord}–{block.ad_lord} · {fmtDate(block.start_date)} → {fmtDate(block.end_date)}
      </p>

      <div className="flex flex-wrap gap-2 mb-4">
        <Tag tone="muted" className="capitalize">
          {eventLabel.toLowerCase()}
        </Tag>
        {block.is_primary_opportunity ? <Tag tone="royal">Primary opportunity</Tag> : null}
        {block.foreign_opportunity ? (
          <Tag tone="info">
            <Globe2 className="w-3 h-3" /> Foreign
          </Tag>
        ) : null}
        {block.domain_tag ? <Tag tone="muted">{block.domain_tag}</Tag> : null}
      </div>

      <div className="text-[11px] font-bold uppercase tracking-[0.06em] text-royal mb-1">In Plain Language</div>
      {block.llm_plain_language_html ? (
        <ProseBlock className="text-sm leading-relaxed mb-4" html={asHtmlString(block.llm_plain_language_html)} />
      ) : block.narrative_hint ? (
        <p className="text-sm leading-relaxed text-foreground/90 mb-4 border-l-2 border-gold/40 pl-3">
          {block.narrative_hint}
        </p>
      ) : block.llm_ad_narrative_html ? (
        <ProseBlock className="text-sm leading-relaxed mb-4" html={asHtmlString(block.llm_ad_narrative_html)} />
      ) : null}

      {block.llm_astro_explanation_html ? (
        <>
          <div className="text-[11px] font-bold uppercase tracking-[0.06em] text-royal mb-1 mt-2">
            Astrological Explanation
          </div>
          <ProseBlock
            className="text-sm leading-relaxed mb-4 text-muted-foreground"
            html={asHtmlString(block.llm_astro_explanation_html)}
          />
        </>
      ) : null}

      {block.kp_promotion_override_label || block.kp_override_applied ? (
        <Callout tone="warn" label="KP override" className="mb-4 text-sm">
          Promotion-significator houses (2/6/10/11) are weak while foreign/job-change or leadership houses are
          strong — final read: {String(block.kp_promotion_override_label || block.event_type)}.
          {block.kp_override_reason ? ` ${String(block.kp_override_reason)}` : ""}
        </Callout>
      ) : null}

      {yogas.length ? (
        <div className="space-y-1.5 mb-4">
          {yogas.map((y) => (
            <div key={y} className="text-xs rounded-lg border border-border/70 bg-muted/30 px-3 py-2">
              <strong>{y.replace(/_/g, " ")}</strong>
            </div>
          ))}
        </div>
      ) : null}

      {matrix.length ? (
        <div className="mb-4 rounded-xl border border-border bg-muted/20 p-4">
          <div className="text-sm font-semibold mb-3">Score Breakdown</div>
          <div className="space-y-2">
            {matrix.map(([label, value]) => (
              <div key={label} className="grid grid-cols-[120px_1fr_40px] items-center gap-2 text-xs">
                <span className="text-muted-foreground">{label}</span>
                <Meter value={Math.round(value * 100)} tone="gold" className="h-1.5" />
                <span className="tabular-nums font-medium text-right">{Math.round(value * 100)}%</span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">
            Note: promotion_score reflects raw promotion-potential signal strength before KP/D10/D9 override checks.
            final_event_type ({eventLabel}) is the result after those checks are applied.
          </p>
        </div>
      ) : null}

      {d10 ? (
        <div className="mb-4 rounded-xl border border-border bg-muted/20 p-4 space-y-2">
          <div className="text-sm font-semibold">D10 Structural Table (This Period)</div>
          <p className="text-xs text-muted-foreground">{d10.occupancy}</p>
          <p className="text-sm">
            <strong>D10 Manifestation:</strong> {d10.manifest}
          </p>
          <p className="text-sm font-semibold" style={{ color: d10.color }}>
            D10 Verdict: {d10.verdict}
          </p>
        </div>
      ) : null}

      {cx.supporting.length || cx.blocking.length ? (
        <div className="mb-4 rounded-xl border border-border bg-muted/20 p-4">
          <div className="text-sm font-semibold mb-2">Contradiction Check</div>
          <div className="grid md:grid-cols-2 gap-4 text-xs">
            <div>
              <div className="font-bold text-success mb-1">Supporting</div>
              <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                {(cx.supporting.length ? cx.supporting : ["None identified"]).map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
            <div>
              <div className="font-bold text-danger mb-1">Blocking</div>
              <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                {(cx.blocking.length ? cx.blocking : ["None identified"]).map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          </div>
          <div className={`text-sm font-semibold mt-3 ${netColor}`}>Net: {cx.net}</div>
        </div>
      ) : null}

      <div className="mb-4 rounded-xl border border-gold/20 bg-gold/5 p-4">
        <div className="font-semibold text-foreground mb-1">{family.headline}</div>
        <p className="text-sm text-muted-foreground leading-relaxed">{family.body}</p>
        {severity && severity !== "mild" ? (
          <div className="mt-3 pt-3 border-t border-border/60 text-xs space-y-1">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Severity</span>
              <span className="font-medium capitalize">{severity}</span>
            </div>
          </div>
        ) : null}
      </div>

      {d10Subs.length ? (
        <div className="mb-4 text-sm">
          <div className="font-semibold mb-2">D10 Sub-Dimension Scores</div>
          {d10Subs.map((row) => (
            <div key={row.label} className="flex justify-between py-0.5 text-xs border-b border-border/40 last:border-0">
              <span className="text-muted-foreground">{row.label}</span>
              <strong className="tabular-nums">{row.value.toFixed(2)}</strong>
            </div>
          ))}
        </div>
      ) : null}

      <Accordion type="single" collapsible>
        <AccordionItem value="details" className="border-t border-border">
          <AccordionTrigger className="text-xs font-bold uppercase tracking-wide text-muted-foreground hover:no-underline py-3">
            More detail — skills, sub-periods, remedies
          </AccordionTrigger>
          <AccordionContent className="space-y-4 pb-2">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              {block.confidence ? (
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Confidence</div>
                  <div className="font-medium">{formatConfidence(block.confidence)}</div>
                </div>
              ) : null}
              {block.career_track ? (
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Track</div>
                  <div className="font-medium">{block.career_track}</div>
                </div>
              ) : null}
              {block.jaimini_role ? (
                <div className="col-span-2">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Jaimini role</div>
                  <div className="font-medium">{block.jaimini_role}</div>
                </div>
              ) : null}
              {block.active_houses?.length ? (
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Houses</div>
                  <div className="font-medium">{block.active_houses.join(", ")}</div>
                </div>
              ) : null}
            </div>

            {block.skill_recommendations?.length ? (
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1.5 font-bold">
                  Skills to build
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {block.skill_recommendations.map((sk) => (
                    <Tag key={sk} tone="muted">
                      {sk}
                    </Tag>
                  ))}
                </div>
              </div>
            ) : null}

            {block.remedies?.length ? (
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1.5 font-bold">Remedies</div>
                <ul className="text-xs text-muted-foreground list-disc pl-4 space-y-0.5">
                  {block.remedies.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {block.pratyantardashas?.length ? (
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1.5 font-bold">
                  Sub-periods ({block.pratyantardashas.length})
                </div>
                <div className="space-y-1.5">
                  {block.pratyantardashas.map((pd, i) => (
                    <div key={i} className="rounded-lg border border-border bg-background/40 p-2.5 text-xs">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="font-medium">{pd.pd_lord as string}</span>
                        <span className="text-muted-foreground tabular-nums">
                          {fmtDate(pd.start_date as string)} → {fmtDate(pd.end_date as string)}
                        </span>
                        {typeof pd.pd_score === "number" ? (
                          <span className="tabular-nums font-medium">{Math.round(pd.pd_score * 100)}%</span>
                        ) : null}
                      </div>
                      {pd.llm_narrative_html ? (
                        <ProseBlock className="mt-1 text-muted-foreground" html={asHtmlString(pd.llm_narrative_html)} />
                      ) : pd.hint ? (
                        <p className="mt-1 text-muted-foreground">{pd.hint as string}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </article>
  );
}
