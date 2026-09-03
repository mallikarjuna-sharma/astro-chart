import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Loader2, Plus, ArrowLeft, UserRound, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { PlaceAutocomplete } from "@/components/charts/PlaceAutocomplete";
import {
  CareerContextForm,
  defaultCareerContext,
  defaultYearsExperience,
} from "@/components/career/CareerContextForm";
import { profilesApi } from "@/lib/profiles/client";
import { restoreProfileToChartSession, isProfileSessionReady } from "@/lib/profiles/restore-session";
import { ProfileConfirmReport } from "@/components/profile/ProfileConfirmReport";
import type { ProfileSummary } from "@/lib/profiles/types";
import {
  buildBirthInput,
  buildUserInfoFromForm,
  parseBirthDateTime,
  saveChartSession,
  studentContextFromUserInfo,
} from "@/lib/pyjhora";
import type { CareerContextInput, GeocodeResponse } from "@/lib/pyjhora/types";
import { useAuthStore, useIsAuthenticated } from "@/stores/auth-store";
import { useProfileStore } from "@/stores/profile-store";
import { useChartSessionStore } from "@/stores/chart-session-store";
import { cn } from "@/lib/utils";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

type View = "list" | "create" | "confirm";

const AYANAMSA_OPTIONS = [
  { value: "LAHIRI", label: "Lahiri (Chitrapaksha)" },
  { value: "KP", label: "KP (Krishnamurti)" },
  { value: "RAMAN", label: "Raman" },
];

type FormState = {
  profileName: string;
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
  notes: string;
};

const defaultForm = (): FormState => ({
  profileName: "",
  date: "2008-11-16",
  time: "06:01:00",
  placeLabel: "Srirangam, Tiruchirappalli, Tamil Nadu, India",
  latitude: "10.8655",
  longitude: "78.6882",
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
  notes: "",
});

function ageFromDate(date: string): number | null {
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  return (now.getTime() - d.getTime()) / (365.25 * 24 * 3600 * 1000);
}

