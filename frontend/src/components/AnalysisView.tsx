import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { analyzeReport } from "../api/client";
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

// 인쇄용 전체 명칭
const PRINT_TYPE_LABELS: Record<string, string> = {
  subsidiary: "연결대상 종속회사 변동 분석",
  rnd: "연구개발 및 투자 분석",
  national_tech: "국가전략기술 관련 분석",
};

const PRINT_TYPE_ORDER = ["subsidiary", "rnd", "national_tech"] as const;

const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  pending: { text: "대기중", color: "text-text-tertiary bg-gray-100" },
  running: { text: "분석중", color: "text-warning bg-warning-bg" },
  completed: { text: "완료", color: "text-success bg-success-bg" },
  failed: { text: "실패", color: "text-danger bg-danger-bg" },
};

const PROSE_CLASSES = `
  prose prose-sm max-w-none
  prose-headings:font-semibold prose-headings:text-navy prose-headings:mt-6 prose-headings:mb-3
  prose-h2:text-base prose-h3:text-sm
  prose-p:text-text-primary prose-p:leading-relaxed prose-p:my-3
  prose-li:text-text-primary prose-li:leading-relaxed
  prose-strong:text-text-primary
  prose-table:w-full prose-table:text-sm prose-table:border-collapse
  prose-thead:bg-background
  prose-th:border prose-th:border-border prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:font-semibold prose-th:text-text-secondary
  prose-td:border prose-td:border-border prose-td:px-3 prose-td:py-2 prose-td:text-text-primary
  prose-tr:even:bg-background/40
  prose-hr:border-border prose-hr:my-6
  prose-blockquote:border-l-accent prose-blockquote:text-text-secondary
  prose-code:text-accent prose-code:bg-background prose-code:px-1 prose-code:rounded
`.trim();

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
    years[0] ?? null,
  );
  const [runningId, setRunningId] = useState<number | null>(null);

  // years 목록이 바뀌었을 때 selectedYear가 null이거나 목록에 없으면 자동 선택
  useEffect(() => {
    if (years.length > 0 && (selectedYear === null || !years.includes(selectedYear))) {
      setSelectedYear(years[0]);
    }
  }, [years, selectedYear]);

  const selectedReport = reports.find((r) => r.fiscal_year === selectedYear);
  const selectedAnalysis = relevantAnalyses.find(
    (a) => selectedReport && a.report_id === selectedReport.id,
  );

  // 인쇄용: 선택된 연도의 완료된 3가지 분석을 고정 순서로
  const printAnalyses = selectedReport
    ? (PRINT_TYPE_ORDER
        .map((type) =>
          analyses.find(
            (a) =>
              a.report_id === selectedReport.id &&
              a.analysis_type === type &&
              a.status === "completed",
          ),
        )
        .filter(Boolean) as Analysis[])
    : [];

  // 해당 보고서에 완료된 분석 결과가 있으면 true
  const hasCompletedResult = (reportId: number) =>
    analyses.some((a) => a.report_id === reportId && a.status === "completed");

  const handleRun = async (reportId: number, requireConfirm = false) => {
    if (requireConfirm && hasCompletedResult(reportId)) {
      if (!confirm(
        "이미 분석 결과가 있습니다.\n재분석하면 3가지 분석(종속회사·R&D·국가전략기술)이 모두 덮어쓰여집니다.\n계속하시겠습니까?"
      )) return;
    }
    setRunningId(reportId);
    try {
      await analyzeReport(reportId);
      onRefresh();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setRunningId(null);
    }
  };

  const unanalyzedReports = reports.filter(
    (r) =>
      r.file_path &&
      !relevantAnalyses.some((a) => a.report_id === r.id),
  );

  return (
    <div>
      {/* ───── 화면 UI (인쇄 제외) ───── */}
      <div className="no-print">
        <div className="mb-6 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-navy">
            {TYPE_LABELS[analysisType]}
          </h3>
          <div className="flex items-center gap-3">
            {hasActiveJob && (
              <span className="flex items-center gap-1.5 text-sm text-warning">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-warning" />
                처리중...
              </span>
            )}
            {selectedReport && (
              <button
                disabled={runningId === selectedReport.id}
                onClick={() => handleRun(selectedReport.id, true)}
                className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-background disabled:opacity-50"
                title="3가지 분석 항목을 Gemini 1회 호출로 일괄 재분석"
              >
                {runningId === selectedReport.id ? "요청 중..." : "전체 재분석"}
              </button>
            )}
            {printAnalyses.length > 0 && (
              <button
                onClick={() => window.print()}
                className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-background"
                title={`${selectedYear}년 분석 결과 ${printAnalyses.length}건 PDF 출력`}
              >
                PDF 출력
              </button>
            )}
          </div>
        </div>

        {/* Year chips */}
        {years.length > 0 && (
          <div className="mb-6 flex flex-wrap gap-2">
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
                분석일:{" "}
                {new Date(selectedAnalysis.updated_at).toLocaleDateString("ko-KR")}
              </span>
            </div>
            <article className={PROSE_CLASSES}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {selectedAnalysis.result_summary || ""}
              </ReactMarkdown>
            </article>
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
                      disabled={runningId === r.id}
                      onClick={() => handleRun(r.id)}
                      className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-light disabled:opacity-50"
                    >
                      {runningId === r.id ? "요청 중..." : `${r.fiscal_year} ${r.report_type} 분석`}
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

      {/* ───── 인쇄 전용 통합 보고서 ───── */}
      {printAnalyses.length > 0 && (
        <div className="print-only">
          {/* 커버 헤더 */}
          <div className="print-cover">
            <h1 className="print-company">{companyName}</h1>
            <p className="print-subtitle">{selectedYear}년 사업보고서 AI 분석</p>
            <p className="print-meta">
              분석일:{" "}
              {new Date(printAnalyses[0].updated_at).toLocaleDateString("ko-KR")}
            </p>
          </div>

          {/* 3가지 분석 섹션 */}
          {printAnalyses.map((analysis, idx) => (
            <div key={analysis.id} className={idx > 0 ? "print-page-break" : ""}>
              <h2 className="print-section-title">
                {idx + 1}. {PRINT_TYPE_LABELS[analysis.analysis_type]}
              </h2>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {analysis.result_summary || ""}
              </ReactMarkdown>
            </div>
          ))}

          <footer className="print-footer">
            DART 사업보고서 AI 분석 보고서 — 자동 생성됨
          </footer>
        </div>
      )}
    </div>
  );
}
