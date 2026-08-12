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
  phone?: string | null;
  location_query?: string | null;
  notes?: string | null;
  gender?: "M" | "F" | null;
  education_system?: string | null;
  student_preference?: StudentPreference | null;
}

export interface SavedChartSummary {
  chart_id: string;
  user_id: string;
  user_info: UserInfo;
  birth_local: string;
  place_label: string;
  created_at: string;
  updated_at: string;
}

export interface SavedChartListResponse {
  charts: SavedChartSummary[];
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

/** One row of the D-1 body table: Lagna, grahas, Maandi/Gulika, special lagnas. */
export interface D1BodyRow {
  body: string;
  /** Chara karaka short code ("AK", "AmK", …); empty when the body has none. */
  karaka: string;
  retrograde: boolean;
  /** Formatted as `15 Li 11' 25.29"`. */
  longitude: string;
  longitude_decimal: number;
  nakshatra: string;
  nakshatra_full: string;
  pada: number;
  rasi: string;
  rasi_full: string;
  navamsa: string;
  navamsa_full: string;
}

export interface D1BodiesResponse {
  rows: D1BodyRow[];
  meta: Record<string, unknown>;
}

export interface AshtakavargaResponse {
  /** One row per rasi (Aries..Pisces); `house` is the backend's "H1".."H12" label. */
  sav: { house: string; rasi: string; points: number }[];
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
  track?: string;
  label?: string;
  ug_program?: string;
  ug_niche?: string;
  pg_program?: string;
  pg_niche?: string;
  phd_program?: string;
  phd_niche?: string;
  admission_exams?: string[];
  career_paths?: string[];
  institutions?: string[];
  available_at?: Record<string, boolean | string[] | null>;
}

export interface WealthPotential {
  wealth_potential?: string;
  wealth_connections?: string[];
  wealth_note?: string;
}

export interface GeoSuitability {
  /** Label string e.g. "International / Relocation" (backend key name) */
  geo_suitability?: string;
  geo_foreign_pct?: number;
  geo_domestic_pct?: number;
  geo_note?: string;
}

export interface BurnoutRisk {
  burnout_risk?: string;
  stress_flags?: string[];
  burnout_note?: string;
}

export interface MicroNiches {
  micro_niches?: string[];
  niche_driver?: string;
  driver_planet?: string;
}

export interface ConfidenceMatrix {
  knrao_pct?: number;
  kp_pct?: number;
  jaimini_pct?: number;
  parashara_pct?: number;
  sbc_pct?: number;
  alignment_confidence?: number;
}

export interface AcademicPathStage {
  stage: string;
  label?: string;
  strength_label?: string;
  recommended?: boolean;
}

export interface AcademicPath {
  depth_label?: string;
  path_stages?: AcademicPathStage[];
}

export interface InstitutionalTier {
  tier?: string;
  tier_key?: string;
  archetype?: string;
  target_examples?: string[];
}

export interface ExplainabilityMatrix {
  structural_friction_flag?: string;
  paradigm_spread?: number;
}

export interface SbcDetail {
  career_nakshatras?: string[];
  key_protections?: string[];
  key_obstructions?: string[];
}

export interface ChartType {
  is_cluster?: boolean;
  cluster_label?: string;
  domain_clusters?: Record<string, string[]>;
}

export interface CorporateEntrepreneurial {
  corporate_pct?: number;
  entrep_pct?: number;
  style_label?: string;
  style_note?: string;
}

export interface EducationFieldResult {
  field_id: string;
  field_label: string;
  domain: string;
  final_score: number;
  llm_parent_reason?: string;
  llm_astrological_reason?: string;
  parent_friendly_explanation?: string;
  astrological_reason?: string;
  llm_parent_summary?: string;
  llm_selection_rationale?: string;
  llm_group?: string;
  llm_rank?: number;
  gap_breakdown?: Record<string, number>;
  top_affinity_planets?: Record<string, number>;
  top_karakas?: string[];
  verified_factors?: string;
  boost_pct?: number;
  pre_norm_score?: number;
  norm_note?: string;
  timing_band?: string;
  sbc_event_score?: number;
  smi?: number;
  sbc_exam_date?: string;
  sbc_detail?: SbcDetail;
  wealth_potential?: WealthPotential;
  geo_suitability?: GeoSuitability;
  burnout_risk?: BurnoutRisk;
  micro_niches?: MicroNiches;
  confidence_matrix?: ConfidenceMatrix;
  academic_path?: AcademicPath;
  institutional_tier?: InstitutionalTier;
  explainability_matrix?: ExplainabilityMatrix;
  chart_type?: ChartType;
  score_components?: {
    blended?: number;
    gap_boost_pct?: number;
    gap_penalty_pct?: number;
  };
  registry?: EducationFieldRegistry;
}

export interface CareerOutcome {
  primary_opportunity: string;
  peak_md_lord: string;
  peak_years: string;
  growth_arc: string;
}

export interface CareerTrajectoryPoint {
  label: string;
  score: number;
  color: string;
  event_type: string;
}

export interface CareerCalendarEntry {
  year: number;
  event_type: string;
  ad_lord: string;
  score: number;
  color: string;
}

export interface CareerMDArc {
  md_lord: string;
  start_date: string;
  end_date: string;
  narrative: string;
}

export interface CareerForeignMeta {
  total: number;
  high: number;
  moderate: number;
  mild: number;
  peak_score: number;
  peak_period: string;
  geo_summary: string;
}

export interface CareerForeignOpportunity {
  md_lord?: string;
  ad_lord?: string;
  start_date?: string;
  end_date?: string;
  foreign_score?: number;
  geo_affinity?: string;
  duration_type?: string;
  narrative?: string;
  active_houses?: number[] | null;
  drivers?: string[];
  warnings?: string[];
  [k: string]: unknown;
}

export interface CareerPratyantardasha {
  pd_lord?: string;
  start_date?: string;
  end_date?: string;
  pd_score?: number;
  hint?: string;
  llm_narrative_html?: string;
  [k: string]: unknown;
}

export interface CareerTimelineBlock {
  md_lord: string;
  ad_lord: string;
  start_date: string;
  end_date: string;
  event_type: string;
  secondary_event_type?: string;
  career_score: number;
  confidence?:
    | string
    | {
        score?: number;
        tier?: string;
        label?: string;
        caveats?: string[];
        retro_validation?: Record<string, unknown>;
      };
  is_current?: boolean;
  is_past?: boolean;
  is_primary_opportunity?: boolean;
  domain_tag?: string;
  career_track?: string;
  active_houses?: number[];
  narrative_hint?: string;
  md_narrative?: string;
  md_arc_html?: string;
  // Two segregated narrative layers (2026-07-19): plain-language (client-facing)
  // and technical astro-explanation. `llm_ad_narrative_html` is the legacy combined blob.
  llm_plain_language_html?: string;
  llm_astro_explanation_html?: string;
  llm_ad_narrative_html?: string;
  jaimini_role?: string;
  workplace_dynamics?: Record<string, unknown>;
  salary_range?: Record<string, unknown>;
  skill_recommendations?: string[];
  remedies?: string[];
  event_remedies?: unknown[];
  transit_flags?: unknown[];
  pratyantardashas?: CareerPratyantardasha[];
  foreign_opportunity?: CareerForeignOpportunity;
  sub_scores?: Record<string, number>;
  [k: string]: unknown;
}

export interface CareerContextInput {
  employment_status?: string;
  designation?: string;
  years_experience?: number;
  industry_sector?: string;
  company_type?: string;
  desired_outcome?: string;
  join_date?: string;
  last_promotion_date?: string;
  last_hike_date?: string;
  geographic_preference?: string;
  actively_looking?: boolean;
  on_notice_period?: boolean;
  is_family_business?: boolean;
}

export interface CareerTimelineRequest {
  user_json: Record<string, unknown>;
  career_context?: CareerContextInput;
  enrich_llm?: boolean;
}

export interface CareerTimelineResponse {
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
    active_dasha_lord?: string;
  };
  career_context: Record<string, unknown> & { warnings?: string[] };
  outcome: CareerOutcome;
  trajectory: CareerTrajectoryPoint[];
  calendar: CareerCalendarEntry[];
  md_arcs: CareerMDArc[];
  blocks: CareerTimelineBlock[];
  foreign_opportunities: CareerForeignOpportunity[];
  foreign_meta: CareerForeignMeta;
  micro_timing: Record<string, unknown>;
  llm_enriched: boolean;
}

