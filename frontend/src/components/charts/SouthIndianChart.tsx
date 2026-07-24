import type { DivisionalChart } from "@/lib/pyjhora/types";
import { cn } from "@/lib/utils";

/** South-Indian fixed rasi cell order in the 4×4 grid (matches pyJHora web/index.html). */
const SI_CELL_RASI = [11, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

interface SouthIndianChartProps {
  chart: DivisionalChart;
  meta?: Record<string, unknown>;
  compact?: boolean;
  size?: "default" | "large" | "fit";
  className?: string;
}

export function SouthIndianChart({
  chart,
  meta,
  compact,
  size = "default",
  className,
}: SouthIndianChartProps) {
  const byRasi = Object.fromEntries((chart.houses ?? []).map((h) => [h.rasi, h]));

  const metaLines = meta
    ? [meta.place_label, meta.birth_local, meta.ayanamsa_mode ? `Ayan: ${meta.ayanamsa_mode}` : null]
        .filter(Boolean)
        .join(" · ")
    : "";

  const isFit = size === "fit";

  const widthClass = isFit
    ? "h-full w-full flex flex-col min-h-0"
    : compact
      ? "w-full max-w-xs"
      : size === "large"
        ? "w-full max-w-[min(100%,22rem)] sm:max-w-md md:max-w-lg lg:max-w-2xl mx-auto"
        : "w-full max-w-sm";

  const textClass = isFit
    ? "text-xs md:text-sm"
    : size === "large"
      ? "text-xs sm:text-sm"
      : "text-[10px] sm:text-xs";
  const labelClass = isFit
    ? "text-[10px] md:text-xs"
    : size === "large"
      ? "text-[10px] sm:text-xs"
      : "text-[9px]";

  return (
    <div className={cn(widthClass, className)}>
      <div
        className={cn(
          "text-center font-semibold shrink-0",
          isFit ? "text-sm md:text-base mb-1.5" : size === "large" ? "text-base sm:text-lg mb-2" : "text-sm mb-2",
        )}
      >
        {chart.name}
      </div>
      <div
        className={cn(
          "grid grid-cols-4 grid-rows-4 gap-px border border-border rounded-md overflow-hidden",
          isFit ? "flex-1 min-h-0 w-full max-h-full aspect-square mx-auto" : "aspect-square w-full",
          textClass,
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
          const h = byRasi[r] ?? { rasi: r, rasi_name: "", bodies: [] as string[] };
          return (
            <div
              key={r}
              className={cn(
                "bg-card border border-border/60 flex flex-col gap-0.5 min-h-0 overflow-hidden",
                isFit ? "p-1.5 md:p-2" : "p-1",
              )}
              style={{ gridArea: `r${r}` }}
            >
              <span className={`${labelClass} text-muted-foreground leading-none truncate`}>
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
          className={cn(
            "bg-secondary/50 flex flex-col items-center justify-center text-center font-bold border border-border/60",
            isFit ? "p-1.5 md:p-2" : "p-1",
          )}
          style={{ gridArea: "ce" }}
        >
          <span className={isFit ? "text-xs md:text-sm" : size === "large" ? "text-sm sm:text-base" : "text-xs"}>
            {chart.name}
          </span>
          {metaLines && (
            <span className={`${labelClass} font-normal text-muted-foreground mt-0.5 leading-tight`}>
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
