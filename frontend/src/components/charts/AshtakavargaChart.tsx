import { RASI_NAMES, RASI_SHORT } from "@/lib/rasi";
import { cn } from "@/lib/utils";

/** South-Indian fixed rasi cell order in the 4×4 grid (matches SouthIndianChart). */
const SI_CELL_RASI = [11, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

interface AshtakavargaChartProps {
  /** Center label, e.g. "SAV" or the body short code "Su". */
  label: string;
  /** Bindus per rasi, index 0 = Aries … 11 = Pisces. */
  points: number[];
  total?: number;
  /** Rasi this chart's body occupies in D-1, shaded the way pyJHora shades it. */
  highlightRasi?: number | null;
  className?: string;
}

export function AshtakavargaChart({
  label,
  points,
  total,
  highlightRasi,
  className,
}: AshtakavargaChartProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-4 grid-rows-4 gap-px aspect-square w-full border border-border rounded-md overflow-hidden",
        className,
      )}
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
        const occupied = highlightRasi === r;
        return (
          <div
            key={r}
            className={cn(
              "flex flex-col items-center justify-center gap-0.5 border border-border/60 p-0.5 min-h-0 overflow-hidden",
              occupied ? "bg-gold/20 ring-1 ring-inset ring-gold/60" : "bg-card",
            )}
            style={{ gridArea: `r${r}` }}
            title={`${RASI_NAMES[r]}: ${points[r] ?? 0} bindus${occupied ? ` — ${label} in D-1` : ""}`}
          >
            <span className="text-[8px] leading-none text-muted-foreground">{RASI_SHORT[r]}</span>
            <span
              className={cn(
                "text-[13px] leading-none font-semibold tabular-nums",
                occupied ? "text-gold" : "text-foreground",
              )}
            >
              {points[r] ?? 0}
            </span>
          </div>
        );
      })}
      <div
        className="bg-secondary/50 border border-border/60 flex flex-col items-center justify-center text-center p-1"
        style={{ gridArea: "ce" }}
      >
        <span className="text-sm font-bold text-gold leading-none">{label}</span>
        {total != null ? (
          <span className="text-[9px] text-muted-foreground mt-0.5 leading-none tabular-nums">
            {total}
          </span>
        ) : null}
      </div>
    </div>
  );
}
