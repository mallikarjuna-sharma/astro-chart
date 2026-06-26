import { LucideIcon, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Link } from "@tanstack/react-router";

export function ComingSoonCard({
  title,
  description,
  icon: Icon = Sparkles,
  ctaHref = "/birth-data",
  ctaLabel = "Enter birth data",
}: {
  title: string;
  description: string;
  icon?: LucideIcon;
  ctaHref?: string;
  ctaLabel?: string;
}) {
  return (
    <Card className="border-dashed border-gold/30 bg-card-glass overflow-hidden">
      <CardContent className="py-16 px-6 text-center relative">
        <div className="absolute inset-0 opacity-[0.04] pointer-events-none gradient-gold" aria-hidden />
        <div className="relative mx-auto w-14 h-14 rounded-2xl gradient-gold flex items-center justify-center text-primary-foreground mb-5 shadow-lg">
          <Icon className="w-7 h-7" />
        </div>
        <p className="text-xs font-semibold uppercase tracking-widest text-gold mb-2">Coming soon</p>
        <h2 className="text-xl font-semibold mb-2">{title}</h2>
        <p className="text-sm text-muted-foreground max-w-md mx-auto mb-6">{description}</p>
        <Link to={ctaHref}>
          <Button variant="outline" className="border-gold/40 text-gold hover:bg-gold/10">
            {ctaLabel}
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}
