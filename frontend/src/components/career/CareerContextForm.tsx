import { useState } from "react";
import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { CareerContextInput } from "@/lib/pyjhora/types";

interface Props {
  initial?: CareerContextInput;
  currentAge?: number | null;
  loading?: boolean;
  enrichLlm?: boolean;
  onEnrichLlmChange?: (v: boolean) => void;
  onSubmit?: (ctx: CareerContextInput) => void;
  /** Inline use (e.g. profile wizard) — no submit button or form wrapper. */
  embedded?: boolean;
  value?: CareerContextInput;
  onChange?: (ctx: CareerContextInput) => void;
}

/** Rough heuristic: working years ≈ age - 22, clamped to [0, 50]. */
export function defaultYearsExperience(age: number | null | undefined): number {
  if (typeof age !== "number" || !Number.isFinite(age)) return 0;
  return Math.max(0, Math.min(50, Math.round(age - 22)));
}

export function defaultCareerContext(currentAge?: number | null): CareerContextInput {
  return {
    employment_status: "employed",
    designation: "",
    years_experience: defaultYearsExperience(currentAge),
    company_type: "mnc",
    industry_sector: "software",
    desired_outcome: "promotion",
    join_date: "",
    last_promotion_date: "",
    geographic_preference: "open",
    actively_looking: false,
    on_notice_period: false,
  };
}

const EMPLOYMENT = ["employed", "self_employed", "unemployed", "student", "career_break"];
const COMPANY_TYPES = ["mnc", "indian_corporate", "startup", "government", "consulting", "family_business"];
const INDUSTRIES = ["software", "finance", "healthcare", "manufacturing", "consulting", "education", "media", "government", "research", "other"];
const OUTCOMES = ["promotion", "salary_hike", "job_change", "foreign_assignment", "entrepreneurship", "career_pivot", "stability"];
const GEO = ["open", "domestic_only", "foreign_preferred", "remote_only"];

export function CareerContextForm({
  initial,
  currentAge,
  loading = false,
  enrichLlm = true,
  onEnrichLlmChange,
  onSubmit,
  embedded = false,
  value,
  onChange,
}: Props) {
  const isControlled = value !== undefined && onChange !== undefined;
  const [internalForm, setInternalForm] = useState<CareerContextInput>(() =>
    initial ?? defaultCareerContext(currentAge),
  );
  const form = isControlled ? value : internalForm;

  const update = <K extends keyof CareerContextInput>(k: K, v: CareerContextInput[K]) => {
    const next = { ...form, [k]: v };
    if (isControlled) {
      onChange(next);
    } else {
      setInternalForm(next);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit?.(form);
  };

  const fields = (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 gap-4">
        <Field label="Employment status">
          <Select
            value={form.employment_status}
            onValueChange={(v) => update("employment_status", v)}
          >
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {EMPLOYMENT.map((o) => (
                <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field label="Designation">
          <Input
            value={form.designation ?? ""}
            placeholder="e.g. Senior Manager"
            onChange={(e) => update("designation", e.target.value)}
          />
        </Field>

        <Field label="Years of experience">
          <Input
            type="number"
            min={0}
            max={60}
            value={form.years_experience ?? 0}
            onChange={(e) => update("years_experience", Number(e.target.value))}
          />
        </Field>

        <Field label="Company type">
          <Select value={form.company_type} onValueChange={(v) => update("company_type", v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {COMPANY_TYPES.map((o) => (
                <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field label="Industry">
          <Select value={form.industry_sector} onValueChange={(v) => update("industry_sector", v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {INDUSTRIES.map((o) => (
                <SelectItem key={o} value={o}>{o}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field label="Desired outcome">
          <Select value={form.desired_outcome} onValueChange={(v) => update("desired_outcome", v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {OUTCOMES.map((o) => (
                <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field label="Current job start date">
          <Input
            type="date"
            value={form.join_date ?? ""}
            onChange={(e) => update("join_date", e.target.value)}
          />
        </Field>

        <Field label="Last promotion date">
          <Input
            type="date"
            value={form.last_promotion_date ?? ""}
            onChange={(e) => update("last_promotion_date", e.target.value)}
          />
        </Field>

        <Field label="Geographic preference">
          <Select
            value={form.geographic_preference}
            onValueChange={(v) => update("geographic_preference", v)}
          >
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {GEO.map((o) => (
                <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>

      <div className="flex flex-wrap items-center gap-4 pt-2">
        <label className="flex items-center gap-2 text-sm">
          <Switch
            checked={!!form.actively_looking}
            onCheckedChange={(v) => update("actively_looking", v)}
          />
          Actively looking
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Switch
            checked={!!form.on_notice_period}
            onCheckedChange={(v) => update("on_notice_period", v)}
          />
          On notice period
        </label>
        {!embedded && onEnrichLlmChange ? (
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={enrichLlm} onCheckedChange={onEnrichLlmChange} />
            Enrich narratives (slower, ~30-60s)
          </label>
        ) : null}
        {!embedded ? (
          <div className="ml-auto w-full sm:w-auto">
            <Button type="submit" disabled={loading} className="w-full sm:w-auto">
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Building timeline…
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-2" />
                  Build Career Timeline
                </>
              )}
            </Button>
          </div>
        ) : null}
      </div>
    </>
  );

  if (embedded) {
    return <div className="space-y-4">{fields}</div>;
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {fields}
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs uppercase tracking-wide text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}
