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

export interface EducationFieldRegistry {
  description?: string;
  specialization?: string;
  niche?: string;
  ug_program?: string;
  ug_niche?: string;
  pg_program?: string;
  pg_niche?: string;
  phd_program?: string;
  phd_niche?: string;
  admission_exams?: string[];
  career_paths?: string[];
  institutions?: string[];
}

export interface EducationFieldResult {
  field_id: string;
  field_label: string;
  domain: string;
  final_score: number;
  llm_parent_reason?: string;
  llm_astrological_reason?: string;
  llm_parent_summary?: string;
  llm_selection_rationale?: string;
  llm_group?: string;
  llm_rank?: number;
  gap_breakdown?: Record<string, number>;
  top_affinity_planets?: Record<string, number>;
  score_components?: {
    blended?: number;
    gap_boost_pct?: number;
    gap_penalty_pct?: number;
  };
  registry?: EducationFieldRegistry;
}

export interface EducationAnalysisResponse {
  engine_version: string;
  generated_at: string;
  student: {
    name?: string;
    dob?: string;
    birth_place?: string;
    gender?: string;
    current_age?: number;
    lagna_sign?: string;
    lagna_lord?: string;
    atmakaraka?: string;
    amatyakaraka?: string;
    h10_lord?: string;
    karakamsha?: string;
    yogas?: string[];
    school_board?: string;
    risk_appetite?: string;
  };
  summary: {
    parent_overview?: string;
    astro_overview?: string;
    active_dasha_lord?: string;
  };
  fields: EducationFieldResult[];
  report: Record<string, unknown>;
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
  educationAnalysis?: EducationAnalysisResponse;
  educationAnalysisError?: string;
  savedAt?: string;
}