export interface AiDiagnostics {
  success?: string;
  error?: string;
}

export interface EducationAnalysisResponse {
  analysis_type?: "ug";
  engine_version: string;
  generated_at: string;
  default_tab?: "puc" | "ug" | null;
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
    peak_career_dasha?: string;
    macro_identity?: string;
    confidence?: string;
    career_phase?: string;
  };
  // Frozen html-payload-contract v1 — four JSON payloads (rendered as React,
  // no server-side HTML):
  results: EducationFieldResult[]; // payload 1
  macro_clusters?: Record<string, unknown>[]; // payload 2
  report: Record<string, unknown>; // payload 3 — 14-section narrative
  chart_facts?: Record<string, unknown>; // payload 4
  // Back-compat / convenience:
  fields: EducationFieldResult[]; // alias of `results`
  report_bundle?: Record<string, unknown> | null;
  career_field_report?: Record<string, unknown> | null;
  profile_id?: string | null;
  user_id?: string | null;
  cached?: boolean | null;
  AI?: AiDiagnostics | null;
}

export interface PucAnalysisResponse {
  analysis_type?: "puc";
  engine_version: string;
  generated_at: string;
  default_tab?: "puc" | "ug" | null;
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
    school_board?: string;
  };
  report: Record<string, unknown>;
  stream_narrative?: Record<string, unknown> | null;
  AI?: AiDiagnostics | null;
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
  pucAnalysis?: PucAnalysisResponse;
  pucAnalysisError?: string;
  careerTimeline?: CareerTimelineResponse;
  careerTimelineError?: string;
  careerContextInput?: CareerContextInput;
  savedAt?: string;
}

