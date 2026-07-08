import type { EducationAnalysisResponse } from "@/lib/pyjhora/types";

interface Props {
  data: EducationAnalysisResponse;
}

export function EducationCareerReport({ data }: Props) {
  const reportHtml = data.report_html ?? (data.report?.report_html as string | undefined);

  if (reportHtml) {
    return (
      <iframe
        title="Career Field Recommendation Report"
        srcDoc={reportHtml}
        className="w-full min-h-[1200px] border border-slate-200 rounded-lg bg-white shadow-sm"
        sandbox="allow-same-origin"
      />
    );
  }

  return (
    <div className="rounded-lg border border-amber-300/50 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      Report HTML is not available for this analysis run. Refresh the analysis to regenerate the
      career field report.
    </div>
  );
}
