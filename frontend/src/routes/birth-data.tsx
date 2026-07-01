import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { useState, useEffect } from "react";
import { Loader2, Download } from "lucide-react";
import { toast } from "sonner";
import { PlaceAutocomplete } from "@/components/charts/PlaceAutocomplete";
import {
  buildBirthInput,
  buildUserInfoFromForm,
  fetchAndRestoreCharts,
  formFieldsFromSaved,
  parseBirthDateTime,
  persistUserProfile,
  saveAndGenerateCharts,
  studentContextFromUserInfo,
  ensureUserId,
  PYJHORA_LS_USER,
} from "@/lib/pyjhora";
import type { GeocodeResponse } from "@/lib/pyjhora/types";
import type { UserProfile } from "@/stores/user-store";
import { useUserStore } from "@/stores/user-store";

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

type FormState = {
  displayName: string;
  email: string;
  phone: string;
  notes: string;
  date: string;
  time: string;
  placeLabel: string;
  latitude: string;
  longitude: string;
  timezoneOffsetHours: string;
  ayanamsa: string;
  useTrueNodes: boolean;
  includeOuterPlanets: boolean;
  gender: "M" | "F";
  educationSystem: string;
  riskAppetite: "LOW" | "MODERATE" | "HIGH";
  interestedIn: string;
  excelAt: string;
  financialConstraints: boolean;
};

function defaultForm(stored: {
  displayName: string;
  email: string;
  phone: string;
  locationQuery: string;
  notes: string;
}): FormState {
  return {
    displayName: stored.displayName || "Demo user",
    email: stored.email,
    phone: stored.phone,
    notes: stored.notes,
    date: "2014-08-10",
    time: "13:00:00",
    placeLabel:
      stored.locationQuery || "Srirangam, Tiruchirappalli, Tamil Nadu, India",
    latitude: "10.8627",
    longitude: "78.6928",
    timezoneOffsetHours: "5.5",
    ayanamsa: "LAHIRI",
    useTrueNodes: false,
    includeOuterPlanets: false,
    gender: "M",
    educationSystem: "India_CBSE",
    riskAppetite: "MODERATE",
    interestedIn: "",
    excelAt: "",
    financialConstraints: false,
  };
}

