import { getPyJHoraApiBase } from "@/lib/pyjhora/config";
import { parseApiErrorBody } from "@/lib/api-errors";
import type {
  AuthResponse,
  ResetPasswordResponse,
  SendOtpResponse,
  VerifyOtpResponse,
  VerifyResetOtpResponse,
} from "./types";

const AUTH_TOKEN_KEY = "jyotish:authToken";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getPyJHoraApiBase();
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(parseApiErrorBody(body, `Request failed (${res.status})`));
  }
  return body as T;
}

export function getStoredAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setStoredAuthToken(token: string | null): void {
  if (token) localStorage.setItem(AUTH_TOKEN_KEY, token);
  else localStorage.removeItem(AUTH_TOKEN_KEY);
}

export const authApi = {
  sendOtp(email: string) {
    return request<SendOtpResponse>("/api/auth/otp/send", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },

  verifyOtp(email: string, otp: string) {
    return request<VerifyOtpResponse>("/api/auth/otp/verify", {
      method: "POST",
      body: JSON.stringify({ email, otp }),
    });
  },

  signup(payload: {
    email: string;
    verification_token: string;
    username: string;
    password: string;
    confirm_password: string;
  }) {
    return request<AuthResponse>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  login(identifier: string, password: string) {
    return request<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    });
  },

  me(token: string) {
    return request<{ user: AuthResponse["user"] }>("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
  },

  forgotPassword(email: string) {
    return request<SendOtpResponse>("/api/auth/password/forgot", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },

  verifyResetOtp(email: string, otp: string) {
    return request<VerifyResetOtpResponse>("/api/auth/password/otp/verify", {
      method: "POST",
      body: JSON.stringify({ email, otp }),
    });
  },

  resetPassword(payload: {
    email: string;
    reset_token: string;
    new_password: string;
    confirm_new_password: string;
  }) {
    return request<ResetPasswordResponse>("/api/auth/password/reset", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
