import { Panel, SectionTitle, Tag } from "@/components/report/primitives";
import type { BusinessPredictionResponse, BusinessKpi } from "@/lib/pyjhora/types";
import {
  asRecord,
  asString,
  asArray,
  fmtPct,
  getSectors,
  GLOSSARY,
  KpiScoreCard,
} from "./business-report-utils";
import { Activity, Compass, Target, Database, BarChart3, Clock, Scale, Lightbulb, Map } from "lucide-react";

interface Props {
  data: BusinessPredictionResponse;
}


function EvidenceList({ items }: { items: unknown }) {
  const rows = asArray<Record<string, unknown>>(items);
  if (!rows.length) return <p className="text-sm text-muted-foreground">No items recorded.</p>;
  return (
    <ul className="text-[13px] text-muted-foreground list-disc pl-4 space-y-2">
      {rows.map((item, i) => {
        const text =
          asString(item.note) ||
          asString(item.effect) ||
          asString(item.detail) ||
          asString(item.message) ||
          JSON.stringify(item);
        const title = asString(item.yoga_name) || asString(item.name);
        return (
          <li key={i} className="break-words">
            {title ? <strong className="text-foreground">{title}</strong> : null}
            {title && text !== title ? " — " : null}
            {text !== title ? text : null}
          </li>
        );
      })}
    </ul>
  );
}

