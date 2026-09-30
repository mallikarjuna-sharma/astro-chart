import type { PucAnalysisResponse } from "@/lib/pyjhora/types";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
  data: PucAnalysisResponse;
}

interface StreamSubject {
  subject_id?: string;
  label?: string;
  core?: boolean;
  shared_elective?: boolean;
  mandatory_contraindication?: boolean;
  score?: number;
  rationale?: string;
}

interface StreamRow {
  stream_id?: string;
  label?: string;
  sub_archetype?: string;
  description?: string;
  normalized_score?: number;
  score?: number;
  role_placement_signal_state?: string;
  relational_d1_signal_state?: string;
  d24_confirmation_signal_state?: string;
  subjects?: StreamSubject[];
}

function fmtScore(n: number | undefined) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  return n.toFixed(1);
}

function streamLabel(id: string | undefined) {
  if (!id) return "—";
  return id.charAt(0).toUpperCase() + id.slice(1);
}

export function PucStreamReport({ data }: Props) {
  const report = data.report ?? {};
  const streams = (report.streams ?? []) as StreamRow[];
  const topId = report.top_ranked_stream ?? report.dominant_stream;
  const narrative = data.stream_narrative ?? report.stream_narrative;
  const studentName = data.student?.name ?? report.name ?? "Student";
  const age = data.student?.current_age ?? report.current_age;
  const crossValidation = report.cross_validation as Record<string, unknown> | null | undefined;

  const studentParagraphs =
  (narrative?.student_narrative as { paragraphs?: string[] } | undefined)?.paragraphs ?? [];
  const astroParagraphs =
  (narrative?.astrological_narrative as { paragraphs?: string[] } | undefined)?.paragraphs ?? [];

  return (
    <ReportShell>
      {/* Hero header */}
      <header className="text-center pb-2 mt-4">
        <div className="text-[11px] font-bold tracking-[0.22em] text-gold uppercase mb-3">
          JyotishAI Stream Determination
        </div>
        <h2 className="font-serif text-3xl md:text-[2.5rem] font-semibold text-foreground leading-tight">
          {studentName} · PUC Stream Report
        </h2>
        <p className="text-[0.95rem] text-muted-foreground mt-4 tracking-wide flex items-center justify-center gap-2 flex-wrap">
          <span>Age {typeof age === "number" ? age.toFixed(1) : "—"}</span>
          <span>· Profile: {String(report.calculation_profile ?? "—")}</span>
        </p>
        <div className="mt-3 max-w-2xl mx-auto text-[0.95rem] text-muted-foreground leading-relaxed">
          Evidence-weighted guidance across Science, Commerce and Humanities, with subject-level
          astrological rationale for 11th–12th stream selection.
        </div>
      </header>

      <Panel className="mt-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatTile label="Recommendation status" value={String(report.recommendation_status ?? "—")} />
          <StatTile
            label="Evidence completeness"
            value={
              typeof report.evidence_completeness === "number"
                ? `${Math.round(report.evidence_completeness * 100)}%`
                : "—"
            }
          />
          <StatTile label="Dominant stream" value={streamLabel(topId)} />
          <StatTile
            label="Top-two score gap"
            value={fmtScore(report.score_gap_top_two as number | undefined)}
          />
        </div>
      </Panel>

      {report.is_close_call ? (
        <Callout tone="warn" className="mt-4">
          Close call among streams — review the score gap and subject evidence before deciding.
          {report.close_call_note ? ` ${report.close_call_note}` : ""}
        </Callout>
      ) : null}

      {report.eligibility_note ? (
        <p className="text-xs text-muted-foreground mt-4">{String(report.eligibility_note)}</p>
      ) : null}

      {narrative && studentParagraphs.length ? (
        <Panel className="mt-5">
          <SectionTitle title="AI Narrative Analysis" chip={String(narrative.status ?? "—")} chipTone="info" />
          
          <div className="mt-4">
            <div className="text-[11px] font-bold uppercase tracking-wider text-foreground mb-2">
              What this means for the student
            </div>
            <div className="rounded-xl bg-primary/8 border-l-4 border-gold px-5 py-4 text-[1.02rem] text-foreground leading-relaxed">
              {studentParagraphs.map((p, i) => (
                <p key={i} className={i > 0 ? "mt-3" : ""}>
                  {p}
                </p>
              ))}
            </div>
          </div>
          
          <Accordion type="single" collapsible className="mt-4">
            <AccordionItem value="astro" className="border-none bg-surface-soft/40 border border-border/50 rounded-xl px-5">
              <AccordionTrigger className="text-[11px] uppercase tracking-wider text-muted-foreground hover:no-underline py-4">
                <span className="flex items-center gap-2"><span className="text-[14px]">🔭</span> Astrological Reasoning</span>
              </AccordionTrigger>
              <AccordionContent className="pb-5 pt-1">
                <ul className="space-y-3.5">
                  {astroParagraphs.map((p, i) => (
                    <li key={i} className="text-[0.95rem] text-muted-foreground leading-relaxed flex items-start gap-2.5">
                      <span className="text-gold mt-[0.35rem] shrink-0 text-lg leading-none">•</span>
                      <span>{p}</span>
                    </li>
                  ))}
                </ul>
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          <p className="text-xs text-muted-foreground mt-5">
            The narrative explains the deterministic result and cannot change scores, ranking, or tie status.
            {narrative.provider ? ` · Provider: ${String(narrative.provider)}` : ""}
            {narrative.decision_locked ? " · decision locked" : ""}
          </p>
        </Panel>
      ) : null}

      <div className="grid gap-5 mt-5">
        {streams.map((stream, idx) => {
          const isTop = stream.stream_id === topId;
          const score = stream.normalized_score ?? stream.score ?? 0;
          return (
            <Panel
              key={stream.stream_id ?? idx}
              className={isTop ? "border-l-[4px] border-l-gold shadow-sm" : ""}
            >
              <div className="flex flex-wrap items-baseline gap-2">
                <h3 className="font-serif text-[1.15rem] font-semibold text-foreground">
                  {idx + 1}. {stream.label ?? streamLabel(stream.stream_id)}
                  {stream.sub_archetype ? (
                    <span className="text-[0.95rem] font-normal text-muted-foreground ml-1.5">
                      ({stream.sub_archetype})
                    </span>
                  ) : null}
                  {isTop ? (
                    <Tag tone="gold" className="ml-3 border-gold/30 bg-gold/10 text-gold shadow-none font-bold">
                      Top Ranked
                    </Tag>
                  ) : null}
                </h3>
              </div>
              {stream.description ? (
                <p className="text-[0.95rem] text-muted-foreground mt-2 break-words">{stream.description}</p>
              ) : null}
              <div className="flex items-center gap-3 mt-4 mb-2">
                <span className="text-[13px] font-semibold text-foreground w-32 shrink-0">Stream Score: {fmtScore(score)}</span>
                <div className="flex-1">
                  <Meter value={score} tone="gold" className="h-2" />
                </div>
              </div>
              <div className="text-[11.5px] text-muted-foreground mb-4 break-words">
                <strong className="font-semibold text-foreground/80">Component signals:</strong>{" "}
                <span className="inline-flex flex-wrap gap-x-1.5 gap-y-0.5">
                  <span>role_placement={stream.role_placement_signal_state ?? "—"}</span>
                  <span>·</span>
                  <span>relational_d1={stream.relational_d1_signal_state ?? "—"}</span>
                  <span>·</span>
                  <span>d24_confirmation={stream.d24_confirmation_signal_state ?? "—"}</span>
                </span>
              </div>

              <div className="mt-4 border border-border/60 rounded-xl overflow-hidden shadow-sm">
                <DataTable
                  head={
                    <>
                      <th className="py-2.5 px-3 bg-muted/40">Subject</th>
                      <th className="py-2.5 px-3 bg-muted/40">Score</th>
                      <th className="py-2.5 px-3 bg-muted/40">Astrological rationale</th>
                    </>
                  }
                >
                  {(stream.subjects ?? []).map((sub) => (
                    <tr key={sub.subject_id ?? sub.label} className="border-b border-border/60 align-top last:border-0 hover:bg-muted/10 transition-colors">
                      <td className="py-3 px-3">
                        <span className="font-medium text-foreground">{sub.label}</span>
                        {sub.core ? <Tag tone="gold" className="ml-2 text-[10px] border-gold/20 text-gold bg-gold/5 shadow-none">Core</Tag> : null}
                        {!sub.core ? <Tag tone="muted" className="ml-2 text-[10px] bg-transparent shadow-none">Elective</Tag> : null}
                        {sub.shared_elective ? (
                          <span className="text-[10px] text-muted-foreground ml-1">(shared)</span>
                        ) : null}
                        {sub.mandatory_contraindication ? (
                          <Tag tone="warn" className="ml-2 text-[10px] shadow-none">Capped</Tag>
                        ) : null}
                      </td>
                      <td className="py-3 px-3 font-bold text-foreground">
                        {fmtScore(sub.score)}
                      </td>
                      <td className="py-2.5 px-3">
                        <Accordion type="single" collapsible>
                          <AccordionItem value="rationale" className="border-none">
                            <AccordionTrigger className="text-[10px] uppercase text-muted-foreground hover:no-underline py-1">
                              <span className="flex items-center gap-1.5 font-semibold tracking-wider"><span className="text-[12px]">🔭</span> View Astro Logic</span>
                            </AccordionTrigger>
                            <AccordionContent className="pt-1.5 text-[11.5px] text-muted-foreground/90 leading-relaxed pb-1">
                              {sub.rationale}
                            </AccordionContent>
                          </AccordionItem>
                        </Accordion>
                      </td>
                    </tr>
                  ))}
                </DataTable>
              </div>
            </Panel>
          );
        })}
      </div>

      {crossValidation ? (
        <Panel className="mt-5">
          <SectionTitle
            title="Cross-check vs. Field Determination"
            chip={crossValidation.agree ? "Agree" : "Review"}
            chipTone={crossValidation.agree ? "success" : "warn"}
          />
          <p className="text-[12px] text-muted-foreground mt-1 mb-3">
            Independent supplementary check against the adult career-field engine.
          </p>
          <div className="border border-border/60 rounded-xl overflow-hidden shadow-sm">
            <DataTable
              head={
                <>
                  <th className="py-2.5 px-3 bg-muted/40">Check</th>
                  <th className="py-2.5 px-3 bg-muted/40">Value</th>
                </>
              }
            >
              <tr className="border-b border-border/60 hover:bg-muted/10 transition-colors">
                <td className="py-3 px-3">Field determination top field</td>
                <td className="py-3 px-3 font-medium text-foreground">{String(crossValidation.field_determination_top_cluster_field_label ?? "—")}</td>
              </tr>
              <tr className="border-b border-border/60 hover:bg-muted/10 transition-colors">
                <td className="py-3 px-3">Domain implies stream</td>
                <td className="py-3 px-3 font-medium text-foreground">{String(crossValidation.domain_implied_stream ?? "—")}</td>
              </tr>
              <tr className="border-b border-border/60 hover:bg-muted/10 transition-colors">
                <td className="py-3 px-3">Stream determination top stream</td>
                <td className="py-3 px-3 font-medium text-foreground">{String(crossValidation.stream_determination_top_ranked_stream ?? "—")}</td>
              </tr>
              <tr className="hover:bg-muted/10 transition-colors">
                <td className="py-3 px-3 font-semibold text-foreground">Result</td>
                <td className="py-3 px-3 font-semibold text-foreground">
                  {crossValidation.agree ? (
                    <span className="text-success">AGREE</span>
                  ) : (
                    <span className="text-warn">DISAGREE</span>
                  )}
                </td>
              </tr>
            </DataTable>
          </div>
        </Panel>
      ) : null}

      <p className="text-xs text-muted-foreground mt-6 border-t pt-4">
        {String(report.disclaimer ?? "For educational guidance only.")}
      </p>
    </ReportShell>
  );
}
