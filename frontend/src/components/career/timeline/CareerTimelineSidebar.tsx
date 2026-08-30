import type { CareerChartInsights } from "@/lib/pyjhora/types";

function InsightGrid({ items }: { items: Array<{ label: string; value: string; wide?: boolean }> }) {
  return (
    <div className="grid grid-cols-2 gap-2.5">
      {items.map(({ label, value, wide }) => (
        <div key={label} className={wide ? "col-span-2" : ""}>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
          <div className="text-sm font-medium text-foreground mt-0.5">{value || "—"}</div>
        </div>
      ))}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted-foreground mb-3">{title}</div>
      {children}
    </div>
  );
}

function strengthBarClass(score: number): string {
  if (score >= 1.4) return "bg-success";
  if (score >= 1.0) return "bg-warn";
  return "bg-danger/70";
}

export function CareerTimelineSidebar({ insights }: { insights?: CareerChartInsights }) {
  if (!insights) return null;
  const snap = insights.snapshot ?? {};

  return (
    <div className="space-y-5 w-full text-left">
      <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground px-0.5">Snapshot</div>
      <div className="rounded-2xl border border-border bg-card p-5 shadow-sm space-y-4">
        {[
          ["Lagna", snap.lagna_sign],
          ["Current Dasha", snap.current_dasha],
          ["Atmakaraka", snap.atmakaraka],
          ["Confidence", snap.confidence],
        ].map(([label, value]) => (
          <div key={label} className="pb-4 border-b border-border/60 last:border-0 last:pb-0">
            <div className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">{label}</div>
            <div className="text-[0.98rem] font-semibold text-foreground mt-1 leading-snug">{value || "—"}</div>
          </div>
        ))}
      </div>

      {insights.planetary_strength?.length ? (
        <>
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground px-0.5">
            Planetary Strength
          </div>
          <Panel title="Planetary Strength (Shadbala)">
            <div className="space-y-2">
              {insights.planetary_strength.map((p) => (
                <div key={p.name} className="grid grid-cols-[72px_1fr_36px] items-center gap-2 text-xs">
                  <div className="font-medium">
                    {p.name}
                    {p.tags?.map((t) => (
                      <span key={t} className="ml-1 text-[9px] px-1 py-0.5 rounded border border-gold/30 text-gold">
                        {t}
                      </span>
                    ))}
                    {p.dignity ? (
                      <span className="ml-1 text-[9px] px-1 py-0.5 rounded border border-border text-muted-foreground">
                        {p.dignity}
                      </span>
                    ) : null}
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full rounded-full ${strengthBarClass(p.score)}`}
                      style={{ width: `${p.pct}%` }}
                    />
                  </div>
                  <div className="tabular-nums text-right text-muted-foreground">{p.score.toFixed(2)}</div>
                </div>
              ))}
            </div>
          </Panel>
        </>
      ) : null}

      {insights.d10 ? (
        <>
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground px-0.5">D10 Insights</div>
          <Panel title="D10 (Dashamsha) Insights">
            <InsightGrid
              items={[
                { label: "D10 Lagna", value: insights.d10.lagna ?? "—" },
                { label: "D10 H10 Lord", value: insights.d10.h10_lord ?? "—" },
                {
                  label: "H10 Occupants",
                  value: insights.d10.h10_occupants?.length ? insights.d10.h10_occupants.join(", ") : "—",
                  wide: true,
                },
                {
                  label: "D10 Strength Score",
                  value: insights.d10.strength_score != null ? String(insights.d10.strength_score) : "—",
                  wide: true,
                },
              ]}
            />
          </Panel>
        </>
      ) : null}

      {insights.kp ? (
        <>
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground px-0.5">KP Insights</div>
          <Panel title="KP Insights — H10 Cuspal Chain">
            <InsightGrid
              items={[
                { label: "Sign Lord", value: insights.kp.sign_lord ?? "—" },
                { label: "Star Lord", value: insights.kp.star_lord ?? "—" },
                { label: "Sub Lord", value: insights.kp.sub_lord ?? "—" },
                { label: "Sub-Sub Lord", value: insights.kp.sub_sub_lord ?? "—" },
              ]}
            />
            {insights.kp.birth_time_uncertain ? (
              <p className="text-xs text-warn mt-3 leading-relaxed">
                KP sub-lord/star-lord indications above are shown with reduced confidence because birth time
                precision is uncertain.
              </p>
            ) : null}
          </Panel>
        </>
      ) : null}

      {insights.kn_rao ? (
        <>
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground px-0.5">KN Rao Insights</div>
          <Panel title="KN Rao Insights — Mahadasha">
            <InsightGrid
              items={[
                { label: "Mahadasha Lord", value: insights.kn_rao.md_lord ?? "—" },
                { label: "MD Lord Placed In", value: insights.kn_rao.md_lord_house ?? "—" },
                { label: "Houses Ruled by MD Lord", value: insights.kn_rao.md_houses_ruled ?? "—", wide: true },
              ]}
            />
          </Panel>
        </>
      ) : null}

      {insights.parashara ? (
        <>
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground px-0.5">Parashara Insights</div>
          <Panel title="Parashara Insights">
            <InsightGrid
              items={[
                { label: "Lagna Lord", value: insights.parashara.lagna_lord ?? "—" },
                { label: "Lagna Lord Dignity", value: insights.parashara.lagna_lord_dignity ?? "—" },
                { label: "Active Yogas", value: insights.parashara.active_yogas ?? "—", wide: true },
              ]}
            />
          </Panel>
        </>
      ) : null}

      {insights.jaimini ? (
        <>
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground px-0.5">Jaimini Insights</div>
          <Panel title="Jaimini Insights">
            <InsightGrid
              items={[
                { label: "Atmakaraka (AK)", value: insights.jaimini.atmakaraka ?? "—" },
                { label: "Amatyakaraka (AmK)", value: insights.jaimini.amatyakaraka ?? "—" },
                { label: "Arudha Lagna", value: insights.jaimini.arudha_lagna ?? "—" },
                { label: "Karma Pada (A10)", value: insights.jaimini.karma_pada ?? "—" },
                { label: "Karakamsha", value: insights.jaimini.karakamsha ?? "—" },
                { label: "Darakaraka (DK)", value: insights.jaimini.darakaraka ?? "—" },
              ]}
            />
          </Panel>
        </>
      ) : null}
    </div>
  );
}
