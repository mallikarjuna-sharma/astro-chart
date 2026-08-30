import { useMemo, useState } from "react";
import { useDisplayName } from "@/hooks/use-display-name";
import type { BusinessKpi, BusinessPredictionResponse } from "@/lib/pyjhora/types";
import {
  ASTROLOGER_TABS,
  GLOSSARY,
  PROFILE_TABS,
  asArray,
  asRecord,
  asString,
  badgeClass,
  fmtPct,
  getSectors,
  scrollToSection,
  verdictClass,
  verdictLabel,
  type ViewMode,
} from "./business-report-utils";
import "./business-report.css";

interface Props {
  data: BusinessPredictionResponse;
}

function VerdictBlock({
  category,
  businessPromise,
  jobPromise,
  compact,
}: {
  category?: string;
  businessPromise?: number | null;
  jobPromise?: number | null;
  compact?: boolean;
}) {
  const cls = verdictClass(category);
  return (
    <div>
      <div className="biz-verdict-label">Final Verdict</div>
      <div className={`biz-verdict-value ${cls}`} style={compact ? { fontSize: "1rem" } : undefined}>
        {verdictLabel(category)}
      </div>
      {(businessPromise != null || jobPromise != null) && (
        <div className="biz-verdict-meta">
          Business promise: {fmtPct(businessPromise)} · Job promise: {fmtPct(jobPromise)}
        </div>
      )}
    </div>
  );
}

function KpiScoreCard({ kpi }: { kpi: BusinessKpi }) {
  return (
    <div className={`biz-kpi-card ${kpi.tier}`}>
      <div className="biz-kpi-label">{kpi.label}</div>
      <div className="biz-kpi-value">{fmtPct(kpi.value)}</div>
      {kpi.value != null && (
        <div className="biz-kpi-bar-track">
          <div
            className={`biz-kpi-bar-fill ${kpi.tier}`}
            style={{ width: `${Math.max(0, Math.min(100, kpi.value))}%` }}
          />
        </div>
      )}
      <div className="biz-kpi-hint">{kpi.hint}</div>
    </div>
  );
}

function EvidenceList({ items }: { items: unknown }) {
  const rows = asArray<Record<string, unknown>>(items);
  if (!rows.length) return <p>No items recorded.</p>;
  return (
    <ul className="biz-item-grid">
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
            {title ? <strong>{title}</strong> : null}
            {title && text !== title ? " — " : null}
            {text !== title ? text : null}
          </li>
        );
      })}
    </ul>
  );
}

