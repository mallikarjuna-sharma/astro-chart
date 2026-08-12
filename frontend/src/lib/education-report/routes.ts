export interface EducationRouteView {
  route_name?: string;
  title?: string;
  best_for?: string;
  ug_options?: string;
  pg_options?: string;
  phd_options?: string;
  careers?: string;
  long_term_value?: string;
  risk_level?: string;
}

interface SnapshotLike {
  best_ug_route?: string;
  best_pg_route?: string;
  strong_backup_route?: string;
}

interface ReportLike {
  education_routes?: EducationRouteView[];
  snapshot?: SnapshotLike;
}

/** Ensure Routes & plan always shows A/B/C — back-fills from snapshot when needed. */
export function resolveEducationRoutes(report: ReportLike): EducationRouteView[] {
  const existing = (report.education_routes ?? []).filter(
    (route) => route.title || route.ug_options || route.pg_options,
  );
  if (existing.length >= 3) return existing;

  const snap = report.snapshot ?? {};
  const primary = existing[0] ?? {};
  const templates: EducationRouteView[] = [
    {
      route_name: "Route A - Primary Route",
      title: primary.title ?? snap.best_ug_route,
      ug_options: primary.ug_options ?? snap.best_ug_route,
      pg_options: primary.pg_options ?? snap.best_pg_route,
      phd_options: primary.phd_options,
      careers: primary.careers,
      best_for: primary.best_for,
      risk_level: primary.risk_level,
      long_term_value: primary.long_term_value,
    },
    {
      route_name: "Route B - High-End Specialised Route",
      title: snap.best_pg_route,
      ug_options: snap.best_ug_route,
      pg_options: snap.best_pg_route,
      best_for: "Depth, research, or high-end PG specialization.",
    },
    {
      route_name: "Route C - Safe Practical Backup",
      title: snap.strong_backup_route,
      ug_options: snap.strong_backup_route,
      pg_options: snap.best_pg_route ? `Bridge toward ${snap.best_pg_route}` : undefined,
      best_for: "Practical fallback if rank, finance, or interest shifts.",
    },
  ];

  return templates.filter((route) => route.title || route.ug_options || route.pg_options);
}
