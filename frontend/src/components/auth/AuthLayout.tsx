import { Link } from "@tanstack/react-router";
import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { Toaster } from "@/components/ui/sonner";

export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background relative flex flex-col overflow-hidden">
      {/* Background ambient glow */}
      <div className="absolute inset-0 z-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-gold/10 via-background to-background" />
      <div className="absolute top-0 right-0 -mt-32 -mr-32 w-[32rem] h-[32rem] bg-gold/10 rounded-full blur-3xl opacity-60 pointer-events-none" />
      <div className="absolute bottom-0 left-0 -mb-32 -ml-32 w-[32rem] h-[32rem] bg-gold/5 rounded-full blur-3xl opacity-50 pointer-events-none" />

      <header className="relative z-10 px-6 py-5 border-b border-border/50 bg-background/40 backdrop-blur-md">
        <Link to="/" className="inline-flex items-center gap-2 group">
          <div className="w-9 h-9 rounded-lg gradient-gold flex items-center justify-center text-primary-foreground shadow-md transition-transform group-hover:scale-105">
            <Sparkles className="w-5 h-5" />
          </div>
          <span className="font-serif text-lg font-semibold tracking-tight">Jyotish<span className="text-gradient-gold">AI</span></span>
        </Link>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-5 py-10">
        <div className="w-full max-w-md space-y-8">
          <div className="text-center space-y-3">
            <h1 className="text-3xl md:text-4xl font-serif font-semibold tracking-tight text-foreground drop-shadow-sm">
              {title}
            </h1>
            {subtitle && <p className="text-[0.95rem] text-muted-foreground">{subtitle}</p>}
          </div>
          {children}
        </div>
      </main>
      <Toaster position="top-right" />
    </div>
  );
}
