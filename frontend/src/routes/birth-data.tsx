import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { useState } from "react";
import { toast } from "sonner";
import { PlaceAutocomplete } from "@/components/charts/PlaceAutocomplete";
import {
  buildBirthInput,
  buildUserInfo,
  defaultStudentContext,
  parseBirthDateTime,
  saveAndGenerateCharts,
  ensureUserId,
  PYJHORA_LS_USER,
} from "@/lib/pyjhora";
import type { GeocodeResponse } from "@/lib/pyjhora/types";

export const Route = createFileRoute("/birth-data")({
  head: () => ({ meta: [{ title: "Birth Data — JyotishAI" }] }),
  component: BirthDataPage,
});

const AYANAMSA_OPTIONS = [
  { value: "LAHIRI", label: "Lahiri (Chitrapaksha)" },
  { value: "KP", label: "KP (Krishnamurti)" },
  { value: "RAMAN", label: "Raman" },
  { value: "TRUE_CITRA", label: "True Citra" },
  { value: "TRUE_PUSHYA", label: "True Pushya" },
];

function splitCsv(v: string): string[] {
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function BirthDataPage() {
  const nav = useNavigate();
  const [saving, setSaving] = useState(false);
  const [progress, setProgress] = useState("");

  const [form, setForm] = useState({
    displayName: "Demo user",
    email: "",
    date: "2014-10-08",
    time: "13:00:00",
    locationQuery: "srirangam",
    placeLabel: "Srirangam, Tiruchirappalli, Tamil Nadu, India",
    latitude: "10.8627",
    longitude: "78.6928",
    timezoneOffsetHours: "5.5",
    ayanamsa: "LAHIRI",
    useTrueNodes: false,
    includeOuterPlanets: false,
    gender: "O" as "M" | "F" | "O",
    educationSystem: "India_CBSE",
    riskAppetite: "MODERATE" as "LOW" | "MODERATE" | "HIGH",
    interestedIn: "",
    excelAt: "",
    financialConstraints: false,
  });

  const update = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const applyGeocode = (geo: GeocodeResponse) => {
    update("latitude", String(geo.latitude));
    update("longitude", String(geo.longitude));
    update("placeLabel", geo.place_label);
    if (geo.timezone_offset_hours != null) {
      update("timezoneOffsetHours", String(geo.timezone_offset_hours));
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.displayName.trim()) {
      toast.error("Display name is required");
      return;
    }

    setSaving(true);
    setProgress("Starting…");
    try {
      const userId = ensureUserId(localStorage.getItem(PYJHORA_LS_USER) ?? undefined);
      localStorage.setItem(PYJHORA_LS_USER, userId);

      const dt = parseBirthDateTime(form.date, form.time);
      const birthInput = buildBirthInput(dt, {
        place_label: form.placeLabel || "Birth place",
        latitude: Number(form.latitude),
        longitude: Number(form.longitude),
        timezone_offset_hours: Number(form.timezoneOffsetHours),
        ayanamsa: form.ayanamsa,
        use_true_nodes: form.useTrueNodes,
        include_outer_planets: form.includeOuterPlanets,
      });

      const userInfo = buildUserInfo(form.displayName, form.email, form.locationQuery);
      const studentContext = {
        ...defaultStudentContext(),
        pob: form.placeLabel || null,
        gender: form.gender,
        education_system: form.educationSystem,
        student_preference: {
          interested_in: splitCsv(form.interestedIn),
          already_excel_at: splitCsv(form.excelAt),
          financial_constraints: form.financialConstraints,
          risk_appetite: form.riskAppetite,
        },
      };

      const { session, persisted } = await saveAndGenerateCharts({
        userId,
        userInfo,
        birthInput,
        studentContext,
        onProgress: setProgress,
      });

      if (persisted) {
        toast.success("Charts saved & generated", {
          description: `Chart ${session.chartId} · user ${session.userId}`,
        });
      } else {
        toast.success("Charts generated (session only)", {
          description:
            "DynamoDB not configured on API — charts computed but not persisted. Set DYNAMODB_TABLE_NAME on Render to enable save.",
        });
      }
      nav({ to: "/charts" });
    } catch (err: unknown) {
      toast.error("Pipeline failed", { description: String((err as Error)?.message ?? err) });
    } finally {
      setSaving(false);
      setProgress("");
    }
  };

  return (
    <div>
      <PageHeader
        title="Birth Data"
        subtitle="Enter birth details once — save and all charts load from the PyJHora backend automatically."
      />
      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Native details</CardTitle>
          <CardDescription>
            Geocoding uses the same API as the legacy chart tool. No separate fetch/save buttons needed.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-6">
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <Label>Display name</Label>
                <Input
                  value={form.displayName}
                  onChange={(e) => update("displayName", e.target.value)}
                  required
                  placeholder="As per records"
                />
              </div>
              <div className="sm:col-span-2">
                <Label>Email (optional)</Label>
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => update("email", e.target.value)}
                  placeholder="you@example.com"
                />
              </div>
              <div>
                <Label>Date of birth</Label>
                <Input type="date" value={form.date} onChange={(e) => update("date", e.target.value)} required />
              </div>
              <div>
                <Label>Time of birth (to the second)</Label>
                <Input
                  type="time"
                  step={1}
                  value={form.time}
                  onChange={(e) => update("time", e.target.value)}
                  required
                />
              </div>
              <div className="sm:col-span-2">
                <Label>Location (city / town)</Label>
                <PlaceAutocomplete
                  value={form.locationQuery}
                  onChange={(v) => update("locationQuery", v)}
                  onResolved={(geo) => applyGeocode(geo)}
                />
              </div>
              <div className="sm:col-span-2">
                <Label>Place label</Label>
                <Input value={form.placeLabel} onChange={(e) => update("placeLabel", e.target.value)} />
              </div>
              <div>
                <Label>Latitude</Label>
                <Input
                  type="number"
                  step="any"
                  value={form.latitude}
                  onChange={(e) => update("latitude", e.target.value)}
                  required
                />
              </div>
              <div>
                <Label>Longitude</Label>
                <Input
                  type="number"
                  step="any"
                  value={form.longitude}
                  onChange={(e) => update("longitude", e.target.value)}
                  required
                />
              </div>
              <div className="sm:col-span-2">
                <Label>Timezone (hours east of UTC, e.g. India 5.5)</Label>
                <Input
                  type="number"
                  step="any"
                  value={form.timezoneOffsetHours}
                  onChange={(e) => update("timezoneOffsetHours", e.target.value)}
                  required
                />
              </div>
              <div>
                <Label>Ayanamsa</Label>
                <Select value={form.ayanamsa} onValueChange={(v) => update("ayanamsa", v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {AYANAMSA_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-3 justify-end">
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={form.useTrueNodes}
                    onCheckedChange={(c) => update("useTrueNodes", !!c)}
                  />
                  Use true nodes
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={form.includeOuterPlanets}
                    onCheckedChange={(c) => update("includeOuterPlanets", !!c)}
                  />
                  Include Uranus–Pluto
                </label>
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <p className="text-sm font-medium mb-3">Student context (for consolidated export)</p>
              <div className="grid sm:grid-cols-3 gap-4">
                <div>
                  <Label>Gender</Label>
                  <Select value={form.gender} onValueChange={(v) => update("gender", v as "M" | "F" | "O")}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="M">M</SelectItem>
                      <SelectItem value="F">F</SelectItem>
                      <SelectItem value="O">O</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Education system</Label>
                  <Input
                    value={form.educationSystem}
                    onChange={(e) => update("educationSystem", e.target.value)}
                  />
                </div>
                <div>
                  <Label>Risk appetite</Label>
                  <Select
                    value={form.riskAppetite}
                    onValueChange={(v) => update("riskAppetite", v as "LOW" | "MODERATE" | "HIGH")}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="LOW">LOW</SelectItem>
                      <SelectItem value="MODERATE">MODERATE</SelectItem>
                      <SelectItem value="HIGH">HIGH</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="sm:col-span-3">
                  <Label>Interested in</Label>
                  <Input
                    value={form.interestedIn}
                    onChange={(e) => update("interestedIn", e.target.value)}
                    placeholder="comma separated, e.g. CS, Mathematics"
                  />
                </div>
                <div className="sm:col-span-3">
                  <Label>Already excels at</Label>
                  <Input
                    value={form.excelAt}
                    onChange={(e) => update("excelAt", e.target.value)}
                    placeholder="comma separated, e.g. Physics, Drawing"
                  />
                </div>
                <label className="flex items-center gap-2 text-sm sm:col-span-3">
                  <Checkbox
                    checked={form.financialConstraints}
                    onCheckedChange={(c) => update("financialConstraints", !!c)}
                  />
                  Financial constraints
                </label>
              </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <Button type="submit" disabled={saving} className="gradient-gold text-primary-foreground">
                {saving ? "Generating…" : "Save & generate charts"}
              </Button>
              <Button type="button" variant="outline" onClick={() => nav({ to: "/prashna" })}>
                Skip — use Prashna mode instead
              </Button>
              {progress && <span className="text-xs text-muted-foreground">{progress}</span>}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
