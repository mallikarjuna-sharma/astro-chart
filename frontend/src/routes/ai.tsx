import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/AppShell";
import { AiAssistanceTabs } from "@/components/ai/AiAssistanceTabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { useState } from "react";
import { api } from "@/lib/api";

export const Route = createFileRoute("/ai")({
  head: () => ({ meta: [{ title: "AI Assistant — JyotishAI" }] }),
  component: AIPage,
});

const SAMPLES = [
  "Should I do MBA or MS in Data Science?",
  "Is 2027 a good year to start a business?",
  "Should I leave my IT job for consulting?",
  "Will I get this job offer?",
  "When will my income improve significantly?",
];

function AIPage() {
  const [messages, setMessages] = useState<{ role: "user" | "ai"; text: string; score?: number }[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const send = async (text?: string) => {
    const prompt = (text ?? input).trim();
    if (!prompt) return;
    setMessages((m) => [...m, { role: "user", text: prompt }]);
    setInput(""); setLoading(true);
    const r = await api.askAI(prompt);
    setMessages((m) => [...m, { role: "ai", text: r.answer, score: r.score }]);
    setLoading(false);
  };

  return (
    <div>
      <PageHeader title="AI Assistance" subtitle="Natural language chat and horary (Prashna) questions across all four systems." />
      <AiAssistanceTabs />

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 flex flex-col h-[70vh]">
          <CardHeader><CardTitle>Chat</CardTitle></CardHeader>
          <CardContent className="flex-1 overflow-y-auto space-y-3">
            {messages.length === 0 && <div className="text-sm text-muted-foreground italic">Try a sample question on the right →</div>}
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "text-right" : ""}>
                <div className={`inline-block px-4 py-2 rounded-lg max-w-[80%] text-sm ${m.role === "user" ? "bg-secondary" : "bg-card border border-gold/30"}`}>
                  {m.text}
                  {m.score && <div className="mt-2"><ConfidenceBadge score={m.score} size="sm" /></div>}
                </div>
              </div>
            ))}
            {loading && <div className="text-sm text-muted-foreground italic">Consulting all four systems…</div>}
          </CardContent>
          <div className="border-t border-border p-3 flex gap-2">
            <Textarea value={input} onChange={(e)=>setInput(e.target.value)} placeholder="Ask anything about career, education, timing…" className="min-h-[60px]" />
            <Button className="gradient-gold text-primary-foreground" onClick={() => send()} disabled={loading}>Send</Button>
          </div>
        </Card>

        <Card>
          <CardHeader><CardTitle>Sample questions</CardTitle><CardDescription>Tap to ask.</CardDescription></CardHeader>
          <CardContent className="space-y-2">
            {SAMPLES.map((s) => (
              <Button key={s} variant="ghost" className="w-full justify-start h-auto py-2 text-left whitespace-normal" onClick={() => send(s)}>
                {s}
              </Button>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
