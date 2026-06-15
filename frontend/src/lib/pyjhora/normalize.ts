import type { TableResponse } from "./types";

type TableRow = (string | number | null)[] | Record<string, string | number | null | undefined>;

/** Saved charts store D1 rows as column-keyed objects; direct API returns row arrays. */
export function normalizeTableResponse(
  table: Partial<TableResponse> & { rows?: TableRow[] },
  extraMeta?: Record<string, unknown>,
): TableResponse {
  const columns = table.columns ?? [];
  const rows = (table.rows ?? []).map((row) => {
    if (Array.isArray(row)) return row;
    if (row && typeof row === "object") {
      return columns.map((col) => {
        const value = row[col];
        return value == null ? null : value;
      });
    }
    return [];
  });

  return {
    title: table.title ?? "",
    columns,
    rows,
    meta: { ...(table.meta ?? {}), ...(extraMeta ?? {}) },
  };
}
