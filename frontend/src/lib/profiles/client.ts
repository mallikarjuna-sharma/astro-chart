import { getPyJHoraApiBase } from "@/lib/pyjhora/config";
import { getStoredAuthToken } from "@/lib/auth/client";
import { parseApiErrorBody } from "@/lib/api-errors";
import type {
  CreateProfilePayload,
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

  delete(profileId: string) {
    return request<{ status: string; profile_id: string }>(`/api/profiles/${profileId}`, {
      method: "DELETE",
    });
  },
};
