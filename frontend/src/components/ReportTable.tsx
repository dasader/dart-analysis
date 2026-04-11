import type { Report } from "../types";

interface Props {
  reports: Report[];
  onAnalyze: (reportId: number) => void;
}

const ANALYSIS_TYPES = ["subsidiary", "rnd", "national_tech"];

export default function ReportTable({ reports, onAnalyze }: Props) {
  if (reports.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-surface py-16 text-center text-sm text-text-tertiary">
        아직 다운로드된 보고서가 없습니다.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-background/50">
            <th className="px-5 py-3 text-left font-semibold text-text-secondary">
              보고서명
            </th>
            <th className="px-5 py-3 text-left font-semibold text-text-secondary">
              유형
            </th>
            <th className="px-5 py-3 text-center font-semibold text-text-secondary">
              사업연도
            </th>
            <th className="px-5 py-3 text-left font-semibold text-text-secondary">
              공시일
            </th>
            <th className="px-5 py-3 text-center font-semibold text-text-secondary">
              분석
            </th>
            <th className="px-5 py-3 text-right font-semibold text-text-secondary" />
          </tr>
        </thead>
        <tbody>
          {reports.map((r) => (
            <tr
              key={r.id}
              className="border-b border-border transition-colors last:border-b-0 hover:bg-background/30"
            >
              <td className="px-5 py-3.5 font-medium text-text-primary">
                {r.report_name}
              </td>
              <td className="px-5 py-3.5">
                <span className="inline-flex rounded-full border border-border px-2 py-0.5 text-xs text-text-secondary">
                  {r.report_type}
                </span>
              </td>
              <td className="px-5 py-3.5 text-center font-mono text-text-secondary">
                {r.fiscal_year}
              </td>
              <td className="px-5 py-3.5 text-text-secondary">
                {r.filing_date || "—"}
              </td>
              <td className="px-5 py-3.5 text-center">
                <span
                  className={`font-mono text-xs ${
                    r.analysis_count >= ANALYSIS_TYPES.length
                      ? "text-success"
                      : r.analysis_count > 0
                        ? "text-warning"
                        : "text-text-tertiary"
                  }`}
                >
                  {r.analysis_count}/{ANALYSIS_TYPES.length}
                </span>
              </td>
              <td className="px-5 py-3.5 text-right">
                <button
                  onClick={() => onAnalyze(r.id)}
                  className="text-sm text-accent hover:underline"
                >
                  분석 →
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
