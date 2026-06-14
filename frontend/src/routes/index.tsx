import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Compass, BookOpen, ClipboardList, MessageCircleQuestion,
  GraduationCap, LineChart, Bot, Briefcase, Store, Star, ArrowRight,
} from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Dashboard — JyotishAI" },
      { name: "description", content: "Your four-system Vedic intelligence dashboard." },
    ],
  }),
  component: Dashboard,
});

const MODULES = [
  { to: "/kp", icon: Compass, title: "KP Analysis", desc: "Significators, cusp sub-lords, Vimshottari dasha and ruling planets." },
  { to: "/kn-rao", icon: BookOpen, title: "KN Rao + Jaimini", desc: "Chara Karakas, Karakamsa, D10 concordance and Parashari yogas." },
  { to: "/parashari", icon: ClipboardList, title: "Parashari Strength", desc: "Shadbala, Ashtakavarga, Bhava Chalit and Vimshopaka Bala." },
  { to: "/prashna", icon: MessageCircleQuestion, title: "Prashna (Horary)", desc: "Yes / no answers for specific questions — no birth data required." },
  { to: "/confidence", icon: Star, title: "Four-System Score", desc: "Numerical confidence cross-referenced across all four systems." },
  { to: "/student", icon: GraduationCap, title: "Student / Field", desc: "Grade 10–PG field selection with D24 Siddhamsa." },
  { to: "/career-timeline", icon: LineChart, title: "Career Timeline", desc: "Income, job change and growth windows over your life." },
  { to: "/ai", icon: Bot, title: "AI Assistant", desc: "Ask in natural language — answers backed by all four systems." },
  { to: "/workspace", icon: Briefcase, title: "Astrologer Workspace", desc: "Clients, charts, reports, rectification — for practitioners." },
  { to: "/marketplace", icon: Store, title: "Marketplace", desc: "Book verified KP / KN Rao / Parashari / Prashna astrologers." },
];

function Dashboard() {
  return (
    <div>
      <PageHeader
        title="Four systems. One source of clarity."
        subtitle="KP, KN Rao, Parashari and Prashna combined into a measurable confidence score on every recommendation."
        action={
          <Link to="/birth-data">
            <Button className="gradient-gold text-primary-foreground hover:opacity-90">Start with Birth Data <ArrowRight className="w-4 h-4 ml-1" /></Button>
          </Link>
        }
      />

      <div className="grid lg:grid-cols-3 gap-6 mb-8">
        <Card className="lg:col-span-2 bg-card-glass border-gold/30">
          <CardHeader>
            <CardTitle className="text-gradient-gold">Your latest analysis</CardTitle>
            <CardDescription>Career direction · generated 2 hours ago</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col md:flex-row items-center gap-6">
            <ConfidenceBadge score={78} size="lg" />
            <div className="flex-1">
              <p className="text-sm text-foreground/90">
                KP cusp sub-lord, KN Rao Amatyakaraka and Parashari Ashtakavarga align on
                <span className="text-gold font-semibold"> technology + analytical fields</span>.
                Prashna lends partial confirmation. Peak career window
                <span className="text-gold font-semibold"> 2028–2031</span>.
              </p>
              <div className="mt-4 flex gap-2 flex-wrap">
                <Link to="/confidence"><Button size="sm" variant="outline">View score breakdown</Button></Link>
                <Link to="/career-timeline"><Button size="sm" variant="outline">See timeline</Button></Link>
                <Link to="/reports"><Button size="sm" variant="outline">Generate report</Button></Link>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick actions</CardTitle>
            <CardDescription>Common tasks across the platform</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Link to="/prashna"><Button className="w-full justify-start" variant="ghost"><MessageCircleQuestion className="w-4 h-4 mr-2"/> Ask a Prashna question</Button></Link>
            <Link to="/student"><Button className="w-full justify-start" variant="ghost"><GraduationCap className="w-4 h-4 mr-2"/> Student field selection</Button></Link>
            <Link to="/ai"><Button className="w-full justify-start" variant="ghost"><Bot className="w-4 h-4 mr-2"/> Chat with JyotishAI</Button></Link>
            <Link to="/marketplace"><Button className="w-full justify-start" variant="ghost"><Store className="w-4 h-4 mr-2"/> Book an astrologer</Button></Link>
          </CardContent>
        </Card>
      </div>

      <h2 className="text-lg font-semibold mb-3">Explore modules</h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {MODULES.map((m) => {
          const I = m.icon;
          return (
            <Link key={m.to} to={m.to} className="group">
              <Card className="h-full hover:border-gold/60 transition-colors">
                <CardHeader>
                  <div className="w-10 h-10 rounded-md bg-secondary text-gold flex items-center justify-center mb-2">
                    <I className="w-5 h-5" />
                  </div>
                  <CardTitle className="text-base">{m.title}</CardTitle>
                  <CardDescription>{m.desc}</CardDescription>
                </CardHeader>
                <CardContent>
                  <span className="text-xs text-gold inline-flex items-center group-hover:translate-x-1 transition-transform">
                    Open <ArrowRight className="w-3 h-3 ml-1" />
                  </span>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
