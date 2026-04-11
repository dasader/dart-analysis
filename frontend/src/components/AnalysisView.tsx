import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { runAnalysis } from "../api/client";
import PrintableReport from "./PrintableReport";
import type { Analysis, Report } from "../types";

interface Props {
  companyId: number;
  companyName: string;
  reports: Report[];
  analyses: Analysis[];
  analysisType: "subsidiary" | "rnd" | "national_tech";
  onRefresh: () => void;
}

const TYPE_LABELS: Record<string, string> = {
  subsidiary: "종속회사 변동 분석",
  rnd: "R&D/투자 분석",
  national_tech: "국가전략기술 분석",
};

const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  pending: { text: "대기중", color: "text-text-tertiary bg-gray-100" },
  running: { text: "분석중", color: "text-warning bg-warning-bg" },
  completed: { text: "완료", color: "text-success bg-success-bg" },
  failed: { text: "실패", color: "text-danger bg-danger-bg" },
};

export default function AnalysisView({
  companyId: _companyId,
  companyName,
  reports,
  analyses,
  analysisType,
  onRefresh,
}: Props) {
  const relevantAnalyses = analyses.filter(
    (a) => a.analysis_type === analysisType,
  );

  // pending 또는 running 상태가 있으면 5초마다 자동 폴링
  const hasActiveJob = relevantAnalyses.some(
    (a) => a.status === "pending" || a.status === "running",
  );
  const intervalRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    if (hasActiveJob) {
      intervalRef.current = setInterval(onRefresh, 5000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [hasActiveJob, onRefresh]);

  const years = [
    ...new Set(
      reports
        .filter((r) =>
          relevantAnalyses.some((a) => a.report_id === r.id),
        )
        .map((r) => r.fiscal_year),
    ),
  ].sort((a, b) => b - a);

  const [selectedYear, setSelectedYear] = useState<number | null>(
    years[0] || null,
  );

  const selectedReport = reports.find((r) => r.fiscal_year === selectedYear);
  const selectedAnalysis = relevantAnalyses.find(
    (a) => selectedReport && a.report_id === selectedReport.id,
  );

  const handleRun = async (reportId: number) => {
    try {
      await runAnalysis(reportId, analysisType);
      onRefresh();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const unanalyzedReports = reports.filter(
    (r) =>
      r.file_path &&
      !relevantAnalyses.some((a) => a.report_id === r.id),
  );

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-navy">
          {TYPE_LABELS[analysisType]}
        </h3>
        <div className="no-print flex items-center gap-3">
          {hasActiveJob && (
            <span className="flex items-center gap-1.5 text-sm text-warning">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-warning" />
              처리중...
            </span>
          )}
          {selectedReport && (
            <button
              onClick={() => handleRun(selectedReport.id)}
              className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-background"
            >
              재분석
            </button>
          )}
          <button
            onClick={() => window.print()}
            className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-background"
          >
            PDF 출력
          </button>
        </div>
      </div>

      {/* Year chips */}
      {years.length > 0 && (
        <div className="no-print mb-6 flex flex-wrap gap-2">
          {years.map((y) => {
            const yearAnalysis = relevantAnalyses.find(
              (a) => reports.find((r) => r.id === a.report_id)?.fiscal_year === y,
            );
            const statusInfo = yearAnalysis
              ? STATUS_LABELS[yearAnalysis.status]
              : null;
            return (
              <button
                key={y}
                onClick={() => setSelectedYear(y)}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  selectedYear === y
                    ? "bg-navy text-white"
                    : "border border-border bg-surface text-text-secondary hover:bg-background"
                }`}
              >
                {y}
                {statusInfo && yearAnalysis?.status !== "completed" && (
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] ${statusInfo.color}`}
                  >
                    {statusInfo.text}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Analysis Content */}
      {selectedAnalysis && selectedAnalysis.status === "completed" ? (
        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-3 border-b border-border pb-4">
            <span className="text-xs text-text-tertiary">
              모델: {selectedAnalysis.model_name}
            </span>
            <span className="text-xs text-text-tertiary">
              분석일:{" "}
              {new Date(selectedAnalysis.updated_at).toLocaleDateString("ko-KR")}
            </span>
          </div>
          <article className="prose prose-sm max-w-none prose-headings:text-navy prose-h2:text-base prose-h2:font-semibold prose-h3:text-sm prose-h3:font-semibold prose-p:text-text-primary prose-p:leading-relaxed prose-table:text-sm prose-th:bg-background/50 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2 prose-li:text-text-primary">
            <ReactMarkdown>{selectedAnalysis.result_summary || ""}</ReactMarkdown>
          </article>
          {selectedReport && (
            <PrintableReport
              companyName={companyName}
              fiscalYear={selectedReport.fiscal_year}
              analysis={selectedAnalysis}
            />
          )}
        </div>
      ) : selectedAnalysis &&
        (selectedAnalysis.status === "pending" ||
          selectedAnalysis.status === "running") ? (
        <div className="flex flex-col items-center rounded-xl border border-border bg-surface py-16">
          <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent" />
          <p className="text-sm text-text-secondary">
            {selectedAnalysis.status === "pending"
              ? "큐에서 대기 중입니다..."
              : "Gemini가 보고서를 분석하고 있습니다..."}
          </p>
          <p className="mt-1 text-xs text-text-tertiary">
            이 페이지를 벗어나도 분석은 계속 진행됩니다.
          </p>
        </div>
      ) : selectedAnalysis && selectedAnalysis.status === "failed" ? (
        <div className="rounded-xl border border-danger/30 bg-danger-bg p-6">
          <p className="mb-2 font-medium text-danger">분석 실패</p>
          <p className="text-sm text-text-secondary">
            {selectedAnalysis.error_message}
          </p>
          <button
            onClick={() => handleRun(selectedAnalysis.report_id)}
            className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white"
          >
            재시도
          </button>
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-surface py-16 text-center">
          {unanalyzedReports.length > 0 ? (
            <div>
              <p className="mb-4 text-sm text-text-tertiary">
                아직 이 유형의 분석이 수행되지 않았습니다.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {unanalyzedReports.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => handleRun(r.id)}
                    className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-light"
                  >
                    {r.fiscal_year} {r.report_type} 분석
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-text-tertiary">
              보고서를 먼저 다운로드해주세요.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
