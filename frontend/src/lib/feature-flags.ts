/** Client-side feature flags (VITE_* env vars). */
export const featureFlags = {
  /** Set VITE_ENABLE_AI_ASSISTANT=true to show the full AI chat UI. */
  aiAssistant: (import.meta.env.VITE_ENABLE_AI_ASSISTANT as string | undefined)?.trim() === "true",
} as const;
