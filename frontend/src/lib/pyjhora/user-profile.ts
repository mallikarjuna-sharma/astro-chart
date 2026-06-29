import type { BirthInput, StudentContext, StudentPreference, UserInfo } from "./types";
import { defaultStudentContext } from "./session";

export interface BirthDataFormSlice {
  displayName: string;
  email: string;
  phone: string;
  locationQuery: string;
  notes: string;
  gender: "M" | "F";
  educationSystem: string;
  riskAppetite: "LOW" | "MODERATE" | "HIGH";
  interestedIn: string;
  excelAt: string;
  financialConstraints: boolean;
}

function splitCsv(v: string): string[] {
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function joinCsv(items: string[] | undefined): string {
  return (items ?? []).join(", ");
}

export function studentPreferenceFromForm(form: BirthDataFormSlice): StudentPreference {
  return {
    interested_in: splitCsv(form.interestedIn),
    already_excel_at: splitCsv(form.excelAt),
    financial_constraints: form.financialConstraints,
    risk_appetite: form.riskAppetite,
  };
}

export function buildUserInfoFromForm(form: BirthDataFormSlice): UserInfo {
  return {
    display_name: form.displayName.trim(),
    email: form.email.trim() || null,
    phone: form.phone.trim() || null,
    location_query: form.locationQuery.trim() || null,
    notes: form.notes.trim() || null,
    gender: form.gender,
    education_system: form.educationSystem.trim() || null,
    student_preference: studentPreferenceFromForm(form),
  };
}

export function studentContextFromUserInfo(
  userInfo: UserInfo,
  placeLabel: string,
): StudentContext {
  const pref = userInfo.student_preference;
  return {
    ...defaultStudentContext(),
    pob: placeLabel || null,
    gender: userInfo.gender === "F" ? "F" : userInfo.gender === "M" ? "M" : "M",
    education_system: userInfo.education_system ?? defaultStudentContext().education_system,
    student_preference: pref
      ? {
          interested_in: pref.interested_in ?? [],
          already_excel_at: pref.already_excel_at ?? [],
          financial_constraints: pref.financial_constraints ?? false,
          risk_appetite: pref.risk_appetite ?? "MODERATE",
        }
      : defaultStudentContext().student_preference,
  };
}

export function birthInputToDateTime(birthInput: BirthInput): { date: string; time: string } {
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    date: `${birthInput.year}-${pad(birthInput.month)}-${pad(birthInput.day)}`,
    time: `${pad(birthInput.hour)}:${pad(birthInput.minute)}:${pad(birthInput.second)}`,
  };
}

export function formFieldsFromSaved(
  userInfo: UserInfo,
  birthInput: BirthInput,
): BirthDataFormSlice & {
  date: string;
  time: string;
  placeLabel: string;
  latitude: string;
  longitude: string;
  timezoneOffsetHours: string;
  ayanamsa: string;
  useTrueNodes: boolean;
  includeOuterPlanets: boolean;
} {
  const { date, time } = birthInputToDateTime(birthInput);
  const pref = userInfo.student_preference;

  return {
    displayName: userInfo.display_name ?? "",
    email: userInfo.email ?? "",
    phone: userInfo.phone ?? "",
    locationQuery: userInfo.location_query ?? "",
    notes: userInfo.notes ?? "",
    gender: userInfo.gender === "F" ? "F" : "M",
    educationSystem: userInfo.education_system ?? "India_CBSE",
    riskAppetite: pref?.risk_appetite ?? "MODERATE",
    interestedIn: joinCsv(pref?.interested_in),
    excelAt: joinCsv(pref?.already_excel_at),
    financialConstraints: pref?.financial_constraints ?? false,
    date,
    time,
    placeLabel: birthInput.place_label ?? "",
    latitude: String(birthInput.latitude),
    longitude: String(birthInput.longitude),
    timezoneOffsetHours: String(birthInput.timezone_offset_hours),
    ayanamsa: birthInput.ayanamsa ?? "LAHIRI",
    useTrueNodes: birthInput.use_true_nodes ?? false,
    includeOuterPlanets: birthInput.include_outer_planets ?? false,
  };
}
