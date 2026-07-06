import type { BirthInput, ChartSession, StudentContext, UserInfo } from "./types";
import { isDynamoUnavailableError, pyjhora, PYJHORA_LS_USER } from "./client";
import { normalizeTableResponse } from "./normalize";
import { saveChartSession } from "./session";
import { studentContextFromUserInfo } from "./user-profile";
import { syncUserProfileFromUserInfo } from "@/stores/profile-sync";

export interface GenerateChartsOptions {
  userId: string;
  userInfo: UserInfo;
  birthInput: BirthInput;
  studentContext: StudentContext;
  onProgress?: (step: string) => void;
}

export interface GenerateChartsResult {
  session: ChartSession;
  /** False when DynamoDB was unavailable and charts were computed without persisting. */
  persisted: boolean;
}

export async function computeExtendedAnalysis(
  birthInput: BirthInput,
  studentContext: StudentContext,
  onProgress?: (step: string) => void,
  options?: { runEducationAnalysis?: boolean },
) {
  onProgress?.("Loading extended vargas (D10, D16, D24, D60, D81)…");
  const divisionalExtended = await pyjhora.divisionalCharts(birthInput, "10,16,24,60,81");

  onProgress?.("Panchanga…");
  const panchanga = await pyjhora.panchanga(birthInput);

  onProgress?.("Ashtakavarga…");
  const ashtakavarga = await pyjhora.ashtakavarga(birthInput);

  onProgress?.("Shadbala…");
  const shadbala = await pyjhora.shadbala(birthInput);

  onProgress?.("Jaimini…");
  const jaimini = await pyjhora.jaimini(birthInput);

  onProgress?.("Vimshottari…");
  const vimshottari = await pyjhora.vimshottari(birthInput);

  onProgress?.("KP system…");
  const kp = await pyjhora.kp(birthInput);

  onProgress?.("Consolidated export…");
  const consolidated = await pyjhora.consolidated({
    birth_input: birthInput,
    student_context: studentContext,
  });

  let educationAnalysis;
  let educationAnalysisError: string | undefined;
  if (options?.runEducationAnalysis) {
    onProgress?.("Career & education analysis (LLM)…");
    try {
      educationAnalysis = await pyjhora.educationAnalysis(consolidated);
    } catch (err) {
      educationAnalysisError = String((err as Error)?.message ?? err);
    }
  }

  return {
    divisionalExtended,
    panchanga,
    ashtakavarga,
    shadbala,
    jaimini,
    vimshottari,
    kp,
    consolidated,
    educationAnalysis,
    educationAnalysisError,
  };
}

async function computeAllCharts(
  birthInput: BirthInput,
  studentContext: StudentContext,
  onProgress?: (step: string) => void,
) {
  onProgress?.("Loading divisional charts (D1–D9)…");
  const divisionalBasic = await pyjhora.divisionalCharts(birthInput);

  const extended = await computeExtendedAnalysis(birthInput, studentContext, onProgress, {
    runEducationAnalysis: true,
  });

  return { divisionalBasic, ...extended };
}

/**
 * Save to DynamoDB when available, then load all chart/analysis payloads.
 * Falls back to compute-only (no DB) when DynamoDB is not configured — same as
 * legacy index.html "Show chart" without "Save to database".
 */
export async function saveAndGenerateCharts(opts: GenerateChartsOptions): Promise<GenerateChartsResult> {
  const { userId, userInfo, birthInput, studentContext, onProgress } = opts;

  const skipPersist =
    (import.meta.env.VITE_SKIP_CHART_PERSIST as string | undefined)?.trim() === "true";

  let persisted = false;
  let chartId: string | undefined;
  let sessionUserInfo = userInfo;
  let sessionBirthInput = birthInput;
  let d1Table: ChartSession["d1Table"];
  let divisionalBasic;
  let extended;

  if (skipPersist) {
    onProgress?.("Computing charts locally (DynamoDB save skipped)…");
    chartId = `local-${Date.now()}`;
    const all = await computeAllCharts(birthInput, studentContext, onProgress);
    divisionalBasic = all.divisionalBasic;
    extended = all;
  } else {
    onProgress?.("Saving chart to database…");
    try {
      const saved = await pyjhora.saveChart(userId, userInfo, birthInput);
      persisted = true;
      chartId = saved.chart_id;
      sessionUserInfo = saved.user_info;
      sessionBirthInput = saved.birth_input;
      d1Table = normalizeTableResponse(saved.d1_table, saved.meta);
      divisionalBasic = saved.divisional_charts;
      extended = await computeExtendedAnalysis(birthInput, studentContext, onProgress, {
        runEducationAnalysis: true,
      });
    } catch (err) {
      if (!isDynamoUnavailableError(err)) throw err;
      onProgress?.("Database unavailable — computing charts locally…");
      chartId = `local-${Date.now()}`;
      const all = await computeAllCharts(birthInput, studentContext, onProgress);
      divisionalBasic = all.divisionalBasic;
      extended = all;
    }
  }

  const session: ChartSession = {
    userId,
    chartId,
    userInfo: sessionUserInfo,
    birthInput: sessionBirthInput,
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
    consolidated: extended.consolidated,
    educationAnalysis: extended.educationAnalysis,
    educationAnalysisError: extended.educationAnalysisError,
    savedAt: new Date().toISOString(),
  };

  saveChartSession(session);
  return { session, persisted };
}

export interface FetchUserChartsOptions {
  userId: string;
  chartId?: string;
  onProgress?: (step: string) => void;
}

export interface FetchUserChartsResult {
  session: ChartSession;
  chartId: string;
}

/**
 * Load the latest (or specified) saved chart from DynamoDB and regenerate
 * extended analysis into the local chart session — without creating a new DB row.
 */
export async function fetchAndRestoreCharts(
  opts: FetchUserChartsOptions,
): Promise<FetchUserChartsResult> {
  const { userId, chartId: chartIdOpt, onProgress } = opts;
  const trimmedId = userId.trim();
  if (!trimmedId) {
    throw new Error("User ID is required");
  }

  onProgress?.("Fetching saved charts…");
  const list = await pyjhora.listUserCharts(trimmedId);
  if (!list.charts.length) {
    throw new Error(`No saved charts found for user ID "${trimmedId}"`);
  }

  const chartId = chartIdOpt ?? list.charts[0].chart_id;
  onProgress?.(`Loading chart ${chartId}…`);
  const saved = await pyjhora.getSavedChart(trimmedId, chartId);

  const birthInput = saved.birth_input;
  const userInfo = saved.user_info;
  const studentContext = studentContextFromUserInfo(userInfo, birthInput.place_label ?? "");

  if (typeof window !== "undefined") {
    localStorage.setItem(PYJHORA_LS_USER, trimmedId);
  }
  syncUserProfileFromUserInfo(trimmedId, userInfo);

  const d1Table = normalizeTableResponse(saved.d1_table, saved.meta);
  const divisionalBasic = saved.divisional_charts;
  const extended = await computeExtendedAnalysis(birthInput, studentContext, onProgress, {
    runEducationAnalysis: true,
  });

  const session: ChartSession = {
    userId: trimmedId,
    chartId: saved.chart_id,
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
    consolidated: extended.consolidated,
    educationAnalysis: extended.educationAnalysis,
    educationAnalysisError: extended.educationAnalysisError,
    savedAt: saved.updated_at,
  };

  saveChartSession(session);
  return { session, chartId: saved.chart_id };
}
