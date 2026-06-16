import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Star } from "lucide-react";

export const Route = createFileRoute("/marketplace")({
  head: () => ({ meta: [{ title: "Marketplace — JyotishAI" }] }),
  component: MarketplacePage,
});

function MarketplacePage() {
  const { data } = useQuery({ queryKey: ["astrologers"], queryFn: api.listAstrologers });
  const [filter, setFilter] = useState("");
  const [slot, setSlot] = useState("");

  const book = async (id: string, s: string) => {
    const r = await api.bookConsultation(id, s);
    toast.success("Booking " + r.bookingId + " confirmed");
  };

  const list = data?.filter((a) => (a.name + a.systems.join(" ")).toLowerCase().includes(filter.toLowerCase())) ?? [];

  return (
    <div>
      <PageHeader
        title="Consultation Marketplace"
        subtitle="Verified astrologers across KP, KN Rao, Parashari and Prashna."
        action={<Input placeholder="Filter…" value={filter} onChange={(e)=>setFilter(e.target.value)} className="w-56" />}
      />
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {list.map((a) => (
          <Card key={a.id}>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full gradient-gold flex items-center justify-center text-primary-foreground font-semibold">
                  {a.name.split(" ").map(w=>w[0]).slice(0,2).join("")}
                </div>
                <div>
                  <CardTitle className="text-base">{a.name}</CardTitle>
                  <CardDescription className="flex items-center gap-1"><Star className="w-3 h-3 fill-gold text-gold" /> {a.rating} · ₹{a.pricePerMin}/min</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1 mb-2">{a.systems.map((s)=>(<Badge key={s} variant="outline" className="border-gold/50 text-gold">{s}</Badge>))}</div>
              <div className="text-xs text-muted-foreground mb-3">Languages: {a.languages.join(", ")}</div>
              <Dialog>
                <DialogTrigger asChild><Button className="w-full gradient-gold text-primary-foreground">Book consultation</Button></DialogTrigger>
                <DialogContent>
                  <DialogHeader><DialogTitle>Book {a.name}</DialogTitle></DialogHeader>
                  <div className="space-y-2"><label className="text-sm">Preferred slot</label><Input type="datetime-local" value={slot} onChange={(e)=>setSlot(e.target.value)} /></div>
                  <DialogFooter><Button onClick={() => book(a.id, slot)} disabled={!slot}>Confirm booking</Button></DialogFooter>
                </DialogContent>
              </Dialog>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
