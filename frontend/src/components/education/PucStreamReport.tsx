import type { PucAnalysisResponse } from "@/lib/pyjhora/types";
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
      <div className="rounded-2xl border border-border bg-card/80 p-6 md:p-8 shadow-sm">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-teal-700 dark:text-teal-400">
          JyotishAI Stream Determination
        </div>
        <h2 className="font-serif text-2xl md:text-3xl font-semibold mt-1">
          {studentName} · PUC Stream Report
        </h2>
        <p className="text-sm text-muted-foreground mt-2 max-w-3xl">
          Evidence-weighted guidance across Science, Commerce and Humanities, with subject-level
          astrological rationale for 11th–12th stream selection.
        </p>
        <p className="text-xs text-muted-foreground mt-2">
          Age: {typeof age === "number" ? age.toFixed(1) : "—"}
          {" · "}
          Profile: {String(report.calculation_profile ?? "—")}
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
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
      </div>

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
        <Panel className="mt-5 border-teal-200/60 dark:border-teal-900/50 bg-teal-50/30 dark:bg-teal-950/20">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-3">
            Narrative: {String(narrative.status ?? "—")}
            {narrative.provider ? ` · ${String(narrative.provider)}` : ""}
            {narrative.decision_locked ? " · decision locked" : ""}
          </div>
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <SectionTitle title="What this means for the student" />
              {studentParagraphs.map((p, i) => (
                <p key={i} className="text-sm text-muted-foreground mt-2 leading-relaxed">
                  {p}
                </p>
              ))}
            </div>
            <div>
              <SectionTitle title="Astrological reasoning" />
              {astroParagraphs.map((p, i) => (
                <p key={i} className="text-sm text-muted-foreground mt-2 leading-relaxed">
                  {p}
                </p>
              ))}
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-4">
            The narrative explains the deterministic result and cannot change scores, ranking, or tie status.
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
              className={isTop ? "border-teal-600/50 bg-teal-50/20 dark:bg-teal-950/10" : ""}
            >
              <div className="flex flex-wrap items-baseline gap-2">
                <h3 className="font-serif text-lg font-semibold">
                  {idx + 1}. {stream.label ?? streamLabel(stream.stream_id)}
                  {stream.sub_archetype ? (
                    <span className="text-sm font-normal text-muted-foreground ml-1">
                      ({stream.sub_archetype})
                    </span>
                  ) : null}
                  {isTop ? (
                    <Tag tone="success" className="ml-2">
                      Top ranked
                    </Tag>
                  ) : null}
                </h3>
              </div>
              {stream.description ? (
                <p className="text-sm text-muted-foreground mt-1">{stream.description}</p>
              ) : null}
              <p className="text-sm mt-2">
                Stream score: <strong>{fmtScore(score)} / 100</strong>
              </p>
              <Meter value={score} tone="success" className="mt-2" />
              <p className="text-xs text-muted-foreground mt-2">
                Section signals: role_placement={stream.role_placement_signal_state ?? "—"},
                relational_d1={stream.relational_d1_signal_state ?? "—"},
                d24_confirmation={stream.d24_confirmation_signal_state ?? "—"}
              </p>

              <div className="mt-4">
              <DataTable
                head={
                  <>
                    <th className="py-2 pr-3">Subject</th>
                    <th className="py-2 pr-3">Score</th>
                    <th className="py-2">Astrological rationale</th>
                  </>
                }
              >
                {(stream.subjects ?? []).map((sub) => (
                  <tr key={sub.subject_id ?? sub.label} className="border-b border-border/60 align-top">
                    <td className="py-2.5 pr-3">
                      {sub.label}
                      {sub.core ? <Tag tone="success" className="ml-1.5 text-[10px]">Core</Tag> : null}
                      {!sub.core ? <Tag tone="muted" className="ml-1.5 text-[10px]">Elective</Tag> : null}
                      {sub.shared_elective ? (
                        <span className="text-[10px] text-muted-foreground ml-1">(shared)</span>
                      ) : null}
                      {sub.mandatory_contraindication ? (
                        <Tag tone="warn" className="ml-1.5 text-[10px]">Capped</Tag>
                      ) : null}
                    </td>
                    <td className="py-2.5 pr-3 font-bold text-teal-700 dark:text-teal-400">
                      {fmtScore(sub.score)}
                    </td>
                    <td className="py-2.5 text-muted-foreground text-xs leading-relaxed">
                      {sub.rationale}
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
          <p className="text-xs text-muted-foreground mt-1 mb-3">
            Independent supplementary check against the adult career-field engine.
          </p>
          <DataTable
            head={
              <>
                <th className="py-2 pr-3">Check</th>
                <th className="py-2">Value</th>
              </>
            }
          >
            <tr className="border-b border-border/60">
              <td className="py-2 pr-3">Field determination top field</td>
              <td className="py-2">{String(crossValidation.field_determination_top_cluster_field_label ?? "—")}</td>
            </tr>
            <tr className="border-b border-border/60">
              <td className="py-2 pr-3">Domain implies stream</td>
              <td className="py-2">{String(crossValidation.domain_implied_stream ?? "—")}</td>
            </tr>
            <tr className="border-b border-border/60">
              <td className="py-2 pr-3">Stream determination top stream</td>
              <td className="py-2">{String(crossValidation.stream_determination_top_ranked_stream ?? "—")}</td>
            </tr>
            <tr>
              <td className="py-2 pr-3 font-semibold">Result</td>
              <td className="py-2 font-semibold">{crossValidation.agree ? "AGREE" : "DISAGREE"}</td>
            </tr>
          </DataTable>
        </Panel>
      ) : null}

      <p className="text-xs text-muted-foreground mt-6 border-t pt-4">
        {String(report.disclaimer ?? "For educational guidance only.")}
      </p>
    </ReportShell>
  );
}
