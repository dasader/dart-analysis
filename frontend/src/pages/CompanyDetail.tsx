import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  fetchCompanies,
  fetchReports,
  fetchCompanyAnalyses,
  deleteCompany,
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
      <div className="mb-6">
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
              onClick={async () => {
                const result = await analyzeAll(companyId);
                alert(result.message);
                load();
              }}
              className="rounded-lg border border-accent px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent/5"
            >
              전체 분석
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
          onAnalyze={(reportId) => {
            setTab("subsidiary");
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
