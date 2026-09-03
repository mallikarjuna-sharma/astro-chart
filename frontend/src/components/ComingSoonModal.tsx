import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function ComingSoonModal({
  open,
  onOpenChange,
  title = "Coming soon",
  description = "This feature is not available yet. We're working on it.",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  description?: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <div className="mx-auto w-12 h-12 rounded-xl gradient-gold flex items-center justify-center text-primary-foreground mb-2">
            <Sparkles className="w-6 h-6" />
          </div>
          <p className="text-xs font-semibold uppercase tracking-widest text-gold text-center">Coming soon</p>
          <DialogTitle className="text-center">{title}</DialogTitle>
          <DialogDescription className="text-center">{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="sm:justify-center">
          <Button onClick={() => onOpenChange(false)} className="gradient-gold text-primary-foreground">
            Got it
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
