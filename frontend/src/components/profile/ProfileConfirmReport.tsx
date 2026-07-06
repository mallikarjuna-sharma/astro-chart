import type { ReactNode } from "react";
import type { CareerContextInput } from "@/lib/pyjhora/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type BasicForm = {
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
  gender: string;
  educationSystem: string;
  riskAppetite: string;
  interestedIn: string;
  excelAt: string;
  financialConstraints: boolean;
  notes: string;
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-1 py-2 border-b border-border/60 last:border-0">
      <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
      <dd className="sm:col-span-2 text-sm break-words">{value || "—"}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl>{children}</dl>
      </CardContent>
    </Card>
  );
}

export function ProfileConfirmReport({
  form,
  careerContext,
  accountEmail,
}: {
  form: BasicForm;
  careerContext: CareerContextInput;
  accountEmail?: string;
}) {
  return (
    <div className="space-y-4">
      <Card className="border-gold/30 bg-gold/5">
        <CardHeader>
          <CardTitle>Confirm profile details</CardTitle>
          <CardDescription>
            Review everything below. On confirm we compute charts and analyses once, save them to
            your account, and reuse this data when you open the profile — no recalculation.
          </CardDescription>
        </CardHeader>
      </Card>

      <Section title="1. Basic details">
        <Row label="Profile name" value={form.profileName} />
        <Row label="Account email" value={accountEmail ?? ""} />
        <Row label="Date of birth" value={form.date} />
        <Row label="Time of birth" value={form.time} />
        <Row label="Place" value={form.placeLabel} />
        <Row label="Coordinates" value={`${form.latitude}, ${form.longitude}`} />
        <Row label="Timezone offset" value={`${form.timezoneOffsetHours} hours`} />
        <Row label="Ayanamsa" value={form.ayanamsa} />
        <Row label="True nodes" value={form.useTrueNodes ? "Yes" : "No"} />
        <Row label="Outer planets" value={form.includeOuterPlanets ? "Yes" : "No"} />
      </Section>

      <Section title="2. Career field (student context)">
        <Row label="Gender" value={form.gender} />
        <Row label="Education system" value={form.educationSystem} />
        <Row label="Risk appetite" value={form.riskAppetite} />
        <Row label="Interested in" value={form.interestedIn} />
        <Row label="Excel at" value={form.excelAt} />
        <Row label="Financial constraints" value={form.financialConstraints ? "Yes" : "No"} />
        <Row label="Notes" value={form.notes} />
      </Section>

      <Section title="3. Job analysis (career context)">
        <Row label="Employment" value={careerContext.employment_status} />
        <Row label="Designation" value={careerContext.designation ?? ""} />
        <Row label="Years experience" value={String(careerContext.years_experience ?? "")} />
        <Row label="Company type" value={careerContext.company_type ?? ""} />
        <Row label="Industry" value={careerContext.industry_sector ?? ""} />
        <Row label="Desired outcome" value={careerContext.desired_outcome ?? ""} />
        <Row label="Join date" value={careerContext.join_date ?? ""} />
        <Row label="Last promotion" value={careerContext.last_promotion_date ?? ""} />
        <Row label="Geographic preference" value={careerContext.geographic_preference ?? ""} />
        <Row
          label="Actively looking"
          value={careerContext.actively_looking ? "Yes" : "No"}
        />
        <Row label="Notice period" value={careerContext.on_notice_period ? "Yes" : "No"} />
      </Section>
    </div>
  );
}
