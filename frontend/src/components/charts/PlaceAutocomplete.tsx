import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { pyjhora } from "@/lib/pyjhora/client";
import type { GeocodeResponse, PlaceSuggestion } from "@/lib/pyjhora/types";
import { cn } from "@/lib/utils";

/** Wait this long after the last keystroke before calling Google Places autocomplete. */
const DEBOUNCE_MS = 450;
const MIN_QUERY_LENGTH = 2;

interface PlaceAutocompleteProps {
  value: string;
  onChange: (v: string) => void;
  onResolved: (geo: GeocodeResponse, query?: string) => void;
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
  const listId = useId();
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const fetchSuggestions = useCallback(async (input: string) => {
    abortRef.current?.abort();
    if (input.length < MIN_QUERY_LENGTH) {
      setSuggestions([]);
      setOpen(false);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setStatus("");

    try {
      const data = await pyjhora.placesAutocomplete(input);
      if (controller.signal.aborted) return;
      const items = data.suggestions ?? [];
      setSuggestions(items);
      setOpen(items.length > 0);
    } catch (err) {
      if (controller.signal.aborted) return;
      setSuggestions([]);
      setOpen(false);
      setStatus(String((err as Error).message ?? err));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  const scheduleFetch = useCallback(
    (input: string) => {
      if (timer.current) clearTimeout(timer.current);
      abortRef.current?.abort();
      setLoading(false);

      const trimmed = input.trim();
      if (trimmed.length < MIN_QUERY_LENGTH) {
        setSuggestions([]);
        setOpen(false);
        return;
      }

      timer.current = setTimeout(() => {
        void fetchSuggestions(trimmed);
      }, DEBOUNCE_MS);
    },
    [fetchSuggestions],
  );

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
      abortRef.current?.abort();
    };
  }, []);

  const onInput = (v: string) => {
    onChange(v);
    setStatus("");
    setOpen(false);
    scheduleFetch(v);
  };

  const resolve = async (placeId: string, description: string) => {
    setOpen(false);
    setSuggestions([]);
    setLoading(true);
    setStatus("");
    try {
      const geo = await pyjhora.resolvePlace(placeId);
      const label = description || geo.place_label;
      onChange(label);
      onResolved(geo, label);
      setStatus(`Resolved: ${geo.place_label}`);
    } catch (err) {
      setStatus(String((err as Error).message ?? err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div ref={wrapRef} className={cn("relative", className)}>
      <Input
        value={value}
        onChange={(e) => onInput(e.target.value)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setOpen(false);
            return;
          }
          if (e.key === "Enter" && open && suggestions.length > 0) {
            e.preventDefault();
            const first = suggestions[0];
            void resolve(first.place_id, first.description);
          }
        }}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
      />
      {open && suggestions.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 left-0 right-0 mt-1 border border-border rounded-md bg-popover shadow-lg max-h-48 overflow-auto"
        >
          {suggestions.map((s) => (
            <li
              key={s.place_id}
              role="option"
              className="px-3 py-2 text-sm cursor-pointer hover:bg-muted border-b border-border/50 last:border-0"
              onMouseDown={(e) => {
                e.preventDefault();
                void resolve(s.place_id, s.description);
              }}
            >
              {s.description}
            </li>
          ))}
        </ul>
      )}
      {(status || loading) && (
        <p className={cn("text-xs mt-1", status ? "text-muted-foreground" : "text-muted-foreground/70")}>
          {loading ? "Searching places…" : status}
        </p>
      )}
    </div>
  );
}
