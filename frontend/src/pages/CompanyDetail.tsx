import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  fetchCompany,
  fetchReports,
  fetchCompanyAnalyses,
  fetchTags,
  assignTag,
  removeCompanyTag,
  deleteCompany,
  deleteReport,
  redownloadReport,
  analyzeReport,
  analyzeAll,
} from "../api/client";
import ReportTable from "../components/ReportTable";
import DownloadModal from "../components/DownloadModal";
import AnalysisView from "../components/AnalysisView";
import TagChip from "../components/TagChip";
import { getErrorMessage } from "../lib/errors";
import { ANALYSIS_TYPE_KEYS, ANALYSIS_TYPE_LABELS } from "../types";
import type { Company, Report, Analysis, AnalysisType, Tag } from "../types";

type TabKey = "reports" | AnalysisType;

// 분석 탭은 단일 출처(ANALYSIS_TYPE_KEYS/LABELS)에서 파생
const TABS: { key: TabKey; label: string }[] = [
  { key: "reports", label: "보고서" },
  ...ANALYSIS_TYPE_KEYS.map((k) => ({ key: k, label: ANALYSIS_TYPE_LABELS[k] })),
];

// 폴링 시 분석 상태가 실제로 바뀌었을 때만 setState 하기 위한 비교
function analysesEqual(a: Analysis[], b: Analysis[]): boolean {
  return (
    a.length === b.length &&
    a.every(
      (x, i) =>
        x.id === b[i].id &&
        x.status === b[i].status &&
        x.updated_at === b[i].updated_at,
    )
  );
}

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
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [showTagDropdown, setShowTagDropdown] = useState(false);
  const tagDropdownRef = useRef<HTMLDivElement>(null);

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const load = useCallback(async () => {
    const [companyData, reps, anals] = await Promise.all([
      fetchCompany(companyId).catch(() => null),
      fetchReports(companyId),
      fetchCompanyAnalyses(companyId),
    ]);
    setCompany(companyData);
    setReports(reps);
    setAnalyses(anals);
  }, [companyId]);

  // 비동기 액션 공통 처리: 성공 메시지 토스트 + 재로딩, 실패 시 에러 토스트
  const runWithToast = async (action: () => Promise<string | void>) => {
    try {
      const msg = await action();
      if (msg) showToast(msg);
      await load();
    } catch (e) {
      showToast(getErrorMessage(e), "err");
    }
  };

  // 폴링 전용: 변하지 않는 회사/보고서/태그는 건너뛰고 분석 상태만 갱신
  const refreshAnalyses = useCallback(async () => {
    const next = await fetchCompanyAnalyses(companyId);
    setAnalyses((prev) => (analysesEqual(prev, next) ? prev : next));
  }, [companyId]);

  useEffect(() => {
    load();
  }, [load]);

  // 태그 목록은 거의 불변 → 마운트 시 1회만 조회
  useEffect(() => {
    fetchTags().then(setAllTags).catch(() => {});
  }, []);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (tagDropdownRef.current && !tagDropdownRef.current.contains(e.target as Node)) {
        setShowTagDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleDelete = async () => {
    if (!confirm("이 기업과 관련 데이터를 모두 삭제하시겠습니까?")) return;
    await deleteCompany(companyId);
    window.location.href = "/";
  };

  const handleAssignTag = async (tagId: number) => {
    try {
      const updated = await assignTag(companyId, tagId);
      setCompany(updated);
      setShowTagDropdown(false);
    } catch (e) {
      showToast(getErrorMessage(e), "err");
    }
  };

  const handleRemoveTag = async (tagId: number) => {
    try {
      const updated = await removeCompanyTag(companyId, tagId);
      setCompany(updated);
    } catch (e) {
      showToast(getErrorMessage(e), "err");
    }
  };

  if (!company) {
    return (
      <div className="py-16 text-center text-text-tertiary">로딩 중...</div>
    );
  }

  const availableTags = allTags.filter((t) => !company.tags.some((ct) => ct.id === t.id));

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
            <div className="no-print mt-2 flex flex-wrap items-center gap-1.5">
              {company.tags.map((tag) => (
                <TagChip key={tag.id} tag={tag} onRemove={handleRemoveTag} />
              ))}
              <div ref={tagDropdownRef} className="relative">
                <button
                  onClick={() => setShowTagDropdown((v) => !v)}
                  className="rounded-full border border-dashed border-border px-2.5 py-0.5 text-xs text-text-tertiary hover:border-accent hover:text-accent"
                >
                  + 태그
                </button>
                {showTagDropdown && (
                  <div className="absolute left-0 top-full z-20 mt-1 min-w-36 rounded-lg border border-border bg-surface shadow-lg">
                    {availableTags.length === 0 ? (
                      <p className="px-3 py-2.5 text-xs text-text-tertiary">
                        할당 가능한 태그가 없습니다.
                      </p>
                    ) : (
                      availableTags.map((tag) => (
                        <button
                          key={tag.id}
                          onClick={() => handleAssignTag(tag.id)}
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-background/60"
                        >
                          <span
                            style={{ backgroundColor: tag.color }}
                            className="inline-block h-2.5 w-2.5 rounded-full flex-shrink-0"
                          />
                          {tag.name}
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="no-print flex gap-2">
            <button
              onClick={() => setShowDownload(true)}
              className="btn btn-primary"
            >
              보고서 다운로드
            </button>
            <button
              disabled={analyzing}
              onClick={() => {
                setAnalyzing(true);
                runWithToast(async () => (await analyzeAll(companyId)).message).finally(
                  () => setAnalyzing(false),
                );
              }}
              className="btn btn-ghost-accent"
            >
              {analyzing ? "요청 중..." : "전체 분석"}
            </button>
            <button
              onClick={handleDelete}
              className="btn btn-danger"
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
          onAnalyze={(reportId) => {
            setAnalyzing(true);
            runWithToast(async () => {
              const result = await analyzeReport(reportId);
              setTab("subsidiary");
              return result.message;
            }).finally(() => setAnalyzing(false));
          }}
          onDelete={(reportId) => {
            const report = reports.find((r) => r.id === reportId);
            if (!confirm(`"${report?.report_name}" 보고서를 삭제하시겠습니까?\n관련 분석 데이터도 함께 삭제됩니다.`)) return;
            runWithToast(async () => {
              await deleteReport(reportId);
              return "보고서가 삭제되었습니다.";
            });
          }}
          onRedownload={(reportId) => {
            const report = reports.find((r) => r.id === reportId);
            if (
              report &&
              report.analysis_count > 0 &&
              !confirm(
                `"${report.report_name}"\n\n이 보고서에 분석 결과 ${report.analysis_count}건이 있습니다.\n재다운로드하면 기존 분석 결과가 모두 삭제됩니다.\n계속하시겠습니까?`,
              )
            )
              return;
            return runWithToast(async () => {
              await redownloadReport(reportId);
              return "보고서 파일을 재다운로드했습니다. 기존 분석 결과가 삭제되었습니다.";
            });
          }}
        />
      )}

      {tab !== "reports" && (
        <AnalysisView
          companyName={company.corp_name}
          reports={reports}
          analyses={analyses}
          analysisType={tab}
          onRefresh={refreshAnalyses}
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
