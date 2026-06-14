import type { DivisionalChart } from "@/lib/pyjhora/types";

/** South-Indian fixed rasi cell order in the 4×4 grid (matches pyJHora web/index.html). */
const SI_CELL_RASI = [11, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

interface SouthIndianChartProps {
  chart: DivisionalChart;
  meta?: Record<string, unknown>;
  compact?: boolean;
}

export function SouthIndianChart({ chart, meta, compact }: SouthIndianChartProps) {
  const byRasi = Object.fromEntries((chart.houses ?? []).map((h) => [h.rasi, h]));

  const metaLines = meta
    ? [meta.place_label, meta.birth_local, meta.ayanamsa_mode ? `Ayan: ${meta.ayanamsa_mode}` : null]
        .filter(Boolean)
        .join(" · ")
    : "";

  return (
    <div className={compact ? "w-full max-w-xs" : "w-full max-w-sm"}>
      <div className="text-center font-semibold text-sm mb-2">{chart.name}</div>
      <div
        className="grid grid-cols-4 grid-rows-4 aspect-square gap-px border border-border rounded-md overflow-hidden text-[10px] sm:text-xs"
        style={{
          gridTemplateAreas: `
            "r11 r0  r1  r2"
            "r10 ce  ce  r3"
            "r9  ce  ce  r4"
            "r8  r7  r6  r5"
          `,
        }}
      >
        {SI_CELL_RASI.map((r) => {
          const h = byRasi[r] ?? { rasi: r, rasi_name: "", bodies: [] as string[] };
          return (
            <div
              key={r}
              className="bg-card border border-border/60 p-1 flex flex-col gap-0.5 min-h-0 overflow-hidden"
              style={{ gridArea: `r${r}` }}
            >
              <span className="text-[9px] text-muted-foreground leading-none truncate">
                {h.rasi_name || `R${r}`}
              </span>
              <div className="flex flex-wrap gap-0.5 font-semibold text-gold">
                {h.bodies.map((b) => (
                  <span key={b} className="px-0.5 rounded bg-secondary/80">
                    {b}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
        <div
          className="bg-secondary/50 flex flex-col items-center justify-center p-1 text-center font-bold border border-border/60"
          style={{ gridArea: "ce" }}
        >
          <span className="text-xs">{chart.name}</span>
          {metaLines && (
            <span className="text-[9px] font-normal text-muted-foreground mt-0.5 leading-tight">
              {String(metaLines)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function ChartLegend() {
  return (
    <p className="text-xs text-muted-foreground mt-3">
      Codes: La Lagna · Su Sun · Mo Moon · Ma Mars · Me Mercury · Ju Jupiter · Ve Venus · Sa Saturn ·
      Ra Rahu · Ke Ketu · Gu Gulika · Md Maandi
    </p>
  );
}
