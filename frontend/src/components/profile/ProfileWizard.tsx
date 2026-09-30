import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Loader2, Plus, ArrowLeft, UserRound, Trash2, Settings2, ChevronRight, ChevronLeft, CheckCircle2 } from "lucide-react";
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
  const activeSession = useChartSessionStore((s) => s.session);
  const currentProfileId = activeSession?.chartId;

  const [view, setView] = useState<View>("list");
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);
  const [showAdvanced, setShowAdvanced] = useState(false);
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
      <div className="max-w-6xl mx-auto space-y-6 animate-in fade-in duration-500">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div className="space-y-1 text-left">
            <h1 className="text-3xl font-bold tracking-tight text-foreground flex items-center gap-2">
              <UserRound className="w-7 h-7 text-gold" />
              Your Profiles
            </h1>
            <p className="text-muted-foreground">
              {profiles.length} of {maxProfiles} profiles used. Saved profiles are read-only and loaded from the database.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-stretch gap-5 pt-4">
          {profiles.length === 0 && !canCreate && (
             <p className="text-sm text-muted-foreground">No profiles yet.</p>
          )}
          
          {profiles.map((p) => {
            const isActive = p.profile_id === currentProfileId;
            return (
              <div
                key={p.profile_id}
                className={cn(
                  "group relative flex flex-col justify-between p-5 rounded-2xl border bg-card hover:bg-muted/20 hover:border-gold/40 hover:shadow-md transition-all duration-300 ease-in-out w-full sm:w-[280px]",
                  isActive ? "border-gold bg-gold/5 shadow-sm" : "border-border/60"
                )}
              >
              <div className="absolute top-0 right-0 p-3 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-destructive hover:bg-destructive/10 hover:text-destructive rounded-full"
                  disabled={loading}
                  onClick={() => setDeleteTarget(p)}
                >
                  <Trash2 className="w-4 h-4" />
                  <span className="sr-only">Delete</span>
                </Button>
              </div>

              <div className="min-w-0 mb-6 pr-8">
                <div className="font-semibold text-lg text-foreground truncate mb-1 flex items-center gap-2">
                  {p.profile_name}
                  {isActive && (
                    <span className="text-[10px] uppercase font-bold tracking-wider text-gold bg-gold/10 px-1.5 py-0.5 rounded-sm">
                      Active
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground line-clamp-2">
                  {p.birth_local || p.place_label}
                </div>
              </div>
              
              <div className="mt-auto pt-4 border-t border-border/40">
                <Button 
                  className={cn(
                    "w-full transition-colors rounded-xl h-10",
                    isActive
                      ? "bg-gold text-primary-foreground hover:bg-gold/90 shadow-sm font-semibold"
                      : "bg-gold/10 text-gold hover:bg-gold hover:text-primary-foreground"
                  )}
                  disabled={loading} 
                  onClick={() => void loadProfile(p.profile_id)}
                >
                  {isActive ? "View Charts" : "Open Analysis"}
                </Button>
              </div>
            </div>
            );
          })}

          {canCreate && (
            <button
              onClick={startCreate}
              className="group flex flex-col items-center justify-center p-5 rounded-2xl border-2 border-dashed border-border hover:border-gold/50 bg-transparent hover:bg-gold/5 transition-all duration-300 ease-in-out w-full sm:w-[280px] min-h-[160px]"
            >
              <div className="h-10 w-10 rounded-full bg-gold/10 flex items-center justify-center mb-3 group-hover:bg-gold group-hover:scale-110 transition-all duration-300">
                <Plus className="w-5 h-5 text-gold group-hover:text-primary-foreground" />
              </div>
              <span className="font-medium text-muted-foreground group-hover:text-foreground transition-colors">
                Create New Profile
              </span>
            </button>
          )}
        </div>

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
      <div className="max-w-6xl mx-auto space-y-6 pb-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button 
            variant="outline" 
            size="sm" 
            className="rounded-full border-border/50 bg-background hover:bg-gold/10 hover:text-gold hover:border-gold/30 transition-colors shadow-sm"
            disabled={loading} 
            onClick={() => setView("create")}
          >
            <ArrowLeft className="w-4 h-4 mr-1.5" /> Edit details
          </Button>
          {progress ? <p className="text-sm text-gold">{progress}</p> : null}
        </div>

        <div className="max-w-3xl mx-auto space-y-6">
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
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-12 animate-in fade-in duration-500">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button 
          variant="outline" 
          size="sm" 
          className="rounded-full border-border/50 bg-background hover:bg-gold/10 hover:text-gold hover:border-gold/30 transition-colors shadow-sm"
          disabled={loading} 
          onClick={() => setView("list")}
        >
          <ArrowLeft className="w-4 h-4 mr-1.5" /> Back to profiles
        </Button>
        {progress ? <p className="text-sm text-gold">{progress}</p> : null}
      </div>

      <div className="max-w-3xl mx-auto space-y-8">
        <div className="flex items-center justify-between mb-8 relative px-4 sm:px-12">
          <div className="absolute left-4 right-4 sm:left-12 sm:right-12 top-1/2 -translate-y-1/2 h-1 bg-border/50 z-0 rounded-full" />
          <div 
            className="absolute left-4 sm:left-12 top-1/2 -translate-y-1/2 h-1 bg-gold z-0 rounded-full transition-all duration-500"
            style={{ width: currentStep === 1 ? '0%' : currentStep === 2 ? '50%' : '100%' }}
          />
          
          {[1, 2, 3].map((step) => (
            <div key={step} className="relative z-10 flex flex-col items-center gap-2">
              <div 
                className={cn(
                  "w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold border-2 transition-colors duration-300",
                  currentStep > step 
                    ? "bg-gold border-gold text-primary-foreground" 
                    : currentStep === step 
                      ? "bg-background border-gold text-gold"
                      : "bg-background border-border text-muted-foreground"
                )}
              >
                {currentStep > step ? <CheckCircle2 className="w-5 h-5" /> : step}
              </div>
              <span className={cn(
                "text-xs font-medium absolute -bottom-6 w-24 text-center",
                currentStep >= step ? "text-foreground" : "text-muted-foreground"
              )}>
                {step === 1 ? "Basic Info" : step === 2 ? "Education" : "Career"}
              </span>
            </div>
          ))}
        </div>

        <div className="mt-12 bg-card border border-border/50 rounded-3xl p-6 md:p-8 shadow-sm">
        {currentStep === 1 && (
          <div className="space-y-6 animate-in slide-in-from-right-4 duration-300">
            <div className="space-y-1 mb-6">
              <h2 className="text-2xl font-semibold tracking-tight text-foreground">Basic Details</h2>
              <p className="text-muted-foreground text-sm">Enter the exact birth details to cast the astrological chart.</p>
            </div>
            
            <div className="grid grid-cols-1 gap-5">
              <div>
                <Label>Profile Name</Label>
                <Input
                  placeholder="e.g. Shiva Ramakrishanan"
                  value={form.profileName}
                  onChange={(e) => update("profileName", e.target.value)}
                  className="h-11 mt-1.5"
                />
              </div>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div>
                  <Label>Date of Birth</Label>
                  <Input type="date" value={form.date} onChange={(e) => update("date", e.target.value)} className="h-11 mt-1.5" />
                </div>
                <div>
                  <Label>Time of Birth</Label>
                  <Input type="time" step={1} value={form.time} onChange={(e) => update("time", e.target.value)} className="h-11 mt-1.5" />
                </div>
              </div>
              
              <div>
                <Label>Place of Birth</Label>
                <div className="mt-1.5">
                  <PlaceAutocomplete
                    value={form.placeLabel}
                    onResolved={applyGeocode}
                    onChange={(v) => update("placeLabel", v)}
                  />
                </div>
              </div>
            </div>

            <div className="pt-6 mt-4 border-t border-border/50">
              <Button 
                variant="ghost" 
                size="sm" 
                className="text-muted-foreground mb-4 hover:text-foreground"
                onClick={() => setShowAdvanced(!showAdvanced)}
              >
                <Settings2 className="w-4 h-4 mr-2" />
                {showAdvanced ? "Hide Advanced Settings" : "Show Advanced Settings"}
              </Button>
              
              {showAdvanced && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 p-5 rounded-2xl bg-muted/20 border border-border/50 animate-in fade-in duration-300">
                  <div className="grid grid-cols-2 gap-3 sm:col-span-2">
                    <div><Label>Latitude</Label><Input value={form.latitude} onChange={(e) => update("latitude", e.target.value)} className="mt-1.5" /></div>
                    <div><Label>Longitude</Label><Input value={form.longitude} onChange={(e) => update("longitude", e.target.value)} className="mt-1.5" /></div>
                  </div>
                  <div><Label>TZ offset (hrs)</Label><Input value={form.timezoneOffsetHours} onChange={(e) => update("timezoneOffsetHours", e.target.value)} className="mt-1.5" /></div>
                  <div>
                    <Label>Ayanamsa</Label>
                    <Select value={form.ayanamsa} onValueChange={(v) => update("ayanamsa", v)}>
                      <SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {AYANAMSA_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="sm:col-span-2 flex flex-wrap gap-6 pt-2">
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                      <Checkbox checked={form.useTrueNodes} onCheckedChange={(c) => update("useTrueNodes", !!c)} />
                      Use True Nodes
                    </label>
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                      <Checkbox checked={form.includeOuterPlanets} onCheckedChange={(c) => update("includeOuterPlanets", !!c)} />
                      Include Outer Planets
                    </label>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {currentStep === 2 && (
          <div className="space-y-6 animate-in slide-in-from-right-4 duration-300">
             <div className="space-y-1 mb-6">
              <h2 className="text-2xl font-semibold tracking-tight text-foreground">Education & Interests</h2>
              <p className="text-muted-foreground text-sm">Tell us about your background to tailor field recommendations.</p>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div>
                <Label>Gender</Label>
                <Select value={form.gender} onValueChange={(v) => update("gender", v as "M" | "F")}>
                  <SelectTrigger className="h-11 mt-1.5"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="M">Male</SelectItem>
                    <SelectItem value="F">Female</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Education System</Label>
                <Input value={form.educationSystem} onChange={(e) => update("educationSystem", e.target.value)} className="h-11 mt-1.5" />
              </div>
              <div>
                <Label>Risk Appetite</Label>
                <Select value={form.riskAppetite} onValueChange={(v) => update("riskAppetite", v as FormState["riskAppetite"])}>
                  <SelectTrigger className="h-11 mt-1.5"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["LOW", "MODERATE", "HIGH"].map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="sm:col-span-2">
                <Label>Interested In (comma-separated)</Label>
                <Input value={form.interestedIn} onChange={(e) => update("interestedIn", e.target.value)} placeholder="e.g. Technology, Arts, Management" className="h-11 mt-1.5" />
              </div>
              <div className="sm:col-span-2">
                <Label>Already Excel At</Label>
                <Input value={form.excelAt} onChange={(e) => update("excelAt", e.target.value)} placeholder="e.g. Mathematics, Public Speaking" className="h-11 mt-1.5" />
              </div>
              <div className="sm:col-span-2">
                <Label>Notes</Label>
                <Textarea value={form.notes} onChange={(e) => update("notes", e.target.value)} rows={3} placeholder="Any specific questions or context..." className="mt-1.5" />
              </div>
              <div className="sm:col-span-2 pt-2">
                <label className="flex items-start gap-3 cursor-pointer border border-border/50 p-4 rounded-xl hover:bg-muted/20 transition-colors">
                  <Checkbox className="mt-1" checked={form.financialConstraints} onCheckedChange={(c) => update("financialConstraints", !!c)} />
                  <div className="space-y-1">
                    <p className="font-medium text-sm leading-none">Financial Constraints</p>
                    <p className="text-muted-foreground text-xs">Factor this into education and business predictions.</p>
                  </div>
                </label>
              </div>
            </div>
          </div>
        )}

        {currentStep === 3 && (
          <div className="space-y-6 animate-in slide-in-from-right-4 duration-300">
            <div className="space-y-1 mb-6">
              <h2 className="text-2xl font-semibold tracking-tight text-foreground">Current Job Context</h2>
              <p className="text-muted-foreground text-sm">
                {currentAge != null 
                  ? `Provide your current status for the age ${currentAge.toFixed(1)} career timeline.` 
                  : "Provide your current employment status."}
              </p>
            </div>
            
            <div className="bg-muted/10 p-5 rounded-2xl border border-border/50">
              <CareerContextForm
                embedded
                value={careerContext}
                onChange={setCareerContext}
                currentAge={currentAge}
              />
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between mt-8">
        <Button 
          variant="outline" 
          onClick={() => setCurrentStep((prev) => Math.max(1, prev - 1) as 1|2|3)}
          disabled={currentStep === 1 || loading}
          className="w-28 h-11"
        >
          <ChevronLeft className="w-4 h-4 mr-2" /> Back
        </Button>

        {currentStep < 3 ? (
          <Button 
            className="w-28 h-11 bg-primary hover:bg-primary/90 text-primary-foreground transition-colors"
            onClick={() => setCurrentStep((prev) => Math.min(3, prev + 1) as 1|2|3)}
          >
            Next <ChevronRight className="w-4 h-4 ml-2" />
          </Button>
        ) : (
          <Button
            className="h-11 px-6 gradient-gold text-primary-foreground shadow-md hover:shadow-lg hover:scale-[1.02] transition-all"
            disabled={loading || !form.profileName.trim()}
            onClick={() => setView("confirm")}
          >
            <UserRound className="w-4 h-4 mr-2" />
            Review Details
          </Button>
        )}
      </div>
      </div>
    </div>
  );
}
