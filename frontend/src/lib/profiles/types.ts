export interface ProfileSummary {
  profile_id: string;
  profile_name: string;
  place_label: string;
  birth_local: string;
  created_at: string;
  updated_at: string;
}

export interface ProfileListResponse {
  profiles: ProfileSummary[];
  count: number;
  max_profiles: number;
}

export interface ProfileResponse {
  profile_id: string;
  profile_name: string;
  profile_key: string;
  user_id: string;
  birth_input: Record<string, unknown>;
  user_info: Record<string, unknown>;
  student_context?: Record<string, unknown> | null;
  career_context?: Record<string, unknown> | null;
  meta: Record<string, unknown>;
  d1_table: Record<string, unknown>;
  divisional_charts: Record<string, unknown>;
  consolidated?: Record<string, unknown> | null;
  education_analysis?: Record<string, unknown> | null;
  education_analysis_error?: string | null;
  career_timeline?: Record<string, unknown> | null;
  career_timeline_error?: string | null;
  created_at: string;
  updated_at: string;
  read_only: boolean;
}

export interface CreateProfilePayload {
  profile_name: string;
  birth_input: Record<string, unknown>;
  user_info: Record<string, unknown>;
  student_context?: Record<string, unknown> | null;
  career_context: Record<string, unknown>;
  enrich_llm_career?: boolean;
}