function MuhurtaPanel({ muhurta }: { muhurta: unknown }) {
  const m = asRecord(muhurta);
  const results = asArray<Record<string, unknown>>(m.results);
  if (!Object.keys(m).length) {
    return <p className="text-[13px] text-muted-foreground italic">Not evaluated — no scan attached.</p>;
  }
  if (m.status !== "OK" || !results.length) {
    return (
      <>
        <p className="text-[13px] text-muted-foreground italic mb-2">
          Not evaluated as part of the scored prediction — supplementary scan shown for convenience only.
        </p>
        <p className="text-[13px] text-foreground font-medium">
          {asString(m.status)}
          {m.note ? `: ${asString(m.note)}` : ""}
        </p>
      </>
    );
  }
  return (
    <>
      <p className="text-[13px] text-muted-foreground mb-3">{asString(m.note)}</p>
      <div className="space-y-3">
        {results.slice(0, 10).map((r, i) => (
          <div key={i} className="border-l-2 border-border pl-3">
            <div className="text-[13px] text-foreground font-semibold">
              {asString(r.date)} <span className="text-muted-foreground font-normal mx-1">—</span> <span className="text-gold italic">{asString(r.tier)}</span>
              <span className="text-muted-foreground font-normal ml-1">({fmtPct(r.score_0_100 as number)})</span>
            </div>
            {asArray<string>(r.citations).length > 0 && (
              <div className="text-[11.5px] text-muted-foreground mt-1">
                {asArray<string>(r.citations).join("; ")}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
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
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
      {years.map((y, i) => (
        <div key={i} className="border border-border bg-card rounded-lg p-3">
          <div className="text-[14px] font-bold text-foreground mb-1">{asString(y.year)}</div>
          <div className="text-[12px] text-gold italic mb-1">{asString(y.tier ?? y.label)}</div>
          {y.note ? (
            <div className="text-[11px] text-muted-foreground leading-tight">{asString(y.note)}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function SignificatorTable({ prediction }: { prediction: Record<string, unknown> }) {
  const sig = asRecord(prediction.significators);
  const evidence = asArray<Record<string, unknown>>(sig.evidence);
  if (!evidence.length) return <p className="text-sm text-muted-foreground">No significator evidence recorded.</p>;

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-left text-[13px]">
          <thead className="bg-muted/50 border-b border-border">
            <tr>
              <th className="px-4 py-2 font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">Polarity</th>
              <th className="px-4 py-2 font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">Weight</th>
              <th className="px-4 py-2 font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">Family</th>
              <th className="px-4 py-2 font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">Note</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {evidence.map((e, i) => (
              <tr key={i} className="hover:bg-muted/20">
                <td className="px-4 py-2.5">
                  <Tag tone={asString(e.polarity) === "positive" ? "success" : "warn"}>{asString(e.polarity)}</Tag>
                </td>
                <td className="px-4 py-2.5 text-foreground">{asString(e.weight)}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{asString(e.family)}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{asString(e.note)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-4 text-[12px] text-muted-foreground bg-muted/30 p-3 rounded-lg border border-border">
        <div><strong>Net score:</strong> {asString(sig.net_score)}</div>
        <div><strong>Positive total:</strong> {asString(sig.positive_total)}</div>
        <div><strong>Negative total:</strong> {asString(sig.negative_total)}</div>
      </div>
    </div>
  );
}

export function BusinessInsightsTab({ data }: Props) {
  const report = data.report;
  const prediction = data.prediction;
  const auth = asRecord(prediction.authoritative_recommendation);
  const muhurta = prediction.supplementary_muhurta ?? auth.muhurta_check;
  const ashtakavarga = prediction.supplementary_ashtakavarga ?? auth.ashtakavarga_year_check;
  const sectors = getSectors(data);
  const modeGate = asRecord(prediction.mode_gate);
  const operatingModel = asRecord(prediction.operating_model);
  const finalCategory = asString(auth.final_category) || asString(report.verdict.final_category);

  const d2 = asArray(prediction.d2_hora_evidence);
  const d2deep = asRecord(prediction.d2_hora_deep_evidence);
  const mercury = asRecord(prediction.mercury_adjudication);
  const nakshatraChain = asRecord(prediction.janma_nakshatra_full_chain);
  const lagnesh = asRecord(prediction.lagnesh_neecha_bhanga);
  const d10rect = asRecord(prediction.d10_rectification_sensitivity);
  const foreign = asArray(prediction.foreign_business_evidence);

  return (
    <div className="space-y-8 text-left">
      {/* ── Signal Reconciliation ── */}
      <div className="space-y-6">
        <h3 className="font-serif text-[1.2rem] font-bold text-foreground">
          <span className="bg-[#D8C7A0]/40 px-1.5 py-0.5 rounded mr-1.5 text-black">Signal Reconciliation:</span> 
          Employment vs. Independent Profession vs. Business
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="rounded-xl border border-border bg-card p-4 text-[12px]">
            <strong className="text-foreground">Authoritative verdict:</strong> {asString(finalCategory).replace(/_/g, " ")} (business {fmtPct(prediction.business_promise as number)}, job {fmtPct(prediction.job_promise as number)})
          </div>
          <div className="rounded-xl border border-border bg-card p-4 text-[12px]">
            <strong className="text-foreground">Legacy mode_gate signal:</strong> {asString(modeGate.recommended_mode)} (confidence={asString(modeGate.confidence)}, business_score={asString(modeGate.business_score)})
          </div>
          <div className="rounded-xl border border-border bg-card p-4 text-[12px]">
            <strong className="text-foreground">Independent-profession promise:</strong> {fmtPct(prediction.independent_profession_promise as number)}
          </div>
          <div className="rounded-xl border border-border bg-card p-4 text-[12px]">
            <strong className="text-foreground">Best-fit operating model (D1):</strong> {asString(operatingModel.best_fit)}
          </div>
        </div>
        
        <div className="rounded-xl border border-border bg-card p-4 text-[13px]">
          <strong className="text-foreground">Business advantage:</strong> {asString(prediction.business_advantage_label)} ( margin {fmtPct(prediction.business_advantage_margin as number)})
        </div>

        {asArray(prediction.contradiction_findings).length > 0 && (
          <div className="pt-2">
            <h3 className="font-serif text-[1.1rem] font-bold text-foreground mb-4">Contradiction findings</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {asArray<Record<string, unknown>>(prediction.contradiction_findings).map((item, i) => {
                const text = asString(item.note) || asString(item.effect) || asString(item.detail) || asString(item.message) || JSON.stringify(item);
                return (
                  <div key={i} className="rounded-xl border border-border bg-card p-4 text-[12.5px] text-muted-foreground leading-relaxed">
                    {text}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ── Structural Promise Fields ── */}
      <Panel>
        <SectionTitle title="Structural Promise Fields" icon={<BarChart3 className="h-5 w-5 text-gold" />} />
        <p className="text-[13px] text-muted-foreground mb-4 -mt-2">
          Eight separate readings — business promise, job promise, execution, profitability, and timing readiness.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {report.kpis.map((k) => (
            <KpiScoreCard key={k.key} kpi={k} />
          ))}
        </div>
      </Panel>

      {/* ── Additional Operational & Forecast Meta ── */}
      <div className="space-y-6">
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="font-serif text-[1.2rem] font-bold text-foreground mb-3">Capital Strategy: Bootstrap vs External Capital</h3>
          <p className="text-[13px] text-muted-foreground leading-relaxed">
            Best-fit operating model (D1): <strong className="text-foreground">{asString(operatingModel.best_fit)}</strong> — {asString(operatingModel.note) || "Operating-model fit is a RELATIVE, within-chart ranking (each model normalized against this chart's own top scorer), not an absolute cross-chart scale -- do not compare these numbers across different charts."}
          </p>
        </div>

        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="font-serif text-[1.2rem] font-bold text-foreground mb-3">Forecast Window & Timing Status</h3>
          <div className="text-[13px] text-muted-foreground space-y-2">
            <p>As of: {asString(asRecord(prediction.forecast_metadata).as_of) || "2026-09-30"} · Years ahead: {asString(asRecord(prediction.forecast_metadata).years_ahead) || "15"}</p>
            <p>Timing status: {asString(asRecord(prediction.forecast_metadata).status) || "OK"} · Calendar periods: {asString(asRecord(prediction.forecast_metadata).periods) || "72"}</p>
          </div>
        </div>
      </div>

      {/* ── Full Sectors List ── */}
      <Panel>
        <SectionTitle title="All Business Sectors (Full List)" icon={<Map className="h-5 w-5 text-info" />} />
        <p className="text-[13px] text-muted-foreground mb-4 -mt-2">
          Ranked by matching classical planetary significators — a fit score, not a viability guarantee.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {sectors.map((s) => (
            <div key={`${s.rank}-${s.label}`} className="rounded-xl border border-border bg-surface-soft/40 p-3.5 flex flex-col gap-2 relative overflow-hidden">
              <div className="flex items-center justify-between pl-2">
                <div className="flex items-center gap-2">
                  <div className="text-[10px] font-bold text-muted-foreground bg-border px-1.5 py-0.5 rounded">#{s.rank}</div>
                  <div className="font-semibold text-sm text-foreground">{s.label}</div>
                </div>
                <div className="text-sm font-bold">{fmtPct(s.score)}</div>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="flex flex-col gap-8">
        <div className="space-y-8">
          {/* ── Significators ── */}
          <Panel>
            <SectionTitle title="Business-Strength Significators" icon={<Activity className="h-5 w-5 text-info" />} />
            <SignificatorTable prediction={prediction} />
            
            <div className="grid grid-cols-1 gap-6 mt-6 pt-6 border-t border-border">
              <div>
                <h3 className="text-[13px] font-bold text-foreground mb-3">Top Positive Evidences</h3>
                <EvidenceList items={report.significators.positive} />
              </div>
              <div>
                <h3 className="text-[13px] font-bold text-foreground mb-3">Top Risk Evidences</h3>
                <EvidenceList items={report.significators.negative} />
              </div>
            </div>
          </Panel>


        </div>

        <div className="space-y-8">
          {/* ── Technical Appendix ── */}
          <Panel>
            <SectionTitle title="Technical Appendix" icon={<Database className="h-5 w-5 text-gold" />} />
            
            <div className="space-y-6">
              {/* Muhurta */}
              <div>
                <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Clock className="w-3.5 h-3.5" /> Auspicious Date/Time (Muhurta)</h3>
                <MuhurtaPanel muhurta={muhurta} />
              </div>

              {/* Ashtakavarga */}
              <div className="pt-4 border-t border-border">
                <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><BarChart3 className="w-3.5 h-3.5" /> Strongest Years for Business (Ashtakavarga)</h3>
                <AshtakavargaPanel ashtakavarga={ashtakavarga} />
              </div>

              {/* Yogas */}
              <div className="pt-4 border-t border-border">
                <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Lightbulb className="w-3.5 h-3.5" /> Special Combinations (Yogas)</h3>
                <EvidenceList items={prediction.detected_yogas} />
                <p className="text-[11px] text-muted-foreground mt-2 italic">Status: {asString(prediction.yoga_detection_status)}</p>
              </div>

              {/* Legal */}
              <div className="pt-4 border-t border-border">
                <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Scale className="w-3.5 h-3.5" /> Dispute & Contract Risks</h3>
                <p className="text-[12px] text-foreground mb-2">{asString(prediction.legal_dispute_risk_status)}</p>
                <EvidenceList items={prediction.legal_dispute_risk} />
              </div>

              {/* D2 Hora */}
              {d2.length > 0 && (
                <div className="pt-4 border-t border-border">
                  <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Compass className="w-3.5 h-3.5" /> Wealth Flow Indicators (D2 Hora)</h3>
                  <EvidenceList items={d2} />
                </div>
              )}
              {/* D2 Deep */}
              {Object.keys(d2deep).length > 0 && (
                <div className="pt-4 border-t border-border">
                  <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Compass className="w-3.5 h-3.5" /> Earning, Saving & Spending Signals</h3>
                  <EvidenceList
                    items={Object.entries(d2deep)
                      .filter(([k]) => !["status"].includes(k))
                      .map(([k, v]) => ({ note: `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}` }))}
                  />
                </div>
              )}

              {/* Mercury Adjudication */}
              {Object.keys(mercury).length > 0 && (
                <div className="pt-4 border-t border-border">
                  <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Activity className="w-3.5 h-3.5" /> Mercury: Commerce and Career</h3>
                  <EvidenceList
                    items={Object.entries(mercury).map(([k, v]) => ({
                      note: `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v) : v}`,
                    }))}
                  />
                </div>
              )}

              {/* Nakshatra Chain */}
              {Object.keys(nakshatraChain).length > 0 && (
                <div className="pt-4 border-t border-border">
                  <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Target className="w-3.5 h-3.5" /> Vocational Direction (Star-Lord Chain)</h3>
                  <EvidenceList
                    items={Object.entries(nakshatraChain).map(([k, v]) => ({
                      note: `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v) : v}`,
                    }))}
                  />
                </div>
              )}

              {/* Lagnesh Neecha Bhanga */}
              {Object.keys(lagnesh).length > 0 && (
                <div className="pt-4 border-t border-border">
                  <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Activity className="w-3.5 h-3.5" /> Lagnesh Neecha Bhanga</h3>
                  <EvidenceList
                    items={Object.entries(lagnesh).map(([k, v]) => ({
                      note: `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`,
                    }))}
                  />
                </div>
              )}

              {/* D10 Rectification */}
              {Object.keys(d10rect).length > 0 && (
                <div className="pt-4 border-t border-border">
                  <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Activity className="w-3.5 h-3.5" /> Reliability Check (Birth-Time Sensitivity)</h3>
                  <p className="text-[12px] text-muted-foreground">{asString(d10rect.note ?? d10rect.status ?? d10rect.stability)}</p>
                </div>
              )}

              {/* Foreign Business */}
              {foreign.length > 0 && (
                <div className="pt-4 border-t border-border">
                  <h3 className="text-[13px] font-bold text-foreground mb-2 flex items-center gap-2"><Map className="w-3.5 h-3.5" /> Foreign / Cross-Border Business</h3>
                  <EvidenceList items={foreign} />
                </div>
              )}


            </div>
          </Panel>
          
          {/* ── Method Status ── */}
          <Panel>
            <SectionTitle title="Method-level Status & Forecast Windows" icon={<Database className="h-5 w-5 text-gold" />} />
            
            <div className="space-y-4">
              <div className="overflow-x-auto rounded-xl border border-border">
                <table className="w-full text-left text-[13px]">
                  <thead className="bg-muted/50 border-b border-border">
                    <tr>
                      <th className="px-4 py-2 font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">Method</th>
                      <th className="px-4 py-2 font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {Object.entries(asRecord(prediction.method_status)).map(([k, v]) => (
                      <tr key={k} className="hover:bg-muted/20">
                        <td className="px-4 py-2.5 text-foreground">{k.replace(/_/g, " ")}</td>
                        <td className="px-4 py-2.5 text-muted-foreground">{typeof v === "object" ? JSON.stringify(v) : asString(v)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="text-[12px] text-muted-foreground bg-muted/30 p-3 rounded-lg border border-border space-y-1">
                <div><strong>Confidence label:</strong> {report.confidence.label ?? "—"} · <strong>Leaning:</strong> {report.confidence.overall_leaning ?? "—"}</div>
                <div><strong>Method agreement:</strong> {report.confidence.method_agreement != null ? `${(report.confidence.method_agreement * 100).toFixed(1)}%` : "—"}</div>
              </div>
            </div>
          </Panel>
          


        </div>
      </div>

      {/* ── Glossary ── */}
      <div id="glossary">
        <Panel>
          <SectionTitle title="How to Read This Report — Astrological Terms Explained" icon={<Database className="h-5 w-5 text-gold" />} />
        <p className="text-[13px] text-muted-foreground mb-4 -mt-2">
          Plain-language definitions for terms used throughout this report — useful on screen or in print.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
          {GLOSSARY.map(([term, def], i) => (
            <div key={i} className="rounded-xl border border-border bg-surface-soft/40 p-4">
              <div className="text-[12px] font-bold text-foreground mb-1.5">{term}</div>
              <div className="text-[11.5px] text-muted-foreground leading-relaxed">{def}</div>
            </div>
          ))}
        </div>
        </Panel>
      </div>
    </div>
  );
}
