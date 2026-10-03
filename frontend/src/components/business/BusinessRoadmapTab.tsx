
import {
  Callout,
  Panel,
  SectionTitle,
  Tag,
  type Tone,
} from "@/components/report/primitives";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { 
  Briefcase, 
  TrendingUp, 
  Banknote, 
  Map, 
  CalendarClock, 
  AlertTriangle 
} from "lucide-react";
import type { BusinessPredictionResponse } from "@/lib/pyjhora/types";
import {
  asRecord,
  asString,
  asArray,
  badgeClass,
  fmtPct,
  getSectors,
  verdictClass,
  verdictLabel,
  KpiScoreCard,
} from "./business-report-utils";

interface Props {
  data: BusinessPredictionResponse;
}

function AshtakavargaPanel({ ashtakavarga }: { ashtakavarga: unknown }) {
  const a = asRecord(ashtakavarga);
  const years = asArray<Record<string, unknown>>(a.ranked_years ?? a.years);
  if (!Object.keys(a).length) {
    return <p className="text-[13px] text-muted-foreground italic">Not evaluated.</p>;
  }
  if (!years.length) {
    return (
      <>
        <p className="text-[13px] text-muted-foreground italic mb-2">Supplementary scan — did not affect the main recommendation.</p>
        <p className="text-[13px] text-foreground font-medium">
          {asString(a.status)}
          {a.note ? `: ${asString(a.note)}` : ""}
        </p>
      </>
    );
  }
  return (
    <div className="bg-card border border-border p-5 rounded-xl shadow-sm">
      <ul className="text-[13.5px] text-foreground space-y-2 font-medium">
        {years.map((y, i) => (
          <li key={i}>
            <span className="font-bold">{asString(y.year)}</span> <span className="text-muted-foreground mx-1">—</span> <span className="text-muted-foreground uppercase">{asString(y.tier ?? y.label)}</span>
            {asString(y.note) ? <div className="text-[11px] text-muted-foreground font-normal ml-11">{asString(y.note)}</div> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SpecialCombinationsList({ items }: { items: unknown }) {
  const rows = asArray<Record<string, unknown>>(items);
  if (!rows.length) return <p className="text-sm text-muted-foreground">No items recorded.</p>;
  return (
    <ul className="text-[13.5px] text-muted-foreground list-disc pl-4 space-y-2">
      {rows.map((item, i) => {
        const text =
          asString(item.note) ||
          asString(item.effect) ||
          asString(item.detail) ||
          asString(item.message) ||
          JSON.stringify(item);
        const title = asString(item.yoga_name) || asString(item.name);
        return (
          <li key={i}>
            {title ? <strong className="text-foreground">{title}</strong> : null}
            {title && text !== title ? " — " : null}
            {text !== title ? text : null}
          </li>
        );
      })}
    </ul>
  );
}

export function BusinessRoadmapTab({ data }: Props) {
  const report = data.report;
  const prediction = data.prediction;
  const auth = asRecord(prediction.authoritative_recommendation);
  const ashtakavarga = prediction.supplementary_ashtakavarga ?? auth.ashtakavarga_year_check;
  const transition = asRecord(prediction.transition_timing_recommendation);
  const financial = asRecord(auth.financial_readiness ?? prediction.financial_readiness);
  const operatingModel = asRecord(prediction.operating_model);
  const rec = asRecord(prediction.recommendation);
  const finalCategory =
    asString(auth.final_category) || asString(report.verdict.final_category) || asString(rec.venture_type);
  const sectors = getSectors(data);
  const topRisk = report.top_risk;

  return (
    <div className="space-y-6 text-left">




      {/* ── Transition Timing: Should You Move Now, Or Wait? ── */}
      {Object.keys(transition).length > 0 && (
        <div id="transition">
          <Panel>
            <h3 className="font-serif text-[1.1rem] font-bold text-foreground mb-4">Should You Move Now, Or Wait?</h3>
            <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
              <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
                Our Read
              </div>
              <div className="text-[17px] font-bold text-gold uppercase mb-3">
                {asString(transition.verdict).replace(/_/g, " ")}
              </div>
              <div className="text-[14px] text-foreground leading-relaxed">
                {asString(transition.client_message)}
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* ── Scores at a Glance ── */}
      {report.kpis && report.kpis.length > 0 && (
        <div id="scores">
          <Panel>
            <h3 className="font-serif text-[1.1rem] font-bold text-foreground mb-1.5">Your Scores at a Glance</h3>
            <p className="text-[12.5px] text-muted-foreground mb-4">
              Eight separate readings — business promise, job promise, execution, profitability, and timing readiness.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {report.kpis.map((kpi, idx) => (
                <KpiScoreCard key={idx} kpi={kpi} />
              ))}
            </div>
          </Panel>
        </div>
      )}

      {/* ── Financial Readiness ── */}
      <Panel>
        <SectionTitle title="Financial Readiness Evidence" icon={<Banknote className="h-5 w-5 text-success" />} />
        <div className="grid sm:grid-cols-2 gap-4 mt-3">
          <div className="rounded-xl border border-border bg-surface-soft/40 p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Certification Status</div>
              <Tag tone={auth.capital_readiness_certified || financial.certified ? "success" : "warn"}>
                {auth.capital_readiness_certified || financial.certified ? "CERTIFIED" : "NOT CERTIFIED"}
              </Tag>
            </div>
            <p className="text-[13px] text-foreground font-medium">{asString(auth.capital_readiness_status ?? financial.status)}</p>
          </div>
          <div className="rounded-xl border border-border bg-surface-soft/40 p-4">
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Astrological Capital Status</div>
            <p className="text-[13px] text-foreground font-medium">{asString(financial.astrological_capital_status ?? financial.capital_status)}</p>
          </div>
        </div>
        
        {asArray(financial.missing_fields).length > 0 || (report.financial_readiness.missing_fields && report.financial_readiness.missing_fields.length > 0) ? (
          <div className="mt-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">Missing Evidence Fields</div>
            <p className="text-[12px] text-muted-foreground">
              {asArray(financial.missing_fields).length
                ? asArray<string>(financial.missing_fields).join(", ")
                : report.financial_readiness.missing_fields?.join(", ") || "None recorded"}
            </p>
          </div>
        ) : null}
        
        {asString(financial.note) && <p className="text-[12px] text-muted-foreground mt-3 italic">{asString(financial.note)}</p>}
      </Panel>

      {/* ── Sectors ── */}
      <Panel>
        <SectionTitle title="Sectors That Fit You Best" icon={<Map className="h-5 w-5 text-info" />} />
        <p className="text-xs text-muted-foreground -mt-2 mb-4">
          Ranked by matching classical planetary significators — a fit score, not a viability guarantee.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {sectors.slice(0, 12).map((s) => (
            <div key={`${s.rank}-${s.label}`} className="rounded-xl border border-border bg-surface-soft/40 p-3.5 flex flex-col gap-2 relative overflow-hidden">
              <div className="absolute top-0 left-0 bottom-0 w-1 bg-gradient-to-b from-muted to-transparent" />
              <div className="flex items-center justify-between pl-2">
                <div className="flex items-center gap-2">
                  <div className="text-[10px] font-bold text-muted-foreground bg-border px-1.5 py-0.5 rounded">#{s.rank}</div>
                  <div className="font-semibold text-sm text-foreground">{s.label}</div>
                </div>
                <div className="text-sm font-bold">{fmtPct(s.score)}</div>
              </div>
              <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden mt-1 pl-2">
                <div 
                  className="h-full bg-info/70 rounded-full" 
                  style={{ width: `${sectors[0]?.score ? ((s.score ?? 0) / sectors[0].score!) * 100 : 0}%` }} 
                />
              </div>
              <div className="flex flex-wrap gap-1.5 mt-1 pl-2">
                {s.match_confidence && (
                  <Tag tone={s.match_confidence.includes("HIGH") ? "success" : "muted"}>
                    {s.match_confidence.replace(/_/g, " ")}
                  </Tag>
                )}
                {s.capital_intensity && (
                  <Tag tone="muted">
                    {s.capital_intensity} capital
                  </Tag>
                )}
              </div>
            </div>
          ))}
        </div>
        {sectors.length > 12 && (
          <p className="text-[11px] text-muted-foreground mt-4 text-center">
            Showing top 12 of {sectors.length} ranked sectors. See Astro Insights tab for the full technical list.
          </p>
        )}
      </Panel>

      {/* ── Timed Windows ── */}
      <Panel>
        <SectionTitle title="Favorable Periods Ahead" icon={<CalendarClock className="h-5 w-5 text-success" />} />
        <p className="text-xs text-muted-foreground -mt-2 mb-4">
          Dasha/bhukti windows ranked by business-supportiveness.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {report.timed_windows.map((w, i) => {
            const bc = badgeClass(w.label);
            const tone: Tone = (bc === "STRONG_FAVORABLE" || bc === "FAVORABLE") ? "success" : bc === "CAUTION" ? "warn" : "muted";
            return (
              <div key={i} className="rounded-xl border border-border bg-surface-soft/40 p-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="font-medium text-[13px]">
                    {w.start_date} → {w.end_date}
                  </div>
                  <Tag tone={tone}>{(w.label ?? "—").replace(/_/g, " ")}</Tag>
                </div>
                <div className="text-[11.5px] text-muted-foreground font-semibold uppercase tracking-wider mb-2">
                  {w.md_lord} / {w.ad_lord}
                  {w.net_score != null ? ` · ${fmtPct(w.net_score)}` : ""}
                </div>
                {w.evidence?.length ? (
                  <Accordion type="single" collapsible>
                    <AccordionItem value="astro" className="border-none mt-1">
                      <AccordionTrigger className="text-[10px] uppercase text-royal hover:no-underline py-1">
                        <span className="flex items-center gap-1.5"><span className="text-sm">🔭</span> Astro Logic</span>
                      </AccordionTrigger>
                      <AccordionContent className="pt-1">
                        <ul className="text-[11.5px] text-muted-foreground list-disc pl-4 space-y-1">
                          {w.evidence.map((e, j) => (
                            <li key={j}>{e}</li>
                          ))}
                        </ul>
                      </AccordionContent>
                    </AccordionItem>
                  </Accordion>
                ) : null}
              </div>
            );
          })}
        </div>
      </Panel>

      {/* ── Strongest Years & Yogas ── */}
      <Panel>
        <div className="space-y-8">
          <div className="bg-card border border-border p-5 rounded-xl shadow-sm">
            <h3 className="font-serif text-[1.2rem] font-bold text-foreground mb-4">Your Strongest Years for Business</h3>
            <AshtakavargaPanel ashtakavarga={ashtakavarga} />
          </div>
          <div className="bg-card border border-border p-5 rounded-xl shadow-sm">
            <h3 className="font-serif text-[1.2rem] font-bold text-foreground mb-4">Special Combinations in Your Chart</h3>
            <SpecialCombinationsList items={prediction.detected_yogas} />
            <p className="text-[11.5px] text-muted-foreground mt-4 italic border-t border-border pt-3">
              Status: {asString(prediction.yoga_detection_status)}
            </p>
          </div>
          <div className="bg-card border border-border p-5 rounded-xl shadow-sm space-y-2">
            <h3 className="font-serif text-[1.2rem] font-bold text-foreground mb-4">Dispute & Contract Caution Points</h3>
            <p className="text-[12px] text-foreground">{asString(prediction.legal_dispute_risk_status)}</p>
            <SpecialCombinationsList items={prediction.legal_dispute_risk} />
          </div>
          <div className="bg-card border border-border p-5 rounded-xl shadow-sm">
            <h3 className="font-serif text-[1.2rem] font-bold text-foreground mb-4">Wealth Flow Indicators (D2 Hora)</h3>
            {asArray(prediction.d2_hora_evidence).length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {asArray<Record<string, unknown>>(prediction.d2_hora_evidence).map((item, i) => {
                  const text = asString(item.note) || asString(item.effect) || asString(item.detail) || asString(item.message) || JSON.stringify(item);
                  return (
                    <div key={i} className="bg-muted border border-border/50 p-3 rounded-lg text-[12px] text-muted-foreground flex-1 min-w-[200px]">
                      {text}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No indicators recorded.</p>
            )}
          </div>
        </div>
      </Panel>
    </div>
  );
}
