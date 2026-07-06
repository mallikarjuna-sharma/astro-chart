import type { ChartSession, StudentContext, UserInfo } from "@/lib/pyjhora/types";
import type { ProfileResponse } from "./types";
import { defaultStudentContext } from "@/lib/pyjhora/session";

export function profileToChartSession(profile: ProfileResponse): ChartSession {
  const birthInput = profile.birth_input as ChartSession["birthInput"];
  const userInfo = profile.user_info as UserInfo;
  const studentContext = (profile.student_context as StudentContext | null) ?? defaultStudentContext();

  return {
    userId: profile.user_id,
    chartId: profile.profile_id,
    userInfo,
    birthInput,
    studentContext,
    d1Table: profile.d1_table as ChartSession["d1Table"],
    divisionalBasic: profile.divisional_charts as ChartSession["divisionalBasic"],
    consolidated: profile.consolidated ?? undefined,
    educationAnalysis: profile.education_analysis as ChartSession["educationAnalysis"],
    educationAnalysisError: profile.education_analysis_error ?? undefined,
    careerTimeline: profile.career_timeline as ChartSession["careerTimeline"],
    careerTimelineError: profile.career_timeline_error ?? undefined,
    careerContextInput: profile.career_context as ChartSession["careerContextInput"],
    savedAt: profile.updated_at,
  };
}
