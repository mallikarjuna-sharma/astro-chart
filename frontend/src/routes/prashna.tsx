import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { PlaceAutocomplete } from "@/components/charts/PlaceAutocomplete";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { pyjhora } from "@/lib/pyjhora";
import type { PrashnaCategoryMeta, PrashnaResponse } from "@/lib/pyjhora/types";

export const Route = createFileRoute("/prashna")({
  head: () => ({ meta: [{ title: "Prashna — JyotishAI" }] }),
  component: PrashnaPage,
});

const FALLBACK_CATEGORIES: PrashnaCategoryMeta[] = [
  { key: "career_employment", label: "Career & Employment", primary_house: 10, example: "Will I get this job offer?" },
  { key: "job_change", label: "Job Change", primary_house: 10, example: "Should I change my job now?" },
  { key: "business", label: "Business", primary_house: 10, example: "Will my business venture succeed?" },
  { key: "financial", label: "Financial", primary_house: 11, example: "Will I receive the expected money?" },
  { key: "education", label: "Education", primary_house: 5, example: "Will I pass my exam / get admission?" },
  { key: "foreign_opportunity", label: "Foreign Opportunity", primary_house: 12, example: "Will I get a chance to go abroad?" },
  { key: "relationship", label: "Relationship", primary_house: 7, example: "Will this relationship work out?" },
  { key: "marriage", label: "Marriage", primary_house: 7, example: "Will my marriage happen this year?" },
  { key: "health", label: "Health", primary_house: 1, example: "Will I recover from this illness quickly?" },
  { key: "property", label: "Property", primary_house: 4, example: "Will I be able to buy/sell this property?" },
  { key: "legal", label: "Legal", primary_house: 6, example: "Will the legal case go in my favour?" },
  { key: "travel", label: "Travel", primary_house: 12, example: "Will my travel plans go ahead smoothly?" },
  { key: "competition", label: "Competition", primary_house: 6, example: "Will I win this competition / election?" },
  { key: "pregnancy", label: "Pregnancy", primary_house: 5, example: "Will I conceive soon?" },
];

