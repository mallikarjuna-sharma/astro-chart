/** Keep in sync with api/auth_validation.py */

export const AUTH_PASSWORD_MIN_LENGTH = 8;
export const AUTH_PASSWORD_MAX_LENGTH = 128;
export const AUTH_USERNAME_MIN_LENGTH = 3;
export const AUTH_USERNAME_MAX_LENGTH = 32;
export const AUTH_OTP_LENGTH = 4;
export const AUTH_IDENTIFIER_MIN_LENGTH = 3;

export type ValidationResult = { ok: true } | { ok: false; message: string };

export function validateUsername(username: string): ValidationResult {
  const normalized = username.trim().toLowerCase();
  if (!normalized) {
    return { ok: false, message: "Username is required." };
  }
  if (normalized.length < AUTH_USERNAME_MIN_LENGTH) {
    return {
      ok: false,
      message: `Username must be at least ${AUTH_USERNAME_MIN_LENGTH} characters.`,
    };
  }
  if (normalized.length > AUTH_USERNAME_MAX_LENGTH) {
    return {
      ok: false,
      message: `Username must be at most ${AUTH_USERNAME_MAX_LENGTH} characters.`,
    };
  }
  if (!/^[a-z0-9._]+$/.test(normalized)) {
    return {
      ok: false,
      message: "Username may only contain letters, numbers, dots, and underscores.",
    };
  }
  return { ok: true };
}

export function validatePassword(password: string): ValidationResult {
  if (!password) {
    return { ok: false, message: "Password is required." };
  }
  if (password.length < AUTH_PASSWORD_MIN_LENGTH) {
    return {
      ok: false,
      message: `Password must be at least ${AUTH_PASSWORD_MIN_LENGTH} characters.`,
    };
  }
  if (password.length > AUTH_PASSWORD_MAX_LENGTH) {
    return {
      ok: false,
      message: `Password must be at most ${AUTH_PASSWORD_MAX_LENGTH} characters.`,
    };
  }
  return { ok: true };
}

export function validateSignupCredentials(
  username: string,
  password: string,
  confirmPassword: string,
): ValidationResult {
  const usernameResult = validateUsername(username);
  if (!usernameResult.ok) return usernameResult;

  const passwordResult = validatePassword(password);
  if (!passwordResult.ok) return passwordResult;

  const confirmResult = validatePassword(confirmPassword);
  if (!confirmResult.ok) {
    return { ok: false, message: "Confirm password must meet the same requirements." };
  }

  if (password !== confirmPassword) {
    return { ok: false, message: "Passwords do not match." };
  }

  return { ok: true };
}

export function validateLoginInput(identifier: string, password: string): ValidationResult {
  if (!identifier.trim()) {
    return { ok: false, message: "Enter your email or username." };
  }
  if (identifier.trim().length < AUTH_IDENTIFIER_MIN_LENGTH) {
    return {
      ok: false,
      message: `Email or username must be at least ${AUTH_IDENTIFIER_MIN_LENGTH} characters.`,
    };
  }
  return validatePassword(password);
}

export function validateOtp(otp: string): ValidationResult {
  if (otp.length !== AUTH_OTP_LENGTH) {
    return { ok: false, message: `Enter the ${AUTH_OTP_LENGTH}-digit verification code.` };
  }
  if (!/^\d+$/.test(otp)) {
    return { ok: false, message: "Verification code must contain only digits." };
  }
  return { ok: true };
}
