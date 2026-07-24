import { createFileRoute, Navigate } from "@tanstack/react-router";
import { defaultEducationTab } from "@/lib/education-report/tab-defaults";
import { useChartSession } from "@/hooks/use-chart-session";

export const Route = createFileRoute("/education-analysis/")({
  component: EducationAnalysisIndexPage,
});

function EducationAnalysisIndexPage() {
  const session = useChartSession();
  const age =
    session?.educationAnalysis?.student?.current_age ??
    session?.pucAnalysis?.student?.current_age;
  const tab = defaultEducationTab(age);
  const to = tab === "puc" ? "/education-analysis/puc" : "/education-analysis/ug";
  return <Navigate to={to} replace />;
}
