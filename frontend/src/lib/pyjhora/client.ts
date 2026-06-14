import type {
  AshtakavargaResponse,
  BirthInput,
  ConsolidatedRequest,
  DivisionalChartsResponse,
  GeocodeResponse,
  JaiminiResponse,
  KpResponse,
  PanchangaResponse,
  PlaceSuggestion,
  SavedChartResponse,
  ShadbalaResponse,
  StudentContext,
  TableResponse,
  UserInfo,
  VimshottariResponse,
} from "./types";
import { getPyJHoraApiBase } from "./config";

export const PYJHORA_LS_USER = "pyjhora_user_id";
export type { ConsolidatedRequest };
export { PYJHORA_API_BASE_DEFAULT, getPyJHoraApiBase } from "./config";

function apiBase(): string {
  return getPyJHoraApiBase();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${apiBase()}${path}`;
  const res = await fetch(url, init);
  const text = await res.text();
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`Not JSON (HTTP ${res.status}): ${text.slice(0, 400)}`);
  }
  if (!res.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? JSON.stringify((data as { detail: unknown }).detail)
        : text.slice(0, 400);
    const err = new Error(`HTTP ${res.status}: ${detail}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return data as T;
}

/** True when DynamoDB is not configured on the API (local dev without AWS). */
export function isDynamoUnavailableError(err: unknown): boolean {
  const msg = String((err as Error)?.message ?? err);
  return (
    msg.includes("503") ||
    msg.includes("DYNAMODB_TABLE_NAME") ||
    msg.includes("DynamoDBNotConfigured") ||
    msg.includes("AWS credentials not found")
  );
}

export function ensureUserId(existing?: string): string {
  const trimmed = existing?.trim();
  if (trimmed) return trimmed;
  const stored = localStorage.getItem(PYJHORA_LS_USER);
  if (stored) return stored;
  const id = "user-" + crypto.randomUUID().slice(0, 8);
  localStorage.setItem(PYJHORA_LS_USER, id);
  return id;
}

export const pyjhora = {
  apiBase,

  geocode: (location: string) =>
    request<GeocodeResponse>(`/api/geocode?location=${encodeURIComponent(location)}`),

  placesAutocomplete: (input: string) =>
    request<{ suggestions: PlaceSuggestion[] }>(
      `/api/places/autocomplete?input=${encodeURIComponent(input)}`,
    ),

  resolvePlace: (placeId: string) =>
    request<GeocodeResponse>(`/api/places/resolve?place_id=${encodeURIComponent(placeId)}`),

  birthChartTable: (body: BirthInput) =>
    request<TableResponse>("/api/birth-chart-table", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, response_format: "json" }),
    }),

  divisionalCharts: (body: BirthInput, factors?: string) => {
    const q = factors ? `?factors=${encodeURIComponent(factors)}` : "";
    return request<DivisionalChartsResponse>(`/api/divisional-charts${q}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  saveChart: (userId: string, userInfo: UserInfo, birthInput: BirthInput) =>
    request<SavedChartResponse>(`/api/users/${encodeURIComponent(userId)}/charts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_info: userInfo, birth_input: birthInput }),
    }),

  getSavedChart: (userId: string, chartId: string) =>
    request<SavedChartResponse>(
      `/api/users/${encodeURIComponent(userId)}/charts/${encodeURIComponent(chartId)}`,
    ),

  panchanga: (body: BirthInput) =>
    request<PanchangaResponse>("/api/panchanga", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  ashtakavarga: (body: BirthInput) =>
    request<AshtakavargaResponse>("/api/ashtakavarga", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  shadbala: (body: BirthInput) =>
    request<ShadbalaResponse>("/api/shadbala", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  jaimini: (body: BirthInput) =>
    request<JaiminiResponse>("/api/jaimini", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  vimshottari: (body: BirthInput) =>
    request<VimshottariResponse>("/api/vimshottari", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  kp: (body: BirthInput) =>
    request<KpResponse>("/api/kp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  consolidated: (req: ConsolidatedRequest) =>
    request<Record<string, unknown>>("/api/consolidated", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
};
