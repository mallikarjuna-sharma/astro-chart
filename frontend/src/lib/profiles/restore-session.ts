import { defaultCareerContext } from "@/components/career/CareerContextForm";
import { computeExtendedAnalysis } from "@/lib/pyjhora/pipeline";
import { normalizeTableResponse } from "@/lib/pyjhora/normalize";
import { defaultStudentContext } from "@/lib/pyjhora/session";
import type {
  BirthInput,
  CareerContextInput,
  ChartSession,
  StudentContext,
  UserInfo,
} from "@/lib/pyjhora/types";
import type { ProfileResponse } from "./types";

/** True when extended APIs (KP, consolidated, etc.) are present in session. */
export function isChartSessionHydrated(session: ChartSession | null | undefined): boolean {
  return !!(session?.birthInput && session.consolidated && session.kp);
}

/**
 * Build a full chart session from a saved profile: runs extended API calls
 * (KP, panchanga, consolidated, …) without re-persisting analyses to DynamoDB.
 */
export async function restoreProfileToChartSession(
  profile: ProfileResponse,
  onProgress?: (step: string) => void,
): Promise<ChartSession> {
  const birthInput = profile.birth_input as BirthInput;
  const userInfo = profile.user_info as UserInfo;
  const studentContext =
    (profile.student_context as StudentContext | null) ?? defaultStudentContext();
  const careerContext =
    (profile.career_context as CareerContextInput | null) ??
    defaultCareerContext(null);

  const d1Table = profile.d1_table
    ? normalizeTableResponse(
        profile.d1_table as ChartSession["d1Table"],
        profile.meta,
      )
    : undefined;
  const divisionalBasic = profile.divisional_charts as ChartSession["divisionalBasic"];

  onProgress?.("Loading extended chart data…");
  const extended = await computeExtendedAnalysis(birthInput, studentContext, onProgress);

  let consolidated = extended.consolidated;
  if (profile.career_context && Object.keys(profile.career_context).length > 0) {
    consolidated = { ...consolidated, career_context: profile.career_context };
  }

  return {
    userId: profile.user_id,
    chartId: profile.profile_id,
    userInfo,
    birthInput,
    studentContext,
    d1Table,
    divisionalBasic,
    divisionalExtended: extended.divisionalExtended,
    panchanga: extended.panchanga,
    ashtakavarga: extended.ashtakavarga,
    shadbala: extended.shadbala,
    jaimini: extended.jaimini,
    vimshottari: extended.vimshottari,
    kp: extended.kp,
    consolidated,
    careerContextInput: careerContext,
    savedAt: profile.updated_at,
  };
}
