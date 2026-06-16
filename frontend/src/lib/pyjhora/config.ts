/** Production PyJHora API (Render). Override with VITE_PYJHORA_API_BASE only if needed. */
export const PYJHORA_API_BASE_DEFAULT = "https://pyjhora-api-8ni1.onrender.com";

export function getPyJHoraApiBase(): string {
  const fromEnv = (import.meta.env.VITE_PYJHORA_API_BASE as string | undefined)?.trim();
  const raw = fromEnv || PYJHORA_API_BASE_DEFAULT;
  return raw.replace(/\/$/, "");
}
