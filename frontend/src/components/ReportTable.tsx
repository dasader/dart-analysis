import { useMemo, useState } from "react";
import type { Report } from "../types";
import { ANALYSIS_TYPE_KEYS } from "../types";
import { useSort, SortIcon } from "../hooks/useSort";
import AdminButton from "./AdminButton";

interface Props {
  reports: Report[];
  analyzing?: boolean;
  onAnalyze: (reportId: number) => void;
  onDelete: (reportId: number) => void;
  onRedownload: (reportId: number) => void;
}

type SortKey = "filing_date" | "fiscal_year";

export default function ReportTable({ reports, analyzing = false, onAnalyze, onDelete, onRedownload }: Props) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const { sortKey, sortDir, toggleSort, compare } = useSort<SortKey>("fiscal_year", "desc");

  const sorted = useMemo(() => {
    return [...reports].sort((a, b) => {
      const av = sortKey === "filing_date" ? (a.filing_date ?? "") : a.fiscal_year;
      const bv = sortKey === "filing_date" ? (b.filing_date ?? "") : b.fiscal_year;
      return compare(av, bv);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reports, sortKey, sortDir]);

  if (reports.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-surface py-16 text-center text-sm text-text-tertiary">
        아직 다운로드된 보고서가 없습니다.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end">
        <span className="text-xs text-text-tertiary">{reports.length}건</span>
      </div>

      {/* 테이블 */}
      <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
        {sorted.length === 0 ? (
          <div className="py-12 text-center text-sm text-text-tertiary">
            조건에 맞는 보고서가 없습니다.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-background/50">
                <th className="px-5 py-3 text-left font-semibold text-text-secondary">
                  보고서명
                </th>
                <th
                  className="cursor-pointer px-5 py-3 text-center font-semibold text-text-secondary hover:text-text-primary"
                  onClick={() => toggleSort("fiscal_year")}
                >
                  사업연도<SortIcon active={sortKey === "fiscal_year"} dir={sortDir} />
                </th>
                <th
                  className="cursor-pointer px-5 py-3 text-left font-semibold text-text-secondary hover:text-text-primary"
                  onClick={() => toggleSort("filing_date")}
                >
                  공시일<SortIcon active={sortKey === "filing_date"} dir={sortDir} />
                </th>
                <th className="px-5 py-3 text-center font-semibold text-text-secondary">
                  분석
                </th>
                <th className="px-5 py-3 text-right font-semibold text-text-secondary">작업</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => {
                const isAmendment = r.report_name.includes("정정");
                return (
                <tr
                  key={r.id}
                  className={`border-b border-border transition-colors last:border-b-0 hover:bg-background/30 ${isAmendment ? "opacity-60" : ""}`}
                >
                  <td className="px-5 py-3.5 font-medium text-text-primary">
                    <span className={r.file_path ? "" : "text-text-tertiary"}>{r.report_name}</span>
                    {isAmendment && (
                      <span
                        className="ml-2 inline-flex rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] font-medium text-warning"
                        title="정정보고서는 일부 내용만 포함되어 분석에서 제외됩니다."
                      >
                        정정
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-center font-mono text-text-secondary">
                    {r.fiscal_year}
                  </td>
                  <td className="px-5 py-3.5 text-text-secondary">
                    {r.filing_date || "—"}
                  </td>
                  <td className="px-5 py-3.5 text-center">
                    {r.analysis_count >= ANALYSIS_TYPE_KEYS.length ? (
                      <span className="inline-flex items-center gap-1 text-xs text-success">
                        <span>●</span> 완료
                      </span>
                    ) : r.analysis_count > 0 ? (
                      <span className="inline-flex items-center gap-1 text-xs text-warning">
                        <span>◐</span> 일부
                      </span>
                    ) : (
                      <span className="text-xs text-text-tertiary">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <div className="flex items-center justify-end gap-3">
                      {isAmendment ? (
                        <span
                          className="cursor-default text-sm text-text-tertiary"
                          title="정정보고서는 일부 내용만 포함되어 분석할 수 없습니다."
                        >
                          분석 불가
                        </span>
                      ) : (
                        <AdminButton
                          disabled={analyzing || busyId === r.id}
                          onClick={() => onAnalyze(r.id)}
                          className="btn btn-link"
                        >
                          {analyzing ? "요청 중..." : "분석"}
                        </AdminButton>
                      )}
                      <AdminButton
                        disabled={busyId === r.id}
                        onClick={async () => {
                          setBusyId(r.id);
                          try { await onRedownload(r.id); }
                          finally { setBusyId(null); }
                        }}
                        className="btn btn-text"
                        title="파일 재다운로드"
                      >
                        {busyId === r.id ? "..." : "재다운로드"}
                      </AdminButton>
                      <AdminButton
                        disabled={busyId === r.id}
                        onClick={() => onDelete(r.id)}
                        className="btn btn-text-danger"
                      >
                        삭제
                      </AdminButton>
                    </div>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
