import type { TableResponse } from "@/lib/pyjhora/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function BirthChartTable({ data }: { data: TableResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{data.title}</CardTitle>
      </CardHeader>
      <CardContent>
        {data.meta && Object.keys(data.meta).length > 0 && (
          <pre className="text-xs bg-muted/50 rounded-md p-3 mb-4 overflow-auto max-h-48 whitespace-pre-wrap">
            {JSON.stringify(data.meta, null, 2)}
          </pre>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border">
                {data.columns.map((c) => (
                  <th key={c} className="text-left py-2 px-2 text-xs text-muted-foreground uppercase">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, i) => (
                <tr key={i} className="border-b border-border/60">
                  {row.map((cell, j) => (
                    <td key={j} className="py-1.5 px-2">
                      {cell == null ? "" : String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
