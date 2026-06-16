import { cn } from "@/lib/utils";

interface Props {
  score: number;
  label?: string;
  size?: "sm" | "md" | "lg";
}

function classify(score: number) {
  if (score >= 80) return { level: "Very High", badge: "ALL FOUR SYSTEMS AGREE", tone: "text-gold border-gold" };
  if (score >= 65) return { level: "High", badge: "THREE SYSTEMS STRONGLY AGREE", tone: "text-saffron border-saffron" };
  if (score >= 50) return { level: "Moderate", badge: "PARTIAL CONCORDANCE", tone: "text-chart-4 border-chart-4" };
  if (score >= 35) return { level: "Low", badge: "MIXED SIGNALS", tone: "text-accent border-accent" };
  return { level: "Inconclusive", badge: "SYSTEMS DIVERGE", tone: "text-destructive border-destructive" };
}

export function ConfidenceBadge({ score, label, size = "md" }: Props) {
  const { level, badge, tone } = classify(score);
  const dim = size === "sm" ? 60 : size === "lg" ? 120 : 84;
  const stroke = size === "sm" ? 6 : 10;
  const r = (dim - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (score / 100) * c;

  return (
    <div className="flex items-center gap-4">
      <div className="relative" style={{ width: dim, height: dim }}>
        <svg width={dim} height={dim} className="-rotate-90">
          <circle cx={dim/2} cy={dim/2} r={r} stroke="currentColor" strokeWidth={stroke} fill="none" className="text-muted opacity-40" />
          <circle
            cx={dim/2} cy={dim/2} r={r}
            stroke="currentColor" strokeWidth={stroke} fill="none"
            strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
            className={cn("transition-all duration-700", tone.split(" ")[0])}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center flex-col">
          <div className={cn("font-bold", size === "lg" ? "text-3xl" : size === "sm" ? "text-base" : "text-xl", tone.split(" ")[0])}>{score}</div>
          {size !== "sm" && <div className="text-[9px] uppercase tracking-wider text-muted-foreground">/100</div>}
        </div>
      </div>
      {size !== "sm" && (
        <div>
          <div className={cn("text-xs font-semibold uppercase tracking-widest", tone.split(" ")[0])}>{label ?? level}</div>
          <div className="text-sm text-foreground/90 mt-1">{badge}</div>
        </div>
      )}
    </div>
  );
}