function PrashnaPage() {
  const [categories, setCategories] = useState<PrashnaCategoryMeta[]>(FALLBACK_CATEGORIES);
  const [category, setCategory] = useState(FALLBACK_CATEGORIES[0].key);
  const [question, setQuestion] = useState("");
  const [place, setPlace] = useState("");
  const [lat, setLat] = useState<number | undefined>();
  const [lon, setLon] = useState<number | undefined>();
  const [askedAt, setAskedAt] = useState(new Date().toISOString().slice(0, 16));
  const [answer, setAnswer] = useState<PrashnaResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    pyjhora.prashnaCategories().then((res) => {
      if (res.categories?.length) {
        setCategories(res.categories);
        setCategory(res.categories[0].key);
      }
    }).catch(() => {
      // Keep fallback list when API is unreachable.
    });
  }, []);

  const selectedCategory = categories.find((c) => c.key === category);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setAnswer(null);
    try {
      const moment = askedAt.replace("T", " ");
      const res = await pyjhora.prashna({
        question: question.trim(),
        category,
        moment,
        city: place,
        lat,
        lon,
      });
      setAnswer(res);
    } catch (err) {
      toast.error(String((err as Error).message ?? err));
    } finally {
      setLoading(false);
    }
  };

  const confidencePct = answer ? Math.round(answer.confidence * 100) : 0;

  return (
    <div>
      <PageHeader title="Prashna (Horary)" subtitle="The moment of your question becomes the chart. No birth data required." />

      <div className="grid lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Ask your question</CardTitle>
            <CardDescription>Be sincere and specific. The chart is cast for the moment you specify.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={ask} className="space-y-3">
              <div>
                <Label>Category</Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {categories.map((c) => (
                      <SelectItem key={c.key} value={c.key}>{c.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedCategory && (
                  <p className="text-xs text-muted-foreground mt-1">
                    e.g. {selectedCategory.example}
                  </p>
                )}
              </div>
              <div>
                <Label>Question</Label>
                <Textarea
                  required
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={selectedCategory?.example ?? "Will this happen?"}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Moment</Label>
                  <Input type="datetime-local" value={askedAt} onChange={(e) => setAskedAt(e.target.value)} required />
                </div>
                <div>
                  <Label>Place</Label>
                  <PlaceAutocomplete
                    value={place}
                    onChange={setPlace}
                    onResolved={(geo) => {
                      setPlace(geo.place_label);
                      setLat(geo.latitude);
                      setLon(geo.longitude);
                    }}
                    placeholder="City where you asked"
                  />
                </div>
              </div>
              <Button type="submit" disabled={loading} className="gradient-gold text-primary-foreground">
                {loading ? "Casting chart…" : "Cast Prashna chart"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="bg-card-glass">
          <CardHeader>
            <CardTitle>Answer</CardTitle>
            <CardDescription>
              {answer ? `${answer.category_label} · ${answer.confidence_band}` : "Cast a chart to see the answer."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!answer && (
              <div className="text-sm text-muted-foreground italic">Your Prashna answer will appear here.</div>
            )}
            {answer && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge className={
                    answer.verdict === "YES" ? "bg-gold text-primary-foreground text-base px-3 py-1" :
                    answer.verdict === "NO" ? "bg-destructive text-base px-3 py-1" :
                    "bg-accent text-accent-foreground text-base px-3 py-1"
                  }>{answer.verdict}</Badge>
                  <ConfidenceBadge score={confidencePct} />
                  {answer.moon_void && (
                    <Badge variant="outline" className="text-amber-600 border-amber-600/40">Moon void-of-course</Badge>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-xs uppercase text-muted-foreground">Lagna</div>
                    <div>{answer.lagna_sign} · lord {answer.lagna_lord}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase text-muted-foreground">Moon</div>
                    <div>{answer.moon_sign} · {answer.moon_nakshatra}</div>
                  </div>
                </div>

                <div>
                  <div className="text-xs uppercase text-muted-foreground">KP sub-lord</div>
                  <div className="text-sm">{answer.kp_sublord_verdict}</div>
                </div>

                <div>
                  <div className="text-xs uppercase text-muted-foreground">Timing</div>
                  <div className="text-sm">{answer.timing_estimate || "—"}</div>
                </div>

                <div>
                  <div className="text-xs uppercase text-muted-foreground">Moon status</div>
                  <div className="text-sm">{answer.moon_status}</div>
                </div>

                {answer.classical_rules.length > 0 && (
                  <div>
                    <div className="text-xs uppercase text-muted-foreground">Classical rules</div>
                    <ul className="text-sm list-disc pl-4 space-y-1">
                      {answer.classical_rules.slice(0, 5).map((rule) => (
                        <li key={rule}>{rule}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {answer.factors.length > 0 && (
                  <div>
                    <div className="text-xs uppercase text-muted-foreground">Key factors</div>
                    <ul className="text-sm space-y-1">
                      {answer.factors.slice(0, 4).map((f) => (
                        <li key={f.factor}>
                          <span className="font-medium">{f.factor}</span>
                          <span className="text-muted-foreground"> — {f.detail}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {answer.remedies.length > 0 && (
                  <div>
                    <div className="text-xs uppercase text-muted-foreground">Remedies / conditions</div>
                    <ul className="text-sm list-disc pl-4 space-y-1">
                      {answer.remedies.slice(0, 3).map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {answer.natal_notes.length > 0 && (
                  <div>
                    <div className="text-xs uppercase text-muted-foreground">Natal overlay</div>
                    <ul className="text-sm list-disc pl-4 space-y-1">
                      {answer.natal_notes.map((n) => (
                        <li key={n}>{n}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
