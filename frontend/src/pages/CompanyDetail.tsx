import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  fetchCompanies,
  fetchReports,
  fetchCompanyAnalyses,
  deleteCompany,
  deleteReport,
  redownloadReport,
  analyzeReport,
  analyzeAll,
} from "../api/client";
import ReportTable from "../components/ReportTable";
import DownloadModal from "../components/DownloadModal";
import AnalysisView from "../components/AnalysisView";
import type { Company, Report, Analysis } from "../types";

const TABS = [
  { key: "reports", label: "보고서" },
  { key: "subsidiary", label: "종속회사 분석" },
  { key: "rnd", label: "R&D/투자 분석" },
  { key: "national_tech", label: "국가전략기술" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function CompanyDetail() {
  const { id } = useParams<{ id: string }>();
  const companyId = Number(id);

  const [company, setCompany] = useState<Company | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [tab, setTab] = useState<TabKey>("reports");
  const [showDownload, setShowDownload] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const load = async () => {
    const [companies, reps, anals] = await Promise.all([
      fetchCompanies(),
      fetchReports(companyId),
      fetchCompanyAnalyses(companyId),
    ]);
    setCompany(companies.find((c) => c.id === companyId) || null);
    setReports(reps);
    setAnalyses(anals);
  };

  useEffect(() => {
    load();
  }, [companyId]);

  const handleDelete = async () => {
    if (!confirm("이 기업과 관련 데이터를 모두 삭제하시겠습니까?")) return;
    await deleteCompany(companyId);
    window.location.href = "/";
  };

  if (!company) {
    return (
      <div className="py-16 text-center text-text-tertiary">로딩 중...</div>
    );
  }

  return (
    <div>
      {/* Breadcrumb + Header */}
      <div className="no-print mb-6">
        <Link
          to="/"
          className="no-print text-sm text-text-tertiary hover:text-accent"
        >
          ← 기업 목록
        </Link>
        <div className="mt-3 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-navy">
              {company.corp_name}
            </h1>
            <div className="mt-1 flex gap-3 text-sm text-text-secondary">
              {company.stock_code && (
                <span className="font-mono">{company.stock_code}</span>
              )}
              <span className="font-mono text-text-tertiary">
                DART: {company.corp_code}
              </span>
            </div>
          </div>
          <div className="no-print flex gap-2">
            <button
              onClick={() => setShowDownload(true)}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-light"
            >
              보고서 다운로드
            </button>
            <button
              disabled={analyzing}
              onClick={async () => {
                setAnalyzing(true);
                try {
                  const result = await analyzeAll(companyId);
                  showToast(result.message);
                  load();
                } catch (e: any) {
                  showToast(e.message, "err");
                } finally {
                  setAnalyzing(false);
                }
              }}
              className="rounded-lg border border-accent px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent/5 disabled:opacity-50"
            >
              {analyzing ? "요청 중..." : "전체 분석"}
            </button>
            <button
              onClick={handleDelete}
              className="rounded-lg border border-danger/30 px-3 py-2 text-sm text-danger transition-colors hover:bg-danger-bg"
            >
              삭제
            </button>
          </div>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div
          className={`no-print mb-4 flex items-center gap-2 rounded-lg px-4 py-3 text-sm font-medium ${
            toast.type === "ok"
              ? "bg-success-bg text-success"
              : "bg-danger-bg text-danger"
          }`}
        >
          <span>{toast.type === "ok" ? "✓" : "✕"}</span>
          {toast.msg}
        </div>
      )}

      {/* Tabs */}
      <div className="no-print mb-6 border-b border-border">
        <div className="flex gap-0">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`border-b-2 px-5 py-3 text-sm font-medium transition-colors ${
                tab === t.key
                  ? "border-accent text-accent"
                  : "border-transparent text-text-secondary hover:text-text-primary"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {tab === "reports" && (
        <ReportTable
          reports={reports}
          analyzing={analyzing}
          onAnalyze={async (reportId) => {
            setAnalyzing(true);
            try {
              const result = await analyzeReport(reportId);
              showToast(result.message);
              load();
              setTab("subsidiary");
            } catch (e: any) {
              showToast(e.message, "err");
            } finally {
              setAnalyzing(false);
            }
          }}
          onDelete={async (reportId) => {
            const report = reports.find((r) => r.id === reportId);
            if (!confirm(`"${report?.report_name}" 보고서를 삭제하시겠습니까?\n관련 분석 데이터도 함께 삭제됩니다.`)) return;
            try {
              await deleteReport(reportId);
              showToast("보고서가 삭제되었습니다.");
              load();
            } catch (e: any) {
              showToast(e.message, "err");
            }
          }}
          onRedownload={async (reportId) => {
            const report = reports.find((r) => r.id === reportId);
            if (report && report.analysis_count > 0) {
              if (!confirm(
                `"${report.report_name}"\n\n이 보고서에 분석 결과 ${report.analysis_count}건이 있습니다.\n재다운로드하면 기존 분석 결과가 모두 삭제됩니다.\n계속하시겠습니까?`
              )) return;
            }
            try {
              await redownloadReport(reportId);
              showToast("보고서 파일을 재다운로드했습니다. 기존 분석 결과가 삭제되었습니다.");
              load();
            } catch (e: any) {
              showToast(e.message, "err");
            }
          }}
        />
      )}

      {tab !== "reports" && (
        <AnalysisView
          companyId={companyId}
          companyName={company.corp_name}
          reports={reports}
          analyses={analyses}
          analysisType={tab}
          onRefresh={load}
        />
      )}

      <DownloadModal
        open={showDownload}
        companyId={companyId}
        onClose={() => setShowDownload(false)}
        onDownloaded={load}
      />
    </div>
  );
}
