import type { D1BodyRow } from "@/lib/pyjhora/types";

export function D1BodyTable({ rows }: { rows: D1BodyRow[] }) {
  return (
    <div className="overflow-x-auto border border-border rounded-md">
      <table className="w-full text-xs md:text-[0.8rem]">
        <thead>
          <tr className="bg-secondary/60 border-b border-border">
            <th className="text-left font-semibold px-2 py-1.5">Body</th>
            <th className="text-right font-semibold px-2 py-1.5">Longitude</th>
            <th className="text-left font-semibold px-2 py-1.5">Nakshatra</th>
            <th className="text-center font-semibold px-2 py-1.5">Pada</th>
            <th className="text-center font-semibold px-2 py-1.5">Rasi</th>
            <th className="text-center font-semibold px-2 py-1.5">Navamsa</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={r.body}
              className={`border-t border-border/50 ${i % 2 ? "bg-secondary/20" : ""}`}
            >
              <td className="px-2 py-1 whitespace-nowrap">
                <span className="text-gold font-medium">{r.body}</span>
                {r.retrograde ? (
                  <span className="text-destructive font-semibold" title="Retrograde">
                    {" "}
                    (R)
                  </span>
                ) : null}
                {r.karaka ? <span className="text-muted-foreground"> - {r.karaka}</span> : null}
              </td>
              <td className="px-2 py-1 text-right tabular-nums whitespace-nowrap">{r.longitude}</td>
              <td className="px-2 py-1 whitespace-nowrap" title={r.nakshatra_full}>
                {r.nakshatra}
              </td>
              <td className="px-2 py-1 text-center tabular-nums">{r.pada}</td>
              <td className="px-2 py-1 text-center" title={r.rasi_full}>
                {r.rasi}
              </td>
              <td className="px-2 py-1 text-center" title={r.navamsa_full}>
                {r.navamsa}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
