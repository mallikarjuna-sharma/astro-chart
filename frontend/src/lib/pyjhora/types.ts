/** Types aligned with pyJHora FastAPI schemas (api/schemas/chart.py, storage.py). */

export interface BirthInput {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
  place_label: string;
  latitude: number;
  longitude: number;
  timezone_offset_hours: number;
  ayanamsa?: string | null;
  use_true_nodes?: boolean;
  include_outer_planets?: boolean;
}

export interface UserInfo {
  display_name: string;
  email?: string | null;
  location_query?: string | null;
}

export interface StudentPreference {
  interested_in: string[];
  already_excel_at: string[];
  financial_constraints: boolean;
  risk_appetite: "LOW" | "MODERATE" | "HIGH";
}

export interface StudentContext {
  pob?: string | null;
  gender: "M" | "F" | "O";
  education_system: string;
  student_preference: StudentPreference;
}

export interface TableResponse {
  title: string;
  columns: string[];
  rows: (string | number | null)[][];
  meta: Record<string, unknown>;
}

export interface DivisionalHouse {
  rasi: number;
  rasi_name: string;
  bodies: string[];
}

export interface DivisionalChart {
  factor: number;
  name: string;
  houses: DivisionalHouse[];
}

export interface DivisionalChartsResponse {
  charts: DivisionalChart[];
  meta: Record<string, unknown>;
}

export interface SavedChartResponse {
  chart_id: string;
  user_id: string;
  user_info: UserInfo;
  birth_input: BirthInput;
  meta: Record<string, unknown>;
  d1_table: TableResponse;
  divisional_charts: DivisionalChartsResponse;
  created_at: string;
  updated_at: string;
}

export interface GeocodeResponse {
  latitude: number;
  longitude: number;
  place_label: string;
  timezone_offset_hours?: number;
  provider: string;
}

export interface PlaceSuggestion {
  place_id: string;
  description: string;
}

export interface PanchangaResponse {
  items: { label: string; value: string }[];
}

export interface AshtakavargaResponse {
  sav: { house: number; rasi: string; points: number }[];
  sav_total: number;
  bav: { contributor: string; houses: number[]; total: number }[];
}

export interface ShadbalaRow {
  planet: string;
  rupas: number;
  percentage: number;
}

export interface ShadbalaResponse {
  rows: ShadbalaRow[];
  strongest: string;
  weakest: string;
}

export interface JaiminiResponse {
  karakas: { karaka: string; planet: string }[];
  karakamsa: string;
  arudha_lagna: string;
  upapada_lagna: string;
  chara_dasha: { rasi: string; start_year: number; end_year: number; years: number }[];
  chara_dasha_error?: string;
}

export interface VimshottariResponse {
  current_mahadasha: string;
  current_antardasha: string;
  periods: { planet: string; start: string; end: string | null }[];
}

export interface KpRow {
  body: string;
  rasi: string;
  kp_number: number;
  sign_lord: string;
  star_lord: string;
  sub_lord: string;
  sub_sub_lord: string;
}

export interface KpResponse {
  rows: KpRow[];
}

export interface ConsolidatedRequest {
  birth_input: BirthInput;
  student_context?: StudentContext | null;
}

export interface ChartSession {
  userId: string;
  chartId?: string;
  userInfo: UserInfo;
  birthInput: BirthInput;
  studentContext: StudentContext;
  d1Table?: TableResponse;
  divisionalBasic?: DivisionalChartsResponse;
  divisionalExtended?: DivisionalChartsResponse;
  panchanga?: PanchangaResponse;
  ashtakavarga?: AshtakavargaResponse;
  shadbala?: ShadbalaResponse;
  jaimini?: JaiminiResponse;
  vimshottari?: VimshottariResponse;
  kp?: KpResponse;
  consolidated?: Record<string, unknown>;
  savedAt?: string;
}
