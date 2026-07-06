import { Link, useRouterState } from "@tanstack/react-router";
import { Bot, MessageCircleQuestion } from "lucide-react";
import { cn } from "@/lib/utils";

const TABS = [
  { to: "/ai", label: "AI Chat", icon: Bot },
  { to: "/prashna", label: "Prashna (Horary)", icon: MessageCircleQuestion },
] as const;

export function AiAssistanceTabs() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <div className="flex gap-1 mb-6 border-b border-border">
      {TABS.map(({ to, label, icon: Icon }) => {
        const active = pathname === to;
        return (
          <Link
            key={to}
            to={to}
            className={cn(
              "inline-flex items-center gap-2 px-4 py-2.5 text-sm border-b-2 -mb-px transition-colors",
              active
                ? "border-gold text-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="w-4 h-4 shrink-0" />
            {label}
          </Link>
        );
      })}
    </div>
  );
}
