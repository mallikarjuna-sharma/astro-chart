import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { useState } from "react";
import { api } from "@/lib/api";

export const Route = createFileRoute("/prashna")({
  head: () => ({ meta: [{ title: "Prashna — JyotishAI" }] }),
  component: PrashnaPage,
});

const CATEGORIES = [
  "Career & Employment","Business","Education","Foreign Opportunity","Financial","Job Change",
];

function PrashnaPage() {
  const [question, setQuestion] = useState("");
  const [category, setCategory] = useState(CATEGORIES[0]);
  const [place, setPlace] = useState("");
  const [askedAt, setAskedAt] = useState(new Date().toISOString().slice(0,16));
  const [answer, setAnswer] = useState<Awaited<ReturnType<typeof api.askPrashna>> | null>(null);
  const [loading, setLoading] = useState(false);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const res = await api.askPrashna({ question, category, place, askedAt });
    setAnswer(res);
    setLoading(false);
  };

  return (
    <div>
      <PageHeader title="Prashna (Horary)" subtitle="The moment of your question becomes the chart. No birth data required." />

      <div className="grid lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle>Ask your question</CardTitle><CardDescription>Be sincere and specific.</CardDescription></CardHeader>
          <CardContent>
            <form onSubmit={ask} className="space-y-3">
              <div>
                <Label>Category</Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{CATEGORIES.map((c)=>(<SelectItem key={c} value={c}>{c}</SelectItem>))}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>Question</Label>
                <Textarea required value={question} onChange={(e)=>setQuestion(e.target.value)} placeholder="Will I get this job offer?" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Moment</Label>
                  <Input type="datetime-local" value={askedAt} onChange={(e)=>setAskedAt(e.target.value)} required />
                </div>
                <div>
                  <Label>Place</Label>
                  <Input value={place} onChange={(e)=>setPlace(e.target.value)} placeholder="City" required />
                </div>
              </div>
              <Button type="submit" disabled={loading} className="gradient-gold text-primary-foreground">
                {loading ? "Casting chart…" : "Cast Prashna chart"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="bg-card-glass">
          <CardHeader><CardTitle>Answer</CardTitle><CardDescription>{answer?.badge ?? "Cast a chart to see the answer."}</CardDescription></CardHeader>
          <CardContent>
            {!answer && <div className="text-sm text-muted-foreground italic">Your Prashna answer will appear here.</div>}
            {answer && (
              <div className="space-y-4">
                <div className="flex items-center gap-4">
                  <Badge className={
                    answer.answer === "YES" ? "bg-gold text-primary-foreground text-base px-3 py-1" :
                    answer.answer === "NO" ? "bg-destructive text-base px-3 py-1" :
                    "bg-accent text-accent-foreground text-base px-3 py-1"
                  }>{answer.answer}</Badge>
                  <ConfidenceBadge score={answer.confidence} />
                </div>
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Timing</div>
                  <div className="text-sm">{answer.timing}</div>
                </div>
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Reasoning</div>
                  <p className="text-sm text-foreground/90">{answer.reasoning}</p>
                </div>
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Conditions</div>
                  <p className="text-sm">{answer.conditions}</p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
