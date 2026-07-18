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
  auth_username?: string;
  birth_input: Record<string, unknown>;
  user_info: Record<string, unknown>;
  student_context?: Record<string, unknown> | null;
  career_context?: Record<string, unknown> | null;
  meta: Record<string, unknown>;
  d1_table: Record<string, unknown>;
  divisional_charts: Record<string, unknown>;
  kp?: Record<string, unknown> | null;
  jaimini?: Record<string, unknown> | null;
  panchanga?: Record<string, unknown> | null;
  ashtakavarga?: Record<string, unknown> | null;
  shadbala?: Record<string, unknown> | null;
  vimshottari?: Record<string, unknown> | null;
  divisional_extended?: Record<string, unknown> | null;
  consolidated?: Record<string, unknown> | null;
  // Education analysis lives in the dedicated JyotishEducationAnalysis table,
  // fetched via profilesApi.educationAnalysis(profileId) — not on the profile.
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

/** DynamoDB chunk keys (SK suffix after PROFILE#{id}#). */
export const PROFILE_SECTION = {
  KP: "ANALYSIS#KP",
  JAIMINI: "ANALYSIS#JAIMINI",
  EXTENDED: "ANALYSIS#EXTENDED",
  CONSOLIDATED: "ANALYSIS#CONSOLIDATED",
  CAREER: "CONTEXT#CAREER",
} as const;

export interface PersistProfileSectionsPayload {
  sections: Record<string, Record<string, unknown>>;
}

export interface PersistProfileSectionsResponse {
  profile_id: string;
  saved_sections: string[];
}
