import { Link, useRouterState } from "@tanstack/react-router";
import { ReactNode } from "react";
import {
  Sparkles, Star, BookOpen, Compass, ClipboardList, GraduationCap,
  LineChart, MessageCircleQuestion, Briefcase, Bot, Store, Settings,
  FileText, User2, Sun, Moon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Toaster } from "@/components/ui/sonner";
import { useDisplayName } from "@/hooks/use-display-name";
import { initialsFromName } from "@/stores/user-store";

interface NavItem { to: string; label: string; icon: any; group: string; }

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: Sparkles, group: "Overview" },
  { to: "/birth-data", label: "Birth Data", icon: User2, group: "Overview" },
  { to: "/panchanga", label: "Panchanga", icon: Sun, group: "Overview" },

  { to: "/charts", label: "Charts (D1–D81)", icon: Star, group: "Systems" },
  { to: "/kp", label: "KP Analysis", icon: Compass, group: "Systems" },
  { to: "/kn-rao", label: "KN Rao / Jaimini", icon: BookOpen, group: "Systems" },
  { to: "/parashari", label: "Parashari Strength", icon: ClipboardList, group: "Systems" },
  { to: "/prashna", label: "Prashna (Horary)", icon: MessageCircleQuestion, group: "Systems" },

  { to: "/education-analysis", label: "Education Analysis", icon: GraduationCap, group: "Intelligence" },
  { to: "/confidence", label: "Four-System Score", icon: Star, group: "Intelligence" },
  { to: "/student", label: "Student / Field", icon: GraduationCap, group: "Intelligence" },
  { to: "/career-timeline", label: "Career Timeline", icon: LineChart, group: "Intelligence" },
  { to: "/ai", label: "AI Assistant", icon: Bot, group: "Intelligence" },

  { to: "/workspace", label: "Astrologer Workspace", icon: Briefcase, group: "Practice" },
  { to: "/reports", label: "Reports", icon: FileText, group: "Practice" },
  { to: "/marketplace", label: "Marketplace", icon: Store, group: "Practice" },
  { to: "/settings", label: "Settings", icon: Settings, group: "Practice" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const groups = Array.from(new Set(NAV.map((n) => n.group)));
  const displayName = useDisplayName();
  const initials = initialsFromName(displayName);

  return (
    <div className="min-h-screen flex">
      <aside className="hidden md:flex w-64 flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border">
        <Link to="/" className="px-5 py-5 flex items-center gap-2 border-b border-sidebar-border">
          <div className="w-9 h-9 rounded-lg gradient-gold flex items-center justify-center text-primary-foreground">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="font-semibold tracking-tight">JyotishAI</div>
            <div className="text-[10px] uppercase tracking-widest text-sidebar-foreground/60">KP · KN Rao · Parashari · Prashna</div>
          </div>
        </Link>
        <nav className="flex-1 overflow-y-auto py-3">
          {groups.map((g) => (
            <div key={g} className="px-3 pb-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/50 px-2 py-2">{g}</div>
              <ul className="space-y-0.5">
                {NAV.filter((n) => n.group === g).map((item) => {
                  const active = pathname === item.to;
                  const Icon = item.icon;
                  return (
                    <li key={item.to}>
                      <Link
                        to={item.to}
                        className={cn(
                          "flex items-center gap-3 px-2.5 py-2 rounded-md text-sm transition-colors",
                          active
                            ? "bg-sidebar-accent text-gold border-l-2 border-gold pl-2"
                            : "hover:bg-sidebar-accent/60 text-sidebar-foreground/85"
                        )}
                      >
                        <Icon className="w-4 h-4 shrink-0" />
                        <span className="truncate">{item.label}</span>
                      </Link>
                    </li>
                  );
                })}
            </ul>
            </div>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-sidebar-border text-xs text-sidebar-foreground/60">
          v1.1 · June 2026
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 flex items-center justify-between px-5 md:px-8 h-14 border-b border-border bg-card-glass">
          <div className="flex items-center gap-3 md:hidden">
            <div className="w-8 h-8 rounded-lg gradient-gold flex items-center justify-center text-primary-foreground">
              <Sparkles className="w-4 h-4" />
            </div>
            <span className="font-semibold">JyotishAI</span>
          </div>
          <div className="text-sm text-muted-foreground hidden md:block">
            {displayName !== "Student" ? (
              <>Welcome back, <span className="font-medium text-foreground">{displayName}</span></>
            ) : (
              "Welcome back — let the charts illuminate the path ahead."
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => document.documentElement.classList.toggle("dark")}
              className="p-2 rounded-md hover:bg-muted text-muted-foreground"
              aria-label="Toggle theme"
            >
              <Sun className="w-4 h-4 hidden dark:block" />
              <Moon className="w-4 h-4 dark:hidden" />
            </button>
            <div
              className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center text-xs font-medium"
              title={displayName}
            >
              {initials}
            </div>
          </div>
        </header>
        <main className="flex-1 px-5 md:px-8 py-6 md:py-8 max-w-[1400px] w-full mx-auto">
          {children}
        </main>
      </div>
      <Toaster position="top-right" />
    </div>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