function BirthDataPage() {
  const nav = useNavigate();
  const [saving, setSaving] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [progress, setProgress] = useState("");

  const storedDisplayName = useUserStore((s) => s.displayName);
  const storedEmail = useUserStore((s) => s.email);
  const storedPhone = useUserStore((s) => s.phone);
  const storedLocationQuery = useUserStore((s) => s.locationQuery);
  const storedNotes = useUserStore((s) => s.notes);
  const storedUserId = useUserStore((s) => s.userId);
  const setProfile = useUserStore((s) => s.setProfile);
  const setUserId = useUserStore((s) => s.setUserId);

  const [userId, setUserIdInput] = useState(
    () => storedUserId || (typeof window !== "undefined" ? localStorage.getItem(PYJHORA_LS_USER) : null) || "",
  );

  const [form, setForm] = useState<FormState>(() =>
    defaultForm({
      displayName: storedDisplayName,
      email: storedEmail,
      phone: storedPhone,
      locationQuery: storedLocationQuery,
      notes: storedNotes,
    }),
  );

  const update = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (storedDisplayName || storedEmail || storedPhone || storedLocationQuery || storedNotes) {
      setForm((f) => ({
        ...f,
        displayName: storedDisplayName || f.displayName,
        email: storedEmail || f.email,
        phone: storedPhone || f.phone,
        notes: storedNotes || f.notes,
        placeLabel: storedLocationQuery || f.placeLabel,
      }));
    }
  }, [storedDisplayName, storedEmail, storedPhone, storedLocationQuery, storedNotes]);

  useEffect(() => {
    if (storedUserId && !userId) {
      setUserIdInput(storedUserId);
    }
  }, [storedUserId, userId]);

  const syncProfileFields = (patch: Partial<UserProfile>) => {
    setProfile(patch);
  };

  const applyFormFromSaved = (fields: ReturnType<typeof formFieldsFromSaved>) => {
    setForm((f) => ({ ...f, ...fields }));
    syncProfileFields({
      displayName: fields.displayName,
      email: fields.email,
      phone: fields.phone,
      locationQuery: fields.placeLabel,
      notes: fields.notes,
    });
  };

  const applyGeocode = (geo: GeocodeResponse, description?: string) => {
    const label = description || geo.place_label;
    setForm((f) => ({
      ...f,
      placeLabel: label,
      latitude: String(geo.latitude),
      longitude: String(geo.longitude),
      timezoneOffsetHours:
        geo.timezone_offset_hours != null
          ? String(geo.timezone_offset_hours)
          : f.timezoneOffsetHours,
    }));
    syncProfileFields({ locationQuery: label });
  };

  const resolveUserId = () => {
    const id = userId.trim() || ensureUserId(localStorage.getItem(PYJHORA_LS_USER) ?? undefined);
    localStorage.setItem(PYJHORA_LS_USER, id);
    setUserIdInput(id);
    setUserId(id);
    return id;
  };

  const handleFetch = async () => {
    const id = userId.trim();
    if (!id) {
      toast.error("Enter your user ID to fetch saved details");
      return;
    }

    setFetching(true);
    setProgress("Fetching from database…");
    try {
      const { session, chartId } = await fetchAndRestoreCharts({
        userId: id,
        onProgress: setProgress,
      });

      applyFormFromSaved(formFieldsFromSaved(session.userInfo, session.birthInput));
      setUserId(id);
      setUserIdInput(id);

      toast.success("Profile loaded", {
        description: `Chart ${chartId} · ${session.userInfo.display_name}`,
      });
      nav({ to: "/charts" });
    } catch (err: unknown) {
      toast.error("Fetch failed", { description: String((err as Error)?.message ?? err) });
    } finally {
      setFetching(false);
      setProgress("");
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
      const resolvedUserId = resolveUserId();
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

      const userInfo = buildUserInfoFromForm(form);
      persistUserProfile(userInfo, resolvedUserId);
      syncProfileFields({ locationQuery: form.placeLabel });
      const studentContext = studentContextFromUserInfo(userInfo, form.placeLabel || "");

      const { session, persisted } = await saveAndGenerateCharts({
        userId: resolvedUserId,
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

  const busy = saving || fetching;

  return (
    <div>
      <PageHeader
        title="Birth Data"
        subtitle="Enter birth details once — save and all charts load from the PyJHora backend automatically."
      />
      <Card className="max-w-3xl mb-6">
        <CardHeader>
          <CardTitle>Your user ID</CardTitle>
          <CardDescription>
            Save this ID to retrieve your birth chart and profile from any device. Use Fetch to load your
            latest saved chart from the database.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <Label htmlFor="user-id">User ID</Label>
              <Input
                id="user-id"
                value={userId}
                onChange={(e) => {
                  setUserIdInput(e.target.value);
                  setUserId(e.target.value.trim());
                }}
                placeholder="e.g. user-82eafa62"
                className="font-mono text-sm mt-1"
              />
            </div>
            <div className="flex items-end gap-2">
              <Button type="button" variant="outline" disabled={busy} onClick={() => void handleFetch()}>
                {fetching ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Download className="h-4 w-4 mr-1" />}
                Fetch
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => {
                  const id = ensureUserId(undefined);
                  setUserIdInput(id);
                  setUserId(id);
                  localStorage.setItem(PYJHORA_LS_USER, id);
                  toast.success("New user ID generated", { description: id });
                }}
              >
                New ID
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Native details</CardTitle>
          <CardDescription>
            Profile fields are stored in <code className="text-xs">user_info</code> in DynamoDB when you save.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-6">
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <Label>Display name</Label>
                <Input
                  value={form.displayName}
                  onChange={(e) => {
                    update("displayName", e.target.value);
                    syncProfileFields({ displayName: e.target.value });
                  }}
                  required
                  placeholder="As per records"
                />
              </div>
              <div>
                <Label>Email (optional)</Label>
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => {
                    update("email", e.target.value);
                    syncProfileFields({ email: e.target.value });
                  }}
                  placeholder="you@example.com"
                />
              </div>
              <div>
                <Label>Phone (optional)</Label>
                <Input
                  type="tel"
                  value={form.phone}
                  onChange={(e) => {
                    update("phone", e.target.value);
                    syncProfileFields({ phone: e.target.value });
                  }}
                  placeholder="+91 …"
                />
              </div>
              <div className="sm:col-span-2">
                <Label>Notes (optional)</Label>
                <Textarea
                  value={form.notes}
                  onChange={(e) => {
                    update("notes", e.target.value);
                    syncProfileFields({ notes: e.target.value });
                  }}
                  placeholder="Any context for the astrologer"
                  rows={2}
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
                <Label>Birth place</Label>
                <PlaceAutocomplete
                  value={form.placeLabel}
                  onChange={(v) => update("placeLabel", v)}
                  onResolved={(geo, label) => applyGeocode(geo, label)}
                  placeholder="Search city or town — pick a suggestion to fill coordinates"
                />
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
              <p className="text-sm font-medium mb-3">Student context (stored in user_info)</p>
              <div className="grid sm:grid-cols-3 gap-4">
                <div>
                  <Label>Gender</Label>
                  <Select value={form.gender} onValueChange={(v) => update("gender", v as "M" | "F")}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="M">Male</SelectItem>
                      <SelectItem value="F">Female</SelectItem>
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
              <Button type="submit" disabled={busy} className="gradient-gold text-primary-foreground">
                {saving ? "Generating…" : "Save & generate charts"}
              </Button>
              <Button type="button" variant="outline" onClick={() => nav({ to: "/prashna" })} disabled={busy}>
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