/** POST /api/prashna — horary chart at question moment. */
export interface PrashnaRequest {
  question: string;
  category: string;
  moment?: string;
  city?: string;
  lat?: number;
  lon?: number;
  natal_lagna_sign?: string;
  natal_moon_sign?: string;
  natal_lagna_lord?: string;
  natal_atmakaraka?: string;
  natal_yogas?: string[];
}

export interface PrashnaFactor {
  // New engine emits name/value/polarity; older payloads used `factor`.
  name?: string;
  value?: string;
  factor?: string;
  polarity?: "affirm" | "deny" | "neutral" | string;
  weight: string;
  detail: string;
}

export interface PrashnaPlanetSnapshot {
  sign?: string;
  degree?: number;
  house?: number;
  nakshatra?: string;
  sub_lord?: string;
  retrograde?: boolean;
}

export interface PrashnaResponse {
  question: string;
  category: string;
  category_label: string;
  moment: string;
  city: string;
  verdict: "YES" | "NO" | "CONDITIONAL" | "UNCERTAIN" | string;
  verdict_label?: string;
  verdict_leaning?: "YES" | "NO" | string;
  binary_answer?: "YES" | "NO" | string;
  confidence: number;
  confidence_pct?: number;
  confidence_band: string;
  kp_sublord_planet: string;
  kp_sublord_verdict: string;
  kp_signifies_affirm: boolean;
  moon_status: string;
  moon_void: boolean;
  timing_estimate: string;
  timing_unit: string;
  affirm_significators: string[];
  deny_significators: string[];
  lagna_sign: string;
  lagna_lord: string;
  moon_sign: string;
  moon_nakshatra: string;
  factors: PrashnaFactor[];
  classical_rules: string[];
  classical_rules_fired?: string[];
  denial_rules_fired?: string[];
  afflicted_planets?: string[];
  internal_conflict_notes?: string[];
  score_semantics?: string;
  moon_status_caveat?: string;
  kp_joint_verdict?: string;
  tajika_aspect_note?: string;
  remedies: string[];
  planets: Record<string, PrashnaPlanetSnapshot>;
  house_lords: Record<string, string>;
  kp_cusp_sublords: Record<string, string>;
  natal_context_applied: boolean;
  natal_notes: string[];
  html_path?: string | null;
}

export interface PrashnaCategoryMeta {
  key: string;
  label: string;
  primary_house: number;
  example: string;
}

export interface PrashnaCategoriesResponse {
  categories: PrashnaCategoryMeta[];
}
