/** Labels for FastAPI/Pydantic validation `loc` fields — keep in sync with api/auth_validation.py */
const FIELD_LABELS: Record<string, string> = {
  email: "Email",
  otp: "Verification code",
  username: "Username",
  password: "Password",
  confirm_password: "Confirm password",
  identifier: "Email or username",
  verification_token: "Verification token",
  profile_name: "Profile name",
};

type ValidationErr = {
  loc?: unknown[];
  msg?: string;
  type?: string;
  ctx?: Record<string, unknown>;
};

function fieldLabel(loc: unknown[] | undefined): string {
  const field = loc?.length ? String(loc[loc.length - 1]) : "field";
  return FIELD_LABELS[field] ?? field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatOneValidationError(item: unknown): string {
  if (typeof item === "string") return item;
  if (!item || typeof item !== "object") return "";

  const err = item as ValidationErr;
  const label = fieldLabel(err.loc);
  const errType = err.type ?? "";
  const ctx = err.ctx ?? {};

  if (errType === "string_too_short") {
    const min = ctx.min_length;
    return `${label} must be at least ${min} characters.`;
  }
  if (errType === "string_too_long") {
    const max = ctx.max_length;
    return `${label} must be at most ${max} characters.`;
  }
  if (errType === "value_error") {
    let msg = err.msg ?? "";
    if (msg.startsWith("Value error, ")) msg = msg.slice("Value error, ".length);
    return msg || `${label} is invalid.`;
  }
  if (errType === "missing" || errType === "value_error.missing") {
    return `${label} is required.`;
  }

  const msg = err.msg ?? "";
  if (msg.startsWith("String should have at least")) {
    const min = ctx.min_length;
    return `${label} must be at least ${min} characters.`;
  }
  if (msg) return `${label}: ${msg}`;
  return `${label} is invalid.`;
}

/** Parse FastAPI error JSON into a single user-facing message. */
export function parseApiErrorBody(body: unknown, fallback = "Request failed"): string {
  if (!body || typeof body !== "object") return fallback;

  const record = body as { detail?: unknown; errors?: unknown };
  const errors = Array.isArray(record.errors)
    ? record.errors
    : Array.isArray(record.detail)
      ? record.detail
      : null;

  if (errors?.length) {
    const messages = errors.map(formatOneValidationError).filter(Boolean);
    if (messages.length) return messages.join(" ");
  }

  if (typeof record.detail === "string") return record.detail;
  return fallback;
}