function ProfileSection({
  step,
  title,
  description,
  children,
  className,
}: {
  step: number;
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("flex flex-col h-full", className)}>
      <CardHeader className="pb-4 space-y-3">
        <div className="flex items-start gap-3">
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-gold/30 bg-gold/10 text-sm font-semibold text-gold"
            aria-hidden
          >
            {step}
          </span>
          <div className="min-w-0">
            <CardTitle className="text-lg leading-tight">{title}</CardTitle>
            {description ? (
              <CardDescription className="mt-1">{description}</CardDescription>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 space-y-4">{children}</CardContent>
    </Card>
  );
}

export function ProfileWizard() {
  const navigate = useNavigate();
  const isAuthenticated = useIsAuthenticated();
  const authUser = useAuthStore((s) => s.user);
  const profiles = useProfileStore((s) => s.profiles);
  const maxProfiles = useProfileStore((s) => s.maxProfiles);
  const fetchProfiles = useProfileStore((s) => s.fetchProfiles);
  const setActiveProfileId = useProfileStore((s) => s.setActiveProfileId);

  const [view, setView] = useState<View>("list");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [form, setForm] = useState<FormState>(defaultForm);
  const [careerContext, setCareerContext] = useState<CareerContextInput>(() =>
    defaultCareerContext(ageFromDate(defaultForm().date)),
  );
  const [deleteTarget, setDeleteTarget] = useState<ProfileSummary | null>(null);

  const update = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const currentAge = ageFromDate(form.date);

  useEffect(() => {
    if (!isAuthenticated) return;
    // Cached in the profile store — only calls the API on first load or when
    // the signed-in user changes. Create/delete force a refresh explicitly.
    void fetchProfiles(authUser?.user_id ?? null).catch((err) =>
      toast.error(err instanceof Error ? err.message : String(err)),
    );
  }, [isAuthenticated, authUser?.user_id, fetchProfiles]);

  useEffect(() => {
    const years = defaultYearsExperience(ageFromDate(form.date));
    setCareerContext((prev) =>
      prev.years_experience === years ? prev : { ...prev, years_experience: years },
    );
  }, [form.date]);

  const startCreate = () => {
    const fresh = defaultForm();
    setForm(fresh);
    setCareerContext(defaultCareerContext(ageFromDate(fresh.date)));
    setView("create");
  };

  const applyGeocode = (geo: GeocodeResponse, description?: string) => {
    const label = description || geo.place_label;
    update("placeLabel", label);
    update("latitude", String(geo.latitude));
    update("longitude", String(geo.longitude));
    if (geo.timezone_offset_hours != null) {
      update("timezoneOffsetHours", String(geo.timezone_offset_hours));
    }
  };

  const loadProfile = async (profileId: string) => {
    const session = useChartSessionStore.getState().session;
    if (isProfileSessionReady(profileId, session)) {
      setActiveProfileId(profileId);
      navigate({ to: "/charts" });
      return;
    }

    setLoading(true);
    setProgress("Loading profile charts…");
    try {
      const profile = await profilesApi.get(profileId);
      const fullSession = await restoreProfileToChartSession(profile, setProgress);
      saveChartSession(fullSession);
      setActiveProfileId(profileId);
      toast.success(`Loaded profile: ${profile.profile_name}`);
      navigate({ to: "/charts" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load profile");
    } finally {
      setLoading(false);
      setProgress("");
    }
  };

  const deleteProfile = async (profile: ProfileSummary) => {
    setLoading(true);
    try {
      await profilesApi.delete(profile.profile_id);
      await fetchProfiles(authUser?.user_id ?? null, { force: true });
      if (useProfileStore.getState().activeProfileId === profile.profile_id) {
        setActiveProfileId(null);
      }
      toast.success(`Deleted profile: ${profile.profile_name}`);
      setDeleteTarget(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete profile");
    } finally {
      setLoading(false);
    }
  };

  const submitProfile = async () => {
    if (!form.profileName.trim()) {
      toast.error("Profile name is required");
      return;
    }
    setLoading(true);
    setProgress("Computing and saving charts & analyses…");
    try {
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

      const userInfo = buildUserInfoFromForm({
        displayName: form.profileName,
        email: authUser?.email ?? "",
        phone: "",
        placeLabel: form.placeLabel,
        notes: form.notes,
        gender: form.gender,
        educationSystem: form.educationSystem,
        riskAppetite: form.riskAppetite,
        interestedIn: form.interestedIn,
        excelAt: form.excelAt,
        financialConstraints: form.financialConstraints,
      });
      const studentContext = studentContextFromUserInfo(userInfo, form.placeLabel);

      const profile = await profilesApi.create({
        profile_name: form.profileName.trim(),
        birth_input: birthInput,
        user_info: userInfo,
        student_context: studentContext,
        career_context: careerContext,
      });

      setProgress("Loading saved profile…");
      const session = restoreProfileToChartSession(profile, setProgress);
      saveChartSession(session);
      setActiveProfileId(profile.profile_id);
      await fetchProfiles(authUser?.user_id ?? null, { force: true });
      toast.success("Profile created", {
        description: `${profile.profile_name} — all details saved to your account.`,
      });
      navigate({ to: "/charts" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Profile creation failed");
    } finally {
      setLoading(false);
      setProgress("");
    }
  };

  if (view === "list") {
    const canCreate = profiles.length < maxProfiles;
    return (
      <div className="space-y-6 max-w-3xl">
        <Card>
          <CardHeader>
            <CardTitle>Your profiles</CardTitle>
            <CardDescription>
              {profiles.length} of {maxProfiles} profiles used. Saved profiles are read-only and loaded from the database.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {profiles.length === 0 && (
              <p className="text-sm text-muted-foreground">No profiles yet. Create your first birth profile below.</p>
            )}
            {profiles.map((p) => (
              <div
                key={p.profile_id}
                className="flex items-center justify-between gap-3 p-3 rounded-lg border border-border hover:bg-muted/40"
              >
                <div className="min-w-0">
                  <div className="font-medium truncate">{p.profile_name}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {p.birth_local || p.place_label}
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" variant="outline" disabled={loading} onClick={() => void loadProfile(p.profile_id)}>
                    Open
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-destructive hover:text-destructive"
                    disabled={loading}
                    onClick={() => setDeleteTarget(p)}
                  >
                    <Trash2 className="w-4 h-4" />
                    <span className="sr-only">Delete</span>
                  </Button>
                </div>
              </div>
            ))}
            {canCreate && (
              <Button className="w-full gradient-gold text-primary-foreground" onClick={startCreate}>
                <Plus className="w-4 h-4 mr-2" /> Create new profile
              </Button>
            )}
          </CardContent>
        </Card>

        <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete profile?</AlertDialogTitle>
              <AlertDialogDescription>
                This permanently removes <strong>{deleteTarget?.profile_name}</strong> and all saved chart data.
                This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={loading}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                disabled={loading}
                onClick={(e) => {
                  e.preventDefault();
                  if (deleteTarget) void deleteProfile(deleteTarget);
                }}
              >
                {loading ? "Deleting…" : "Delete"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  }

  if (view === "confirm") {
    return (
      <div className="max-w-3xl mx-auto space-y-6 pb-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button variant="ghost" size="sm" disabled={loading} onClick={() => setView("create")}>
            <ArrowLeft className="w-4 h-4 mr-1" /> Edit details
          </Button>
          {progress ? <p className="text-sm text-gold">{progress}</p> : null}
        </div>

        <ProfileConfirmReport
          form={form}
          careerContext={careerContext}
          accountEmail={authUser?.email}
        />

        <Card className="border-gold/20">
          <CardContent className="flex flex-col sm:flex-row sm:justify-end gap-3 py-4">
            <Button variant="outline" disabled={loading} onClick={() => setView("create")}>
              Back to edit
            </Button>
            <Button
              className="gradient-gold text-primary-foreground"
              disabled={loading}
              onClick={() => void submitProfile()}
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving profile…
                </>
              ) : (
                "Confirm & save profile"
              )}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" size="sm" disabled={loading} onClick={() => setView("list")}>
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to profiles
        </Button>
        {progress ? <p className="text-sm text-gold">{progress}</p> : null}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        <ProfileSection
          step={1}
          title="Basic details"
          description="Profile name and birth data for chart calculation."
        >
          <div>
            <Label>Profile name</Label>
            <Input
              placeholder="Shiva ramakrishanan"
              value={form.profileName}
              onChange={(e) => update("profileName", e.target.value)}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label>Date of birth</Label>
              <Input type="date" value={form.date} onChange={(e) => update("date", e.target.value)} />
            </div>
            <div>
              <Label>Time of birth</Label>
              <Input type="time" step={1} value={form.time} onChange={(e) => update("time", e.target.value)} />
            </div>
          </div>
          <div>
            <Label>Place of birth</Label>
            <PlaceAutocomplete
              value={form.placeLabel}
              onResolved={applyGeocode}
              onChange={(v) => update("placeLabel", v)}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div><Label>Latitude</Label><Input value={form.latitude} onChange={(e) => update("latitude", e.target.value)} /></div>
            <div><Label>Longitude</Label><Input value={form.longitude} onChange={(e) => update("longitude", e.target.value)} /></div>
            <div><Label>TZ offset (hrs)</Label><Input value={form.timezoneOffsetHours} onChange={(e) => update("timezoneOffsetHours", e.target.value)} /></div>
          </div>
          <div>
            <Label>Ayanamsa</Label>
            <Select value={form.ayanamsa} onValueChange={(v) => update("ayanamsa", v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {AYANAMSA_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={form.useTrueNodes} onCheckedChange={(c) => update("useTrueNodes", !!c)} />
              True nodes
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={form.includeOuterPlanets} onCheckedChange={(c) => update("includeOuterPlanets", !!c)} />
              Outer planets
            </label>
          </div>
        </ProfileSection>

        <ProfileSection
          step={2}
          title="Career field"
          description="Student context used for education and field recommendations."
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 gap-3">
            <div>
              <Label>Gender</Label>
              <Select value={form.gender} onValueChange={(v) => update("gender", v as "M" | "F")}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="M">Male</SelectItem>
                  <SelectItem value="F">Female</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Education system</Label>
              <Input value={form.educationSystem} onChange={(e) => update("educationSystem", e.target.value)} />
            </div>
          </div>
          <div>
            <Label>Risk appetite</Label>
            <Select value={form.riskAppetite} onValueChange={(v) => update("riskAppetite", v as FormState["riskAppetite"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {["LOW", "MODERATE", "HIGH"].map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Interested in (comma-separated)</Label>
            <Input value={form.interestedIn} onChange={(e) => update("interestedIn", e.target.value)} />
          </div>
          <div>
            <Label>Already excel at</Label>
            <Input value={form.excelAt} onChange={(e) => update("excelAt", e.target.value)} />
          </div>
          <div>
            <Label>Notes</Label>
            <Textarea value={form.notes} onChange={(e) => update("notes", e.target.value)} rows={2} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={form.financialConstraints} onCheckedChange={(c) => update("financialConstraints", !!c)} />
            Financial constraints
          </label>
        </ProfileSection>

        <ProfileSection
          step={3}
          title="Job analysis"
          description={
            currentAge != null
              ? `Career context for timeline analysis (age ${currentAge.toFixed(1)}).`
              : "Career context for timeline analysis."
          }
        >
          <CareerContextForm
            embedded
            value={careerContext}
            onChange={setCareerContext}
            currentAge={currentAge}
          />
        </ProfileSection>
      </div>

      <Card className="border-gold/20 bg-muted/20">
        <CardContent className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 py-4">
          <p className="text-sm text-muted-foreground">
            Review your inputs on the next step. Charts are computed once on confirm and saved with your details. Career and education reports run when you open those pages.
          </p>
          <Button
            className="gradient-gold text-primary-foreground shrink-0 w-full sm:w-auto"
            disabled={loading || !form.profileName.trim()}
            onClick={() => setView("confirm")}
          >
            <UserRound className="w-4 h-4 mr-2" />
            Review & confirm
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
