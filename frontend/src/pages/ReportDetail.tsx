import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  analyzeReport,
  fetchCompany,
  fetchReportAnalyses,
  fetchReports,
} from "../api/client";
import AnalysisView from "../components/AnalysisView";
import AdminButton from "../components/AdminButton";
import { getErrorMessage } from "../lib/errors";
import { normalizeTables } from "../lib/markdown";
import {
  ANALYSIS_TYPE_KEYS,
  ANALYSIS_TYPE_LABELS,
  PRINT_TYPE_LABELS,
} from "../types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { analysesEqual, isInProgress } from "../lib/status";
import { usePolling } from "../hooks/usePolling";
import type { Analysis, AnalysisStatus, AnalysisType, Company, Report } from "../types";

const STATUS_BADGE: Record<AnalysisStatus, { text: string; cls: string }> = {
  pending: { text: "대기", cls: "bg-gray-100 text-text-tertiary" },
  running: { text: "처리중", cls: "bg-warning-bg text-warning" },
  completed: { text: "완료", cls: "bg-success-bg text-success" },
  failed: { text: "실패", cls: "bg-danger-bg text-danger" },
};

/** 인쇄할 때만 보이는 통합 보고서. 화면에서는 숨어 있지만 탭 전환·폴링마다 마크다운 3편을
 *  다시 파싱하지 않도록 memo로 분리한다(분석이 바뀔 때만 다시 그린다). 공용 Markdown을 쓰지 않는 건
 *  prose 스타일이 인쇄 CSS와 섞이기 때문이다. */
const PrintReport = memo(function PrintReport({
  company,
  report,
  analyses,
}: {
  company: Company;
  report: Report;
  analyses: Analysis[];
}) {
  return (
    <div className="print-only">
      <div className="print-cover">
        <h1 className="print-company">{company.corp_name}</h1>
        <p className="print-subtitle">
          {report.fiscal_year}년 사업보고서 AI 분석
        </p>
        <p className="print-meta">
          분석일:{" "}
          {new Date(analyses[0].updated_at).toLocaleDateString("ko-KR")}
        </p>
      </div>

      {analyses.map((analysis, idx) => (
        <div key={analysis.id} className={idx > 0 ? "print-page-break" : ""}>
          <h2 className="print-section-title">
            {idx + 1}. {PRINT_TYPE_LABELS[analysis.analysis_type]}
          </h2>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {normalizeTables(analysis.result_summary || "")}
          </ReactMarkdown>
        </div>
      ))}

      <footer className="print-footer">
        DART 사업보고서 AI 분석 보고서 — 자동 생성됨
      </footer>
    </div>
  );
});

export default function ReportDetail() {
  const { id, reportId } = useParams<{ id: string; reportId: string }>();
  const companyId = Number(id);
  const rid = Number(reportId);

  const [company, setCompany] = useState<Company | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [tab, setTab] = useState<AnalysisType>(ANALYSIS_TYPE_KEYS[0]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    // 없는 기업·보고서로 들어와도 화면이 로딩에 멈추지 않도록 각각 흡수한다
    try {
      const [c, reps, anals] = await Promise.all([
        fetchCompany(companyId).catch(() => null),
        fetchReports(companyId).catch(() => [] as Report[]),
        fetchReportAnalyses(rid).catch(() => [] as Analysis[]),
      ]);
      setCompany(c);
      setReport(reps.find((r) => r.id === rid) ?? null);
      setAnalyses(anals);
    } finally {
      setLoading(false);
    }
  }, [companyId, rid]);

  useEffect(() => {
    load();
  }, [load]);

  // 진행 중인 분석이 있으면 주기적으로 갱신. Batch는 분 단위라 10초 간격이면 충분하다.
  const refresh = () =>
    fetchReportAnalyses(rid).then((next) =>
      setAnalyses((prev) => (analysesEqual(prev, next) ? prev : next)),
    );
  usePolling(refresh, 10000, analyses.some(isInProgress));

  const byType = useMemo(
    () => new Map(analyses.map((a) => [a.analysis_type, a])),
    [analyses],
  );

  const printAnalyses = useMemo(
    () =>
      ANALYSIS_TYPE_KEYS.map((t) => byType.get(t)).filter(
        (a): a is Analysis => a?.status === "completed",
      ),
    [byType],
  );

  const handleRun = async (requireConfirm = false) => {
    if (
      requireConfirm &&
      analyses.some((a) => a.status === "completed") &&
      !confirm(
        "이미 분석 결과가 있습니다.\n재분석하면 3가지 분석이 모두 덮어쓰여집니다.\n계속하시겠습니까?",
      )
    ) {
      return;
    }
    setRunning(true);
    setError(null);
    try {
      await analyzeReport(rid);
      await load();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return <div className="py-16 text-center text-text-tertiary">로딩 중...</div>;
  }
  if (!report || !company) {
    return (
      <div className="py-16 text-center text-text-tertiary">
        보고서를 찾을 수 없습니다.{" "}
        <Link to={`/companies/${companyId}`} className="text-accent underline">
          기업으로 돌아가기
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb + Header */}
      <div className="no-print mb-6">
        <div className="flex items-center gap-1.5 text-sm text-text-tertiary">
          <Link to="/" className="hover:text-accent">
            기업 목록
          </Link>
          <span>/</span>
          <Link to={`/companies/${companyId}`} className="hover:text-accent">
            {company.corp_name}
          </Link>
        </div>

        <div className="mt-3 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-navy">
              {report.fiscal_year}년 {report.report_type}
            </h1>
            <div className="mt-1 flex gap-3 text-sm text-text-secondary">
              <span>{report.report_name}</span>
              {report.filing_date && (
                <span className="text-text-tertiary">공시 {report.filing_date}</span>
              )}
            </div>
          </div>

          <div className="flex gap-2">
            <AdminButton
              disabled={running}
              onClick={() => handleRun(true)}
              className="btn btn-outline btn-sm"
              title="3가지 분석을 Gemini 1회 호출로 일괄 재분석"
            >
              {running ? "요청 중..." : "전체 재분석"}
            </AdminButton>
            {printAnalyses.length > 0 && (
              <button
                onClick={() => window.print()}
                className="btn btn-outline btn-sm"
                title={`분석 결과 ${printAnalyses.length}건 PDF 출력`}
              >
                PDF 출력
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-lg bg-danger-bg px-4 py-3 text-sm text-danger">
            {error}
          </div>
        )}
      </div>

      {/* 분석 유형 탭 — 이 보고서에 속한 하위 항목 */}
      <div className="no-print mb-6 border-b border-border">
        <div className="flex gap-0">
          {ANALYSIS_TYPE_KEYS.map((t) => {
            const status = byType.get(t)?.status;
            return (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-medium transition-colors ${
                  tab === t
                    ? "border-accent text-accent"
                    : "border-transparent text-text-secondary hover:text-text-primary"
                }`}
              >
                {ANALYSIS_TYPE_LABELS[t]}
                {status && status !== "completed" && (
                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${STATUS_BADGE[status].cls}`}>
                    {STATUS_BADGE[status].text}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="no-print">
        <AnalysisView
          analysis={byType.get(tab)}
          onRun={() => handleRun()}
          running={running}
        />
      </div>

      {/* ───── 인쇄 전용 통합 보고서 ───── */}
      {printAnalyses.length > 0 && (
        <PrintReport company={company} report={report} analyses={printAnalyses} />
      )}
    </div>
  );
}
