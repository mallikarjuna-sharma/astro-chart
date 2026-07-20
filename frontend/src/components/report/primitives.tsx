import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type Tone = "gold" | "success" | "info" | "warn" | "danger" | "royal" | "muted";

/** Chip / pill tone classes — text in tone color on a translucent tint. */
const PILL_TONE: Record<Tone, string> = {
  gold: "bg-primary/12 text-primary border-primary/25",
  success: "bg-success/12 text-success border-success/25",
  info: "bg-info/12 text-info border-info/25",
  warn: "bg-warn/12 text-warn border-warn/25",
  danger: "bg-danger/12 text-danger border-danger/25",
  royal: "bg-royal/12 text-royal border-royal/25",
  muted: "bg-muted text-muted-foreground border-border",
};

/** Callout / box tone classes — subtle tinted surface with a colored border. */
const CALLOUT_TONE: Record<Tone, string> = {
  gold: "border-primary/25 bg-primary/8",
  success: "border-success/25 bg-success/8",
  info: "border-info/25 bg-info/8",
  warn: "border-warn/25 bg-warn/8",
  danger: "border-danger/25 bg-danger/8",
  royal: "border-royal/25 bg-royal/8",
  muted: "border-border bg-muted/50",
};

const TONE_TEXT: Record<Tone, string> = {
  gold: "text-primary",
  success: "text-success",
  info: "text-info",
  warn: "text-warn",
  danger: "text-danger",
  royal: "text-royal",
  muted: "text-muted-foreground",
};

export const TONE_VAR: Record<Tone, string> = {
  gold: "var(--gold)",
  success: "var(--success)",
  info: "var(--info)",
  warn: "var(--warn)",
  danger: "var(--danger)",
  royal: "var(--royal)",
  muted: "var(--muted-foreground)",
};

/** Outer report container. */
export function ReportShell({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("max-w-[1180px] mx-auto space-y-5 animate-rise", className)}>{children}</div>
  );
}

/** Elevated report surface. */
export function Panel({
  children,
  className,
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={cn("panel", padded && "p-5 md:p-6", className)}>{children}</section>
  );
}

/** Section heading with optional number + tone chip. */
export function SectionTitle({
  n,
  title,
  chip,
  chipTone = "muted",
  icon,
}: {
  n?: number;
  title: string;
  chip?: string;
  chipTone?: Tone;
  icon?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 mb-4">
      <h2 className="flex items-center gap-2.5 font-serif text-lg md:text-xl font-semibold text-foreground leading-tight">
        {n != null ? (
          <span className="grid place-items-center w-7 h-7 rounded-lg text-sm font-bold text-primary-foreground gradient-gold shrink-0">
            {n}
          </span>
        ) : null}
        {icon}
        {title}
      </h2>
      {chip ? <Tag tone={chipTone}>{chip}</Tag> : null}
    </div>
  );
}

/** Small pill / tag. */
export function Tag({
  children,
  tone = "muted",
  className,
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 text-[11px] font-semibold tracking-wide px-2.5 py-1 rounded-full border whitespace-nowrap",
        PILL_TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Tinted callout box. */
export function Callout({
  children,
  tone = "muted",
  label,
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  label?: string;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border px-4 py-3 text-sm text-foreground leading-relaxed", CALLOUT_TONE[tone], className)}>
      {label ? (
        <div className={cn("text-[11px] font-bold uppercase tracking-wider mb-1.5", TONE_TEXT[tone])}>{label}</div>
      ) : null}
      {children}
    </div>
  );
}

/** Metric tile: big value + caption. */
export function StatTile({ value, label, tone = "gold" }: { value: ReactNode; label: string; tone?: Tone }) {
  return (
    <div className="rounded-xl border border-border bg-surface-soft/60 px-3.5 py-3.5 text-center">
      <div className={cn("text-2xl font-bold leading-none tabular-nums", TONE_TEXT[tone])}>{value}</div>
      <div className="text-[11px] text-muted-foreground mt-1.5 leading-snug">{label}</div>
    </div>
  );
}

/** Labeled meter bar. `color` overrides the tone fill (accepts any CSS color). */
export function Meter({
  value,
  tone = "gold",
  color,
  className,
}: {
  value: number;
  tone?: Tone;
  color?: string;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("h-2 rounded-full bg-muted overflow-hidden", className)}>
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${pct}%`, background: color ?? TONE_VAR[tone] }}
      />
    </div>
  );
}

/** Themed data table wrapper. */
export function DataTable({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="overflow-x-auto -mx-1 px-1">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
            {head}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

/** Renders sanitized HTML from the backend inside a theme-aware prose block. */
export function ProseBlock({ html, className }: { html: string; className?: string }) {
  return (
    <div
      className={cn("prose-theme text-sm", className)}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
