import { useCallback, useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { pyjhora } from "@/lib/pyjhora/client";
import type { GeocodeResponse, PlaceSuggestion } from "@/lib/pyjhora/types";
import { cn } from "@/lib/utils";

interface PlaceAutocompleteProps {
  value: string;
  onChange: (v: string) => void;
  onResolved: (geo: GeocodeResponse, query: string) => void;
  className?: string;
  placeholder?: string;
}

export function PlaceAutocomplete({
  value,
  onChange,
  onResolved,
  className,
  placeholder = "Start typing — e.g. Kollam, Srirangam",
}: PlaceAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const fetchSuggestions = useCallback(async (input: string) => {
    if (input.length < 2) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    try {
      const data = await pyjhora.placesAutocomplete(input);
      setSuggestions(data.suggestions ?? []);
      setOpen((data.suggestions?.length ?? 0) > 0);
    } catch {
      setSuggestions([]);
      setOpen(false);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const onInput = (v: string) => {
    onChange(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => fetchSuggestions(v.trim()), 300);
  };

  const resolve = async (placeId: string, description: string) => {
    setOpen(false);
    setSuggestions([]);
    try {
      const geo = await pyjhora.resolvePlace(placeId);
      onChange(description || geo.place_label);
      onResolved(geo, description);
      setStatus(`Resolved via ${geo.provider}: ${geo.place_label}`);
    } catch (err) {
      setStatus(String((err as Error).message ?? err));
    }
  };

  const geocodeDirect = async () => {
    const q = value.trim();
    if (!q) return;
    setOpen(false);
    try {
      const geo = await pyjhora.geocode(q);
      onResolved(geo, q);
      onChange(q);
      setStatus(`Resolved via ${geo.provider}: ${geo.place_label}`);
    } catch (err) {
      setStatus(String((err as Error).message ?? err));
    }
  };

  return (
    <div ref={wrapRef} className={cn("relative", className)}>
      <Input
        value={value}
        onChange={(e) => onInput(e.target.value)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            geocodeDirect();
          }
        }}
        placeholder={placeholder}
        autoComplete="off"
      />
      {open && suggestions.length > 0 && (
        <ul className="absolute z-20 left-0 right-0 mt-1 border border-border rounded-md bg-popover shadow-lg max-h-48 overflow-auto">
          {suggestions.map((s) => (
            <li
              key={s.place_id}
              className="px-3 py-2 text-sm cursor-pointer hover:bg-muted border-b border-border/50 last:border-0"
              onMouseDown={(e) => {
                e.preventDefault();
                resolve(s.place_id, s.description);
              }}
            >
              {s.description}
            </li>
          ))}
        </ul>
      )}
      {status && <p className="text-xs text-muted-foreground mt-1">{status}</p>}
    </div>
  );
}
