import { getPyJHoraApiBase } from "@/lib/pyjhora/config";
import { getStoredAuthToken } from "@/lib/auth/client";
import { parseApiErrorBody } from "@/lib/api-errors";
import type { EducationAnalysisResponse } from "@/lib/pyjhora/types";
import type {
  BusinessPredictionResponse,
  CareerTimelineResponse,
  PucAnalysisResponse,
} from "@/lib/pyjhora/types";
import type {
  CreateProfilePayload,
  PersistProfileSectionsPayload,
  PersistProfileSectionsResponse,
  ProfileListResponse,
  ProfileResponse,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getStoredAuthToken();
  const res = await fetch(`${getPyJHoraApiBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(parseApiErrorBody(body, `Request failed (${res.status})`));
  }
  return body as T;
}

export const profilesApi = {
  list() {
    return request<ProfileListResponse>("/api/profiles");
  },

  get(profileId: string) {
    return request<ProfileResponse>(`/api/profiles/${profileId}`);
  },

  create(payload: CreateProfilePayload) {
    return request<ProfileResponse>("/api/profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async delete(profileId: string) {
    const token = getStoredAuthToken();
    const res = await fetch(`${getPyJHoraApiBase()}/api/profiles/${profileId}`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    const body = await res.json().catch(() => ({}));
    // Profile may have been removed directly in the DB — treat as already deleted.
    if (res.status === 404 && (body as { detail?: string }).detail === "Profile not found.") {
      return { status: "deleted", profile_id: profileId };
    }
    if (!res.ok) {
      throw new Error(parseApiErrorBody(body, `Request failed (${res.status})`));
    }
    return body as { status: string; profile_id: string };
  },

  persistSections(profileId: string, payload: PersistProfileSectionsPayload) {
    return request<PersistProfileSectionsResponse>(`/api/profiles/${profileId}/sections`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Cache-or-compute the career field report for a profile. Returns the stored
   * analysis when present; otherwise the engine runs (30-60s), the four LLM
   * payloads are persisted in DynamoDB, and the fresh result is returned.
   * `userJson` is optional — the API loads consolidated chart data from the
   * profile when omitted.
   */
  educationAnalysis(
    profileId: string,
    userJson?: Record<string, unknown>,
    opts?: { refresh?: boolean },
  ) {
    const q = opts?.refresh ? "?refresh=true" : "";
    return request<EducationAnalysisResponse>(
      `/api/profiles/${profileId}/education-analysis${q}`,
      {
        method: "POST",
        body: JSON.stringify({ user_json: userJson ?? null }),
      },
    );
  },

  /**
   * Cache-or-compute the job timeline for a profile. Chart data is loaded
   * server-side from the profile — only send optional career_context overrides.
   */
  careerTimeline(
    profileId: string,
    opts?: {
      careerContext?: Record<string, unknown>;
      enrichLlm?: boolean;
      refresh?: boolean;
    },
  ) {
    const q = opts?.refresh ? "?refresh=true" : "";
    return request<CareerTimelineResponse>(
      `/api/profiles/${profileId}/career-timeline${q}`,
      {
        method: "POST",
        body: JSON.stringify({
          career_context: opts?.careerContext ?? null,
          enrich_llm: opts?.enrichLlm ?? true,
        }),
      },
    );
  },

  /**
   * Cache-or-compute business prediction for a profile. Chart data is loaded
   * server-side from the profile.
   */
  businessPrediction(
    profileId: string,
    opts?: { ventureType?: string; yearsAhead?: number; refresh?: boolean },
  ) {
    const q = opts?.refresh ? "?refresh=true" : "";
    return request<BusinessPredictionResponse>(
      `/api/profiles/${profileId}/business-prediction${q}`,
      {
        method: "POST",
        body: JSON.stringify({
          venture_type: opts?.ventureType ?? "business",
          years_ahead: opts?.yearsAhead ?? 15,
        }),
      },
    );
  },

  /**
   * Cache-or-compute PUC stream analysis for a profile. Chart data is loaded
   * server-side from the profile — no user_json required.
   */
  pucAnalysis(profileId: string, opts?: { refresh?: boolean }) {
    const q = opts?.refresh ? "?refresh=true" : "";
    return request<PucAnalysisResponse>(
      `/api/profiles/${profileId}/education-analysis/puc${q}`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    );
  },
};
