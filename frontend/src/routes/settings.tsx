import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { ComingSoonModal } from "@/components/ComingSoonModal";
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
  const [language] = useState("English");
  const [whatsapp, setWhatsapp] = useState(true);
  const [emailDigest, setEmailDigest] = useState(true);
  const [comingSoonOpen, setComingSoonOpen] = useState(false);

  const save = () => {
    persistUserProfile({
      display_name: displayName,
      email: email || null,
      location_query: useUserStore.getState().locationQuery || null,
      phone: useUserStore.getState().phone || null,
      notes: useUserStore.getState().notes || null,
    });
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
              <Select value={language}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="English">English</SelectItem>
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
            <Button variant="outline" onClick={() => setComingSoonOpen(true)}>Compare plans</Button>
            <Button variant="outline" onClick={() => setComingSoonOpen(true)}>Manage billing</Button>
            <Button variant="destructive" onClick={() => setComingSoonOpen(true)}>Cancel subscription</Button>
          </CardContent>
        </Card>
      </div>

      <ComingSoonModal
        open={comingSoonOpen}
        onOpenChange={setComingSoonOpen}
        title="Subscription management"
        description="Plan comparison, billing, and subscription changes are coming soon."
      />
    </div>
  );
}