function SignificatorTable({ prediction }: { prediction: Record<string, unknown> }) {
  const sig = asRecord(prediction.significators);
  const evidence = asArray<Record<string, unknown>>(sig.evidence);
  if (!evidence.length) return <p>No significator evidence recorded.</p>;

  return (
    <div className="biz-card" style={{ overflowX: "auto" }}>
      <table className="biz-table">
        <thead>
          <tr>
            <th>Polarity</th>
            <th>Weight</th>
            <th>Family</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {evidence.map((e, i) => (
            <tr key={i}>
              <td>{asString(e.polarity)}</td>
              <td>{asString(e.weight)}</td>
              <td>{asString(e.family)}</td>
              <td>{asString(e.note)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Net score: {asString(sig.net_score)} · Positive total: {asString(sig.positive_total)} ·
        Negative total: {asString(sig.negative_total)}
      </p>
    </div>
  );
}

function MethodStatusPanel({ prediction }: { prediction: Record<string, unknown> }) {
  const ms = asRecord(prediction.method_status);
  const entries = Object.entries(ms);
  if (!entries.length) return <p>No method status recorded.</p>;
  return (
    <div className="biz-card">
      <table className="biz-table">
        <thead>
          <tr>
            <th>Method</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k}>
              <td>{k.replace(/_/g, " ")}</td>
              <td>{typeof v === "object" ? JSON.stringify(v) : asString(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MuhurtaPanel({ muhurta }: { muhurta: unknown }) {
  const m = asRecord(muhurta);
  const results = asArray<Record<string, unknown>>(m.results);
  if (!Object.keys(m).length) {
    return <p className="biz-muted-note">Not evaluated — no scan attached.</p>;
  }
  if (m.status !== "OK" || !results.length) {
    return (
      <>
        <p className="biz-muted-note">
          Not evaluated as part of the scored prediction — supplementary scan shown for convenience
          only.
        </p>
        <p>
          <em>{asString(m.status)}</em>
          {m.note ? `: ${asString(m.note)}` : ""}
        </p>
      </>
    );
  }
  return (
    <>
      <p>{asString(m.note)}</p>
      <ol style={{ margin: "0.5rem 0 0", paddingLeft: "1.25rem", fontSize: "0.8125rem" }}>
        {results.slice(0, 10).map((r, i) => (
          <li key={i} style={{ marginBottom: "0.5rem" }}>
            <strong>{asString(r.date)}</strong> — <em>{asString(r.tier)}</em> (
            {fmtPct(r.score_0_100 as number)})
            {asArray<string>(r.citations).length > 0 && (
              <div style={{ fontSize: "0.75rem", color: "var(--biz-ink-soft)" }}>
                {asArray<string>(r.citations).join("; ")}
              </div>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}

function AshtakavargaPanel({ ashtakavarga }: { ashtakavarga: unknown }) {
  const a = asRecord(ashtakavarga);
  const years = asArray<Record<string, unknown>>(a.ranked_years ?? a.years);
  if (!Object.keys(a).length) {
    return <p className="biz-muted-note">Not evaluated.</p>;
  }
  if (!years.length) {
    return (
      <>
        <p className="biz-muted-note">Supplementary scan — did not affect the main recommendation.</p>
        <p>
          <em>{asString(a.status)}</em>
          {a.note ? `: ${asString(a.note)}` : ""}
        </p>
      </>
    );
  }
  return (
    <ol style={{ margin: 0, paddingLeft: "1.25rem", fontSize: "0.8125rem" }}>
      {years.map((y, i) => (
        <li key={i} style={{ marginBottom: "0.5rem" }}>
          <strong>{asString(y.year)}</strong> — <em>{asString(y.tier ?? y.label)}</em>
          {y.note ? (
            <>
              <br />
              <span style={{ fontSize: "0.75rem" }}>{asString(y.note)}</span>
            </>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function AppendixSections({ prediction, auth }: { prediction: Record<string, unknown>; auth: Record<string, unknown> }) {
  const muhurta = prediction.supplementary_muhurta ?? auth.muhurta_check;
  const ashtakavarga = prediction.supplementary_ashtakavarga ?? auth.ashtakavarga_year_check;
  const d2 = asArray(prediction.d2_hora_evidence);
  const d2deep = asRecord(prediction.d2_hora_deep_evidence);
  const mercury = asRecord(prediction.mercury_adjudication);
  const nakshatraChain = asRecord(prediction.janma_nakshatra_full_chain);
  const d10rect = asRecord(prediction.d10_rectification_sensitivity);
  const foreign = asArray(prediction.foreign_business_evidence);
  const lagnesh = asRecord(prediction.lagnesh_neecha_bhanga);

  return (
    <>
      <section className="biz-section" id="appendix-muhurta">
        <h2>Auspicious Date/Time Recommendations</h2>
        <div className="biz-card">
          <MuhurtaPanel muhurta={muhurta} />
        </div>
      </section>

      <section className="biz-section" id="appendix-ashtakavarga">
        <h2>Your Strongest Years for Business</h2>
        <div className="biz-card">
          <AshtakavargaPanel ashtakavarga={ashtakavarga} />
        </div>
      </section>

      <section className="biz-section" id="appendix-yogas">
        <h2>Special Combinations in Your Chart</h2>
        <div className="biz-card">
          <EvidenceList items={prediction.detected_yogas} />
          <p className="biz-muted-note">Status: {asString(prediction.yoga_detection_status)}</p>
        </div>
      </section>

      <section className="biz-section" id="appendix-legal">
        <h2>Dispute &amp; Contract Caution Points</h2>
        <div className="biz-card">
          <p>{asString(prediction.legal_dispute_risk_status)}</p>
          <EvidenceList items={prediction.legal_dispute_risk} />
        </div>
      </section>

      <section className="biz-section" id="appendix-d2">
        <h2>Wealth Flow Indicators (D2 Hora)</h2>
        <div className="biz-card">
          <EvidenceList items={d2} />
        </div>
      </section>

      {Object.keys(d2deep).length > 0 && (
        <section className="biz-section" id="appendix-d2-deep">
          <h2>Earning, Saving &amp; Spending Signals</h2>
          <div className="biz-card">
            <EvidenceList
              items={Object.entries(d2deep)
                .filter(([k]) => !["status"].includes(k))
                .map(([k, v]) => ({ note: `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}` }))}
            />
          </div>
        </section>
      )}

      {Object.keys(mercury).length > 0 && (
        <section className="biz-section" id="appendix-mercury">
          <h2>Mercury: Commerce and Career</h2>
          <div className="biz-card">
            <EvidenceList
              items={Object.entries(mercury).map(([k, v]) => ({
                note: `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v) : v}`,
              }))}
            />
          </div>
        </section>
      )}

      {Object.keys(nakshatraChain).length > 0 && (
        <section className="biz-section" id="appendix-nakshatra">
          <h2>Vocational Direction (Star-Lord Chain)</h2>
          <div className="biz-card">
            <EvidenceList
              items={Object.entries(nakshatraChain).map(([k, v]) => ({
                note: `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v) : v}`,
              }))}
            />
          </div>
        </section>
      )}

      {Object.keys(lagnesh).length > 0 && (
        <section className="biz-section" id="appendix-lagnesh">
          <h2>Lagnesh Neecha Bhanga</h2>
          <div className="biz-card">
            <EvidenceList
              items={Object.entries(lagnesh).map(([k, v]) => ({
                note: `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`,
              }))}
            />
          </div>
        </section>
      )}

      {Object.keys(d10rect).length > 0 && (
        <section className="biz-section" id="appendix-d10">
          <h3>Reliability Check (Birth-Time Sensitivity)</h3>
          <div className="biz-card">
            <p>{asString(d10rect.note ?? d10rect.status ?? d10rect.stability)}</p>
          </div>
        </section>
      )}

      {foreign.length > 0 && (
        <section className="biz-section" id="appendix-foreign">
          <h2>Foreign / Cross-Border Business</h2>
          <div className="biz-card">
            <EvidenceList items={foreign} />
          </div>
        </section>
      )}

      {asArray(prediction.contradiction_findings).length > 0 && (
        <section className="biz-section" id="appendix-contradictions">
          <h2>Contradiction Findings</h2>
          <div className="biz-card">
            <EvidenceList items={prediction.contradiction_findings} />
          </div>
        </section>
      )}
    </>
  );
}

export function BusinessReport({ data }: Props) {
  const report = data.report;
  const prediction = data.prediction;
  const auth = asRecord(prediction.authoritative_recommendation);
  const student = data.student;
  const displayName = useDisplayName(student.name ?? report.name);
  const [view, setView] = useState<ViewMode>("profile");

  const generated = useMemo(() => {
    if (data.generated_at) {
      return new Date(data.generated_at).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    }
    return report.generated;
  }, [data.generated_at, report.generated]);

  const sectors = useMemo(() => getSectors(data), [data]);
  const tabs = view === "profile" ? PROFILE_TABS : ASTROLOGER_TABS;
  const prefix = view === "profile" ? "p" : "a";

  const transition = asRecord(prediction.transition_timing_recommendation);
  const financial = asRecord(auth.financial_readiness ?? prediction.financial_readiness);
  const operatingModel = asRecord(prediction.operating_model);
  const modeGate = asRecord(prediction.mode_gate);
  const timingStatus = asRecord(prediction.timing_status);
  const forecastWindow = asRecord(prediction.forecast_window);
  const maturityCaveats = asArray<string>(prediction.maturity_caveats);

  const rec = asRecord(prediction.recommendation);
  const finalCategory =
    asString(auth.final_category) || asString(report.verdict.final_category) || asString(rec.venture_type);

  return (
    <div className="biz-report">
      <header className="biz-hero">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="biz-hero-kicker">JyotishAI · Business Astrology Report</div>
            <h1>{displayName}</h1>
            <div className="biz-hero-meta">
              {generated}
              {data.rule_pack_version ? ` · Rule pack ${data.rule_pack_version}` : ""}
            </div>
            <div className="biz-hero-subject">
              {student.dob ? `Born ${student.dob}` : null}
              {student.birth_place ? ` · ${student.birth_place}` : null}
              {typeof student.current_age === "number"
                ? ` · age ${Math.round(student.current_age)}`
                : null}
            </div>
          </div>
          <div className="text-right">
            <VerdictBlock
              category={finalCategory}
              businessPromise={report.verdict.business_promise ?? (prediction.business_promise as number)}
              jobPromise={report.verdict.job_promise ?? (prediction.job_promise as number)}
            />
          </div>
        </div>
      </header>

      <nav className="biz-viewswitch">
        <div className="biz-viewswitch-inner">
          <span className="biz-vs-label">Viewing as</span>
          <button
            type="button"
            className={`biz-vs-btn ${view === "profile" ? "active" : ""}`}
            onClick={() => setView("profile")}
          >
            Chart Profile
          </button>
          <button
            type="button"
            className={`biz-vs-btn ${view === "astrologer" ? "active" : ""}`}
            onClick={() => setView("astrologer")}
          >
            Astrologer View
          </button>
        </div>
      </nav>

      <nav className="biz-tabs">
        <div className="biz-tabs-inner">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => scrollToSection(`${prefix}-${tab.id}`)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      <div className="biz-wrap">
        <section className="biz-glossary" id="glossary">
          <h2>How to Read This Report — Astrological Terms Explained</h2>
          <p>
            Plain-language definitions for terms used throughout this report — useful on screen or in
            print.
          </p>
          <dl className="biz-glossary-grid">
            {GLOSSARY.map(([term, def]) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{def}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* ── At a Glance ── */}
        <section className="biz-section" id={`${prefix}-at-a-glance`}>
          <h2>At a Glance</h2>
          <p>The four headline facts from this report, gathered in one place.</p>
          <div className="biz-kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
            <div className="biz-kpi-card">
              <div className="biz-kpi-label">Verdict</div>
              <VerdictBlock
                category={finalCategory}
                businessPromise={report.verdict.business_promise}
                jobPromise={report.verdict.job_promise}
                compact
              />
            </div>
            <div className="biz-kpi-card">
              <div className="biz-kpi-label">Top-Fit Sector</div>
              <div className="biz-kpi-value" style={{ fontSize: "1rem" }}>
                {report.top_sector?.label ?? "—"}
                {report.top_sector?.score != null && (
                  <span style={{ fontSize: "0.75rem", color: "var(--biz-ink-soft)" }}>
                    {" "}
                    ({fmtPct(report.top_sector.score)})
                  </span>
                )}
              </div>
            </div>
            <div className="biz-kpi-card">
              <div className="biz-kpi-label">Nearest Favorable Window</div>
              <div className="biz-kpi-value" style={{ fontSize: "0.9375rem" }}>
                {report.top_window
                  ? `${report.top_window.start_date} → ${report.top_window.end_date}`
                  : "—"}
                {report.top_window?.md_lord && (
                  <span style={{ fontSize: "0.75rem", color: "var(--biz-ink-soft)", display: "block" }}>
                    {report.top_window.md_lord}/{report.top_window.ad_lord}
                  </span>
                )}
              </div>
            </div>
            <div className="biz-kpi-card">
              <div className="biz-kpi-label">Biggest Risk Flag</div>
              <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--biz-ink)" }}>
                {report.top_risk
                  ? report.top_risk.length > 160
                    ? `${report.top_risk.slice(0, 160)}…`
                    : report.top_risk
                  : "None flagged"}
              </div>
            </div>
          </div>
        </section>

        <div className="biz-disclaimer">
          <p>
            <strong>Model status: {data.model_status || prediction.model_status as string}</strong> —{" "}
            {data.calibration_status || prediction.calibration_status as string}
          </p>
          {asString(prediction.maturity_statement) && (
            <p>
              <strong>Maturity statement:</strong> {asString(prediction.maturity_statement)}
            </p>
          )}
          {maturityCaveats.length > 0 && (
            <ul>
              {maturityCaveats.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          )}
          <p>
            Heuristic tiers are internal rule thresholds, not statistical confidence or financial
            advice. Decision-support narrative for further astrological review only.
          </p>
        </div>

        {/* ── Recommendation / Summary ── */}
        <section className="biz-section" id={`${prefix}-recommendation`}>
          <h2>{view === "profile" ? "In Summary" : "Recommendation"}</h2>
          <div className="biz-card">
            {view === "profile" ? (
              <>
                <p style={{ fontSize: "0.9375rem", color: "var(--biz-ink)", marginTop: 0 }}>
                  {asString(transition.client_message) ||
                    asString(rec.reasoning) ||
                    (finalCategory.includes("JOB")
                      ? "Your chart leans toward employment over an immediate full business transition — validate carefully before committing capital."
                      : "Your chart shows meaningful support for an independent business path — validate sector fit and timing before committing capital.")}
                </p>
                {asString(auth.final_category_note) && (
                  <p style={{ marginTop: "0.75rem" }}>{asString(auth.final_category_note)}</p>
                )}
              </>
            ) : (
              <>
                <p style={{ color: "var(--biz-ink)" }}>
                  Verdict: <strong>{verdictLabel(finalCategory)}</strong>
                  {auth.action_level ? ` (action level: ${asString(auth.action_level)})` : ""} —
                  business promise ({fmtPct(report.verdict.business_promise)}) vs job promise (
                  {fmtPct(report.verdict.job_promise)}).
                </p>
                <p>
                  Comparative advantage: <strong>{rec.comparative_advantage ? "Yes" : "No"}</strong> ·
                  Hybrid suggested: <strong>{rec.hybrid_suggested ? "Yes" : "No"}</strong> · Proceed:{" "}
                  <strong>{rec.proceed ? "Yes" : "No"}</strong>
                </p>
                {asString(rec.reasoning) && <p>{asString(rec.reasoning)}</p>}
                {asString(auth.note) && <p className="biz-muted-note">{asString(auth.note)}</p>}
              </>
            )}
          </div>
        </section>

        {/* ── Financial Readiness (profile) ── */}
        {view === "profile" && (
          <section className="biz-section" id={`${prefix}-financial`}>
            <h2>Financial Readiness Evidence</h2>
            <div className="biz-card">
              <p>
                <strong>Certification status:</strong>{" "}
                {auth.capital_readiness_certified || financial.certified ? "CERTIFIED" : "NOT CERTIFIED"}{" "}
                · {asString(auth.capital_readiness_status ?? financial.status)}
              </p>
              <p>
                <strong>Astrological capital status:</strong>{" "}
                {asString(financial.astrological_capital_status ?? financial.capital_status)}
              </p>
              <p>
                <strong>Missing evidence fields:</strong>{" "}
                {asArray(financial.missing_fields).length
                  ? asArray<string>(financial.missing_fields).join(", ")
                  : report.financial_readiness.missing_fields?.join(", ") || "None recorded"}
              </p>
              {asString(financial.note) && <p style={{ marginBottom: 0 }}>{asString(financial.note)}</p>}
            </div>
          </section>
        )}

        {/* ── Transition Timing (profile) ── */}
        {view === "profile" && Object.keys(transition).length > 0 && (
          <section className="biz-section" id={`${prefix}-transition`}>
            <h2>Should You Move Now, Or Wait?</h2>
            <div className="biz-card">
              <div style={{ marginBottom: "0.75rem" }}>
                <div className="biz-verdict-label">Our Read</div>
                <div className={`biz-verdict-value ${verdictClass(asString(transition.verdict))}`}>
                  {asString(transition.verdict).replace(/_/g, " ")}
                </div>
              </div>
              <p style={{ fontSize: "0.9375rem", color: "var(--biz-ink)", marginTop: 0 }}>
                {asString(transition.client_message)}
              </p>
              {asString(transition.disclaimer) && (
                <p className="biz-muted-note" style={{ marginBottom: 0 }}>
                  {asString(transition.disclaimer)}
                </p>
              )}
            </div>
          </section>
        )}

        {/* ── Promise / Scores ── */}
        <section className="biz-section" id={`${prefix}-scores`}>
          <h2>{view === "profile" ? "Your Scores at a Glance" : "Structural Promise Fields"}</h2>
          <p>Eight separate readings — business promise, job promise, execution, profitability, and timing readiness.</p>
          <div className="biz-kpi-grid">
            {report.kpis.map((k) => (
              <KpiScoreCard key={k.key} kpi={k} />
            ))}
          </div>
          {operatingModel.best_fit && (
            <div className="biz-card" style={{ marginTop: "0.875rem" }}>
              <h3 style={{ marginTop: 0 }}>Capital Strategy: Bootstrap vs External Capital</h3>
              <p style={{ fontSize: "0.8125rem" }}>
                Best-fit operating model (D1): <strong>{asString(operatingModel.best_fit)}</strong>
                {operatingModel.note ? ` — ${asString(operatingModel.note)}` : ""}
              </p>
            </div>
          )}
        </section>

        {/* ── Forecast window (astrologer) ── */}
        {view === "astrologer" && (
          <section className="biz-section" id={`${prefix}-forecast`}>
            <h2>Forecast Window &amp; Timing Status</h2>
            <div className="biz-card">
              <p>
                As of: {asString(forecastWindow.as_of)} · Years ahead:{" "}
                {asString(forecastWindow.years_ahead)}
              </p>
              <p>
                Timing status: {asString(timingStatus.status)} · Calendar periods:{" "}
                {asString(timingStatus.calendar_periods_found)}
              </p>
              {asString(timingStatus.error) && <p>{asString(timingStatus.error)}</p>}
            </div>
          </section>
        )}

        {/* ── Significators (astrologer) ── */}
        {view === "astrologer" && (
          <section className="biz-section" id={`${prefix}-significators`}>
            <h2>Business-Strength Significators</h2>
            <SignificatorTable prediction={prediction} />
            <div className="biz-card" style={{ marginTop: "0.5rem" }}>
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <h3 style={{ marginTop: 0 }}>Top Positive</h3>
                  <EvidenceList items={report.significators.positive} />
                </div>
                <div>
                  <h3 style={{ marginTop: 0 }}>Top Risk</h3>
                  <EvidenceList items={report.significators.negative} />
                </div>
              </div>
            </div>
          </section>
        )}

        {/* ── Signal Reconciliation (profile) ── */}
        {view === "profile" && (
          <section className="biz-section" id={`${prefix}-reconciliation`}>
            <h2>Signal Reconciliation: Employment vs. Independent Profession vs. Business</h2>
            <div className="biz-card">
              <ul className="biz-item-grid">
                <li>
                  <strong>Authoritative verdict</strong>: {verdictLabel(finalCategory)} (business{" "}
                  {fmtPct(prediction.business_promise as number)}, job{" "}
                  {fmtPct(prediction.job_promise as number)})
                </li>
                <li>
                  <strong>Legacy mode_gate signal</strong>: {asString(modeGate.recommended_mode)} (confidence=
                  {asString(modeGate.confidence)}, business_score={asString(modeGate.business_score)})
                </li>
                <li>
                  <strong>Independent-profession promise</strong>:{" "}
                  {fmtPct(prediction.independent_profession_promise as number)}
                </li>
                <li>
                  <strong>Best-fit operating model (D1)</strong>: {asString(operatingModel.best_fit)}
                </li>
                <li>
                  <strong>Business advantage</strong>: {asString(prediction.business_advantage_label)} (
                  margin {fmtPct(prediction.business_advantage_margin as number)})
                </li>
              </ul>
              {asArray(prediction.contradiction_findings).length > 0 && (
                <>
                  <h3>Contradiction findings</h3>
                  <EvidenceList items={prediction.contradiction_findings} />
                </>
              )}
            </div>
          </section>
        )}

        {/* ── Sectors ── */}
        <section className="biz-section" id={`${prefix}-sectors`}>
          <h2>{view === "profile" ? "Sectors That Fit You Best" : "Business Sectors"}</h2>
          <p>
            Ranked by matching classical planetary significators — a fit score, not a viability guarantee.
          </p>
          <div className="biz-card">
            <div className="biz-sector-leaderboard">
              {sectors.slice(0, view === "profile" ? 12 : sectors.length).map((s) => (
                <div
                  key={`${s.rank}-${s.label}`}
                  className={`biz-sector-row ${s.rank <= 3 ? "tier-top" : "tier-mid"}`}
                >
                  <div className="biz-sector-rank">{s.rank}</div>
                  <div>
                    <div className="biz-sector-label-line">
                      <span className="biz-sector-label">{s.label}</span>
                      <span className="biz-sector-score">{fmtPct(s.score)}</span>
                    </div>
                    <div className="biz-sector-bar-track">
                      <div
                        className="biz-sector-bar-fill"
                        style={{
                          width: `${sectors[0]?.score ? ((s.score ?? 0) / sectors[0].score!) * 100 : 0}%`,
                        }}
                      />
                    </div>
                  </div>
                  <div className="biz-sector-meta">
                    {s.match_confidence && (
                      <span className="biz-chip">{s.match_confidence.replace(/_/g, " ")}</span>
                    )}
                    {s.capital_intensity && (
                      <span className="biz-chip">{s.capital_intensity} capital</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {view === "profile" && sectors.length > 12 && (
              <p style={{ marginTop: "0.75rem", fontSize: "0.75rem" }}>
                Showing top 12 of {sectors.length} ranked sectors. Switch to Astrologer View for the full
                list.
              </p>
            )}
          </div>
        </section>

        {/* ── Timed Windows ── */}
        <section className="biz-section" id={`${prefix}-windows`}>
          <h2>{view === "profile" ? "Favorable Periods Ahead" : "Timed Windows"}</h2>
          <p>Dasha/bhukti windows ranked by business-supportiveness.</p>
          <div className="biz-windows-grid">
            {report.timed_windows.map((w, i) => (
              <div key={i} className="biz-window-block">
                <h3>
                  {w.start_date} → {w.end_date}
                  <span className={`biz-badge ${badgeClass(w.label)}`}>
                    {(w.label ?? "—").replace(/_/g, " ")}
                  </span>
                </h3>
                <p style={{ margin: "0.25rem 0", fontSize: "0.75rem" }}>
                  {w.md_lord} / {w.ad_lord}
                  {w.net_score != null ? ` · ${fmtPct(w.net_score)}` : ""}
                </p>
                {w.evidence?.length ? (
                  <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.1rem", fontSize: "0.75rem" }}>
                    {w.evidence.map((e, j) => (
                      <li key={j}>{e}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>
        </section>

        {/* ── Method Status (astrologer) ── */}
        {view === "astrologer" && (
          <section className="biz-section" id={`${prefix}-method`}>
            <h2>Method-level Status</h2>
            <MethodStatusPanel prediction={prediction} />
            <div className="biz-card" style={{ marginTop: "0.5rem" }}>
              <p>
                <strong>Confidence label:</strong> {report.confidence.label ?? "—"} ·{" "}
                <strong>Leaning:</strong> {report.confidence.overall_leaning ?? "—"}
              </p>
              <p style={{ marginBottom: 0 }}>
                Method agreement:{" "}
                {report.confidence.method_agreement != null
                  ? `${(report.confidence.method_agreement * 100).toFixed(1)}%`
                  : "—"}
              </p>
            </div>
          </section>
        )}

        {/* ── Technical Appendix ── */}
        <div className="biz-appendix-divider" id={`${prefix}-appendix`}>
          <h2>Technical Appendix — Supporting Evidence &amp; Deep-Dive Checks</h2>
          <p>
            Individual classical checks that fed into the verdict, scores, sectors, and timing above.
          </p>
        </div>

        <AppendixSections prediction={prediction} auth={auth} />

        <footer className="biz-footer">
          JyotishAI · Business Astrology Report · {data.model_status} · Traditional Jyotish heuristics;
          decision-support for further reflection, not financial, legal, or medical advice.
        </footer>
      </div>
    </div>
  );
}
