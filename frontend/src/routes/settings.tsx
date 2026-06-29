import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useState } from "react";
import { toast } from "sonner";
import { useUserStore } from "@/stores/user-store";
import { persistUserProfile } from "@/lib/pyjhora/session";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings — JyotishAI" }] }),
  component: SettingsPage,
});

function SettingsPage() {
  const displayName = useUserStore((s) => s.displayName);
  const email = useUserStore((s) => s.email);
  const setProfile = useUserStore((s) => s.setProfile);
  const [language, setLanguage] = useState("English");
  const [whatsapp, setWhatsapp] = useState(true);
  const [emailDigest, setEmailDigest] = useState(true);

  const save = () => {
    persistUserProfile(displayName, email, useUserStore.getState().locationQuery);
    toast.success("Profile saved");
  };

  return (
    <div>
      <PageHeader title="Settings" subtitle="Profile, notifications, defaults." />
      <div className="grid lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle>Profile</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div><Label>Name</Label><Input value={displayName} onChange={(e) => setProfile({ displayName: e.target.value })} /></div>
            <div><Label>Email</Label><Input value={email} onChange={(e) => setProfile({ email: e.target.value })} /></div>
            <Button onClick={save} className="gradient-gold text-primary-foreground">Save profile</Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Preferences</CardTitle><CardDescription>Defaults for analysis & reports.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Report language</Label>
              <Select value={language} onValueChange={setLanguage}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["English","Hindi","Tamil","Telugu","Kannada","Malayalam"].map((l)=>(<SelectItem key={l} value={l}>{l}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <Label>WhatsApp notifications</Label>
              <Switch checked={whatsapp} onCheckedChange={setWhatsapp} />
            </div>
            <div className="flex items-center justify-between">
              <Label>Weekly email digest</Label>
              <Switch checked={emailDigest} onCheckedChange={setEmailDigest} />
            </div>
            <Button onClick={save} variant="outline">Save preferences</Button>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Subscription</CardTitle><CardDescription>Professional plan · renews 2026-12-01.</CardDescription></CardHeader>
          <CardContent className="flex gap-2">
            <Button variant="outline" onClick={() => toast("Plan compare opened")}>Compare plans</Button>
            <Button variant="outline" onClick={() => toast("Billing portal opened")}>Manage billing</Button>
            <Button variant="destructive" onClick={() => toast("Subscription will cancel at period end")}>Cancel subscription</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
