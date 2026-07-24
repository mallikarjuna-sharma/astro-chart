import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { type ComponentType, ReactNode, useEffect, useState } from "react";
import {
  Sparkles, Star, BookOpen, Compass, ClipboardList, GraduationCap,
  LineChart, MessageCircleQuestion, Bot, Settings,
  FileText, User2, Sun, Moon, LogIn, LogOut, Menu,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Toaster } from "@/components/ui/sonner";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { useDisplayName } from "@/hooks/use-display-name";
import { initialsFromName } from "@/stores/user-store";
import { useAuthStore, useIsAuthenticated } from "@/stores/auth-store";

interface NavChild {
  to: string;
  label: string;
}

interface NavItem {
  label: string;
  icon: ComponentType<{ className?: string }>;
  group: string;
  to?: string;
  children?: NavChild[];
}

const NAV: NavItem[] = [
  { to: "/", label: "Profiles", icon: User2, group: "Overview" },
  { to: "/panchanga", label: "Panchanga", icon: Sun, group: "Overview" },

  { to: "/charts", label: "Charts (D1–D81)", icon: Star, group: "Systems" },
  { to: "/kp", label: "KP Analysis", icon: Compass, group: "Systems" },
  { to: "/kn-rao", label: "KN Rao / Jaimini", icon: BookOpen, group: "Systems" },
  { to: "/parashari", label: "Parashari Strength", icon: ClipboardList, group: "Systems" },

  {
    label: "Education Analysis",
    icon: GraduationCap,
    group: "Intelligence",
    children: [
      { to: "/education-analysis/puc", label: "PUC" },
      { to: "/education-analysis/ug", label: "UG" },
    ],
  },
  { to: "/career-timeline", label: "Job Timeline", icon: LineChart, group: "Intelligence" },

  { to: "/ai", label: "AI Assistant", icon: Bot, group: "AI Assistance" },
  { to: "/prashna", label: "Prashna (Horary)", icon: MessageCircleQuestion, group: "AI Assistance" },

  { to: "/reports", label: "Reports", icon: FileText, group: "Practice" },
  { to: "/settings", label: "Settings", icon: Settings, group: "Practice" },
];

function useTheme() {
  const [isDark, setIsDark] = useState(false);
  useEffect(() => {
    setIsDark(document.documentElement.classList.contains("dark"));
  }, []);
  const toggle = () => {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try { localStorage.setItem("theme", next ? "dark" : "light"); } catch { /* ignore */ }
    setIsDark(next);
  };
  return { isDark, toggle };
}

function Brand({ onClick }: { onClick?: () => void }) {
  return (
    <Link to="/" onClick={onClick} className="flex items-center gap-2.5 group">
      <div className="relative w-10 h-10 rounded-xl gradient-gold flex items-center justify-center text-primary-foreground shadow-lg ring-gold-glow transition-transform group-hover:scale-105">
        <Sparkles className="w-5 h-5" />
      </div>
      <div className="leading-tight">
        <div className="font-serif text-lg font-semibold tracking-tight">
          Jyotish<span className="text-gradient-gold">AI</span>
        </div>
        <div className="text-[9.5px] uppercase tracking-[0.18em] text-muted-foreground">
          KP · KN Rao · Parashari · Prashna
        </div>
      </div>
    </Link>
  );
}

