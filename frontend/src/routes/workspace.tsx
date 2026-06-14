import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, notifyStub } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/workspace")({
  head: () => ({ meta: [{ title: "Astrologer Workspace — JyotishAI" }] }),
  component: WorkspacePage,
});

function WorkspacePage() {
  const qc = useQueryClient();
  const clients = useQuery({ queryKey: ["clients"], queryFn: api.listClients });
  const [q, setQ] = useState("");
  const [newName, setNewName] = useState("");
  const [open, setOpen] = useState(false);

  const addClient = async () => {
    if (!newName) return;
    await api.createClient(newName);
    toast.success("Client added");
    setNewName(""); setOpen(false);
    qc.invalidateQueries({ queryKey: ["clients"] });
  };

  const filtered = clients.data?.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())) ?? [];

  return (
    <div>
      <PageHeader title="Astrologer Workspace" subtitle="Clients, multi-system analysis tools, reports and teaching." />
      <Tabs defaultValue="clients">
        <TabsList>
          <TabsTrigger value="clients">Clients</TabsTrigger>
          <TabsTrigger value="tools">Analysis Tools</TabsTrigger>
          <TabsTrigger value="teaching">Teaching</TabsTrigger>
        </TabsList>

        <TabsContent value="clients" className="mt-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <div><CardTitle>Clients</CardTitle><CardDescription>Unlimited on Professional tier.</CardDescription></div>
              <div className="flex gap-2">
                <Input placeholder="Search…" value={q} onChange={(e)=>setQ(e.target.value)} className="w-48" />
                <Button variant="outline" onClick={() => notifyStub("Export clients CSV")}>Export CSV</Button>
                <Dialog open={open} onOpenChange={setOpen}>
                  <DialogTrigger asChild><Button className="gradient-gold text-primary-foreground">+ New client</Button></DialogTrigger>
                  <DialogContent>
                    <DialogHeader><DialogTitle>New client</DialogTitle></DialogHeader>
                    <div className="space-y-2"><Label>Name</Label><Input value={newName} onChange={(e)=>setNewName(e.target.value)} /></div>
                    <DialogFooter><Button onClick={addClient}>Create</Button></DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground uppercase">
                  <tr><th className="text-left py-1">Name</th><th>Category</th><th>Last session</th><th /></tr>
                </thead>
                <tbody>
                  {filtered.map((c) => (
                    <tr key={c.id} className="border-t border-border">
                      <td className="py-2">{c.name}</td>
                      <td><Badge variant="outline">{c.category}</Badge></td>
                      <td className="text-muted-foreground tabular-nums">{c.lastSession}</td>
                      <td className="text-right">
                        <Button size="sm" variant="ghost" onClick={() => notifyStub("Open " + c.name)}>Open</Button>
                        <Button size="sm" variant="ghost" onClick={() => notifyStub("Generate report for " + c.name)}>Report</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tools" className="mt-4">
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              "Side-by-side chart comparison (D1/D9/D10/D24/Chalit/Prashna)",
              "Transit overlay with Ashtakavarga bindus",
              "Progressive Dasha drill-down (Maha→Sookshma)",
              "KP sub-sub lord calculator",
              "Ruling Planet calculator",
              "Cuspal Interlink analysis",
              "Shadbala / Ashtakavarga viewer",
              "Birth time rectification wizard",
              "Prashna chart generator",
            ].map((t) => (
              <Card key={t}>
                <CardHeader><CardTitle className="text-base">{t}</CardTitle></CardHeader>
                <CardContent><Button size="sm" variant="outline" onClick={() => notifyStub(t)}>Open tool</Button></CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="teaching" className="mt-4">
          <div className="grid md:grid-cols-2 gap-4">
            {[
              ["Step-by-step calculation viewer","KP / KN Rao / Parashari / Prashna workings."],
              ["Case study library","Verified charts with known outcomes across all four systems."],
              ["Principle reference library","KP Reader, KN Rao texts, BPHS, Prashna Marga."],
              ["Quiz mode","Calculate manually; system verifies your answer."],
            ].map(([t,d]) => (
              <Card key={t}>
                <CardHeader><CardTitle className="text-base">{t}</CardTitle><CardDescription>{d}</CardDescription></CardHeader>
                <CardContent><Button size="sm" variant="outline" onClick={() => notifyStub(t)}>Launch</Button></CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
