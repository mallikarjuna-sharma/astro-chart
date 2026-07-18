export interface AuthUser {
  user_id: string;
  email: string;
  username: string;
  email_verified: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface SendOtpResponse {
  message: string;
  expires_in_seconds: number;
  dev_otp?: string | null;
}

export interface VerifyOtpResponse {
  verification_token: string;
  message: string;
}

export interface VerifyResetOtpResponse {
  reset_token: string;
  message: string;
}

export interface ResetPasswordResponse {
  message: string;
}
