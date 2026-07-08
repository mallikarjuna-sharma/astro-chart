import { normalizeTableResponse } from "@/lib/pyjhora/normalize";
import { defaultStudentContext } from "@/lib/pyjhora/session";
import { defaultCareerContext } from "@/components/career/CareerContextForm";
import type { ChartSession, StudentContext, UserInfo } from "@/lib/pyjhora/types";
import type { ProfileResponse } from "./types";

/** Profile has full chart + analysis payloads persisted in DynamoDB. */
export function profileIsFullyPersisted(profile: ProfileResponse): boolean {
  return !!(
    profile.d1_table &&
    Object.keys(profile.d1_table).length > 0 &&
    profile.kp &&
    profile.consolidated
  );
}

/** Build chart session from DB only — no API recomputation. */
export function profileToChartSession(profile: ProfileResponse): ChartSession {
  const birthInput = profile.birth_input as ChartSession["birthInput"];
  const userInfo = profile.user_info as UserInfo;
  const studentContext =
    (profile.student_context as StudentContext | null) ?? defaultStudentContext();
  const careerContext =
    (profile.career_context as ChartSession["careerContextInput"]) ??
    defaultCareerContext(null);

  const d1Table = profile.d1_table
    ? normalizeTableResponse(
        profile.d1_table as ChartSession["d1Table"],
        profile.meta,
      )
    : undefined;

  let consolidated = profile.consolidated as ChartSession["consolidated"];
  const profileName = profile.profile_name?.trim() || userInfo.display_name?.trim();
  if (consolidated && profileName) {
    const sc = (consolidated.student_context as Record<string, unknown> | undefined) ?? {};
    consolidated = {
      ...consolidated,
      profile_name: profileName,
      user_info: userInfo,
      student_context: { ...sc, student_name: profileName, name: profileName },
    };
  }
  if (consolidated && profile.career_context && Object.keys(profile.career_context).length > 0) {
    consolidated = { ...consolidated, career_context: profile.career_context };
  }

  return {
    userId: profile.user_id,
    chartId: profile.profile_id,
    userInfo,
    birthInput,
    studentContext,
    d1Table,
    divisionalBasic: profile.divisional_charts as ChartSession["divisionalBasic"],
    divisionalExtended: profile.divisional_extended as ChartSession["divisionalExtended"],
    panchanga: profile.panchanga as ChartSession["panchanga"],
    ashtakavarga: profile.ashtakavarga as ChartSession["ashtakavarga"],
    shadbala: profile.shadbala as ChartSession["shadbala"],
    jaimini: profile.jaimini as ChartSession["jaimini"],
    vimshottari: profile.vimshottari as ChartSession["vimshottari"],
    kp: profile.kp as ChartSession["kp"],
    consolidated,
    educationAnalysis: profile.education_analysis as ChartSession["educationAnalysis"],
    educationAnalysisError: profile.education_analysis
      ? undefined
      : profile.education_analysis_error ?? undefined,
    careerTimeline: profile.career_timeline as ChartSession["careerTimeline"],
    careerTimelineError: profile.career_timeline
      ? undefined
      : profile.career_timeline_error ?? undefined,
    careerContextInput: careerContext,
    savedAt: profile.updated_at,
  };
}