function SidebarNav({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const groups = Array.from(new Set(NAV.map((n) => n.group)));

  const renderNavLink = (
    to: string,
    label: string,
    Icon: NavItem["icon"],
    opts?: { nested?: boolean },
  ) => {
    const active = pathname === to || (to !== "/" && pathname.startsWith(`${to}/`));
  return (
      <Link
        to={to}
        onClick={onNavigate}
        className={cn(
          "group relative flex items-center gap-3 rounded-lg text-sm transition-all",
          opts?.nested ? "px-3 py-1.5 pl-9" : "px-3 py-2",
          active
            ? "bg-sidebar-accent text-foreground font-medium"
            : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-foreground",
        )}
      >
        {active && !opts?.nested ? (
          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-full gradient-gold" />
        ) : null}
        {!opts?.nested ? (
          <Icon
            className={cn(
              "w-[18px] h-[18px] shrink-0 transition-colors",
              active ? "text-gold" : "text-sidebar-foreground/55 group-hover:text-gold/80",
            )}
          />
        ) : (
          <span
            className={cn(
              "w-1.5 h-1.5 shrink-0 rounded-full",
              active ? "bg-gold" : "bg-sidebar-foreground/35 group-hover:bg-gold/60",
            )}
          />
        )}
        <span className="truncate">{label}</span>
      </Link>
    );
  };

  return (
    <nav className="flex-1 overflow-y-auto py-4 px-3">
      {groups.map((g) => (
        <div key={g} className="pb-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-sidebar-foreground/45 px-3 py-1.5">
            {g}
          </div>
          <ul className="space-y-0.5">
            {NAV.filter((n) => n.group === g).map((item) => {
              const Icon = item.icon;
              const sectionActive =
                item.children?.some((child) => pathname === child.to || pathname.startsWith(`${child.to}/`)) ??
                false;

              if (item.children?.length) {
                return (
                  <li key={item.label}>
                    <div
                      className={cn(
                        "flex items-center gap-3 px-3 py-2 text-sm font-medium",
                        sectionActive ? "text-foreground" : "text-sidebar-foreground/80",
                      )}
                    >
                      <Icon
                        className={cn(
                          "w-[18px] h-[18px] shrink-0",
                          sectionActive ? "text-gold" : "text-sidebar-foreground/55",
                        )}
                      />
                      <span className="truncate">{item.label}</span>
                    </div>
                    <ul className="mt-0.5 mb-1 space-y-0.5">
                      {item.children.map((child) => (
                        <li key={child.to}>{renderNavLink(child.to, child.label, Icon, { nested: true })}</li>
                      ))}
                    </ul>
                  </li>
                );
              }

              if (!item.to) return null;

              return (
                <li key={item.to}>
                  {renderNavLink(item.to, item.label, Icon)}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();
  const displayName = useDisplayName();
  const initials = initialsFromName(displayName);
  const isAuthenticated = useIsAuthenticated();
  const authUser = useAuthStore((s) => s.user);
  const clearSession = useAuthStore((s) => s.clearSession);
  const { isDark, toggle } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = () => {
    clearSession();
    navigate({ to: "/login" });
  };

  return (
    <div className="min-h-screen flex">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-64 flex-col bg-sidebar/80 backdrop-blur-xl text-sidebar-foreground border-r border-sidebar-border sticky top-0 h-screen">
        <div className="px-5 py-5 border-b border-sidebar-border">
          <Brand />
        </div>
        <SidebarNav pathname={pathname} />
        <div className="px-5 py-3 border-t border-sidebar-border text-[11px] text-sidebar-foreground/45 flex items-center justify-between">
          <span>v1.2 · 2026</span>
          <span className="inline-flex items-center gap-1 text-gold/70"><Sparkles className="w-3 h-3" /> Vedic Intelligence</span>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 px-4 md:px-8 h-16 border-b border-border glass">
          {/* Mobile: hamburger + brand */}
          <div className="flex items-center gap-2 md:hidden">
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <button className="p-2 -ml-1 rounded-lg hover:bg-muted text-muted-foreground" aria-label="Open navigation">
                  <Menu className="w-5 h-5" />
                </button>
              </SheetTrigger>
              <SheetContent side="left" className="w-72 p-0 bg-sidebar text-sidebar-foreground border-sidebar-border flex flex-col">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <div className="px-5 py-5 border-b border-sidebar-border">
                  <Brand onClick={() => setMobileOpen(false)} />
                </div>
                <SidebarNav pathname={pathname} onNavigate={() => setMobileOpen(false)} />
              </SheetContent>
            </Sheet>
            <Brand />
          </div>

          <div className="text-sm text-muted-foreground hidden md:block">
            {isAuthenticated && authUser ? (
              <>Signed in as <span className="font-medium text-foreground">@{authUser.username}</span></>
            ) : displayName !== "Student" ? (
              <>Welcome back, <span className="font-medium text-foreground">{displayName}</span></>
            ) : (
              "Let the charts illuminate the path ahead."
            )}
          </div>

          <div className="flex items-center gap-1.5">
            {isAuthenticated ? (
              <button
                onClick={handleLogout}
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm hover:bg-muted text-muted-foreground transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Log out
              </button>
            ) : (
              <Link
                to="/login"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm hover:bg-muted text-muted-foreground transition-colors"
              >
                <LogIn className="w-4 h-4" />
                Log in
              </Link>
            )}
            <button
              onClick={toggle}
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors"
              aria-label="Toggle theme"
            >
              {isDark ? <Sun className="w-[18px] h-[18px]" /> : <Moon className="w-[18px] h-[18px]" />}
            </button>
            <div
              className="w-9 h-9 rounded-full grid place-items-center text-xs font-semibold text-primary-foreground gradient-gold shadow-sm"
              title={displayName}
            >
              {initials}
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 sm:px-6 md:px-8 py-6 md:py-8 max-w-[1440px] w-full mx-auto">
          {children}
        </main>

        <footer className="border-t border-border/60 px-4 md:px-8 py-5 text-xs text-muted-foreground flex flex-col sm:flex-row items-center justify-between gap-2 max-w-[1440px] w-full mx-auto">
          <span>© {new Date().getFullYear()} JyotishAI · Four-system Vedic intelligence</span>
          <span className="text-muted-foreground/70">For educational guidance only — not a substitute for professional advice.</span>
        </footer>
      </div>
      <Toaster position="top-right" />
    </div>
  );
}

export function PageHeader({ title, subtitle, action, eyebrow }: { title: string; subtitle?: string; action?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-7 flex items-end justify-between gap-4 flex-wrap animate-rise">
      <div>
        {eyebrow && (
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gold/90 mb-1.5">
            {eyebrow}
          </div>
        )}
        <h1 className="font-serif text-3xl md:text-[2.15rem] font-semibold tracking-tight leading-tight">{title}</h1>
        {subtitle && <p className="text-sm md:text-[0.95rem] text-muted-foreground mt-2 max-w-2xl leading-relaxed">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
