import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
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
import TagChip from "../components/TagChip";
import AdminButton from "../components/AdminButton";
import { getErrorMessage } from "../lib/errors";
import { analysesEqual, isInProgress } from "../lib/status";
import { usePolling } from "../hooks/usePolling";
import type { Company, Report, AnalysisState, Tag } from "../types";

export default function CompanyDetail() {
  const { id } = useParams<{ id: string }>();
  const companyId = Number(id);
  const navigate = useNavigate();

  const [company, setCompany] = useState<Company | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisState[]>([]);
  const [showDownload, setShowDownload] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [showTagDropdown, setShowTagDropdown] = useState(false);
  const tagDropdownRef = useRef<HTMLDivElement>(null);

  const showToast = (msg: string, type: "ok" | "err" = "ok") => setToast({ msg, type });
  // 토스트마다 타이머를 새로 건다 — 앞 타이머가 새 토스트를 일찍 닫거나 언마운트 뒤 setState하지 않게
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const load = useCallback(
    () =>
      Promise.all([
        fetchCompany(companyId).catch(() => null),
        fetchReports(companyId),
        fetchCompanyAnalyses(companyId),
      ]).then(([companyData, reps, anals]) => {
        setCompany(companyData);
        setReports(reps);
        setAnalyses(anals);
      }),
    [companyId],
  );

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

  // 폴링 전용: 회사/태그는 건너뛰고 보고서와 분석만 갱신.
  // 보고서도 함께 받아야 목록의 분석 상태가 같이 최신이 된다.
  const refreshProgress = useCallback(async () => {
    const [reps, next] = await Promise.all([
      fetchReports(companyId),
      fetchCompanyAnalyses(companyId),
    ]);
    setReports(reps);
    setAnalyses((prev) => (analysesEqual(prev, next) ? prev : next));
  }, [companyId]);

  useEffect(() => {
    load();
  }, [load]);

  // 진행 중인 분석이 하나라도 있으면 화면 어디에 있든 갱신한다.
  // Batch는 분 단위라 10초 간격이면 충분하다.
  usePolling(refreshProgress, 10000, analyses.some(isInProgress));

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
    try {
      await deleteCompany(companyId);
      navigate("/");
    } catch (e) {
      showToast(getErrorMessage(e), "err");
    }
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
            <AdminButton
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
            </AdminButton>
            <AdminButton
              onClick={handleDelete}
              className="btn btn-danger"
            >
              삭제
            </AdminButton>
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

      {/* 사업보고서 목록 — 분석 3종은 각 보고서 안에 있다 */}
      <div className="no-print mb-4 flex items-baseline gap-2">
        <h2 className="text-lg font-semibold text-navy">사업보고서</h2>
        <span className="text-sm text-text-tertiary">
          보고서명을 클릭하면 분석 결과를 볼 수 있습니다
        </span>
      </div>

      <ReportTable
          companyId={companyId}
          reports={reports}
          analyses={analyses}
          analyzing={analyzing}
          onAnalyze={(reportId) => {
            setAnalyzing(true);
            runWithToast(async () => {
              const result = await analyzeReport(reportId);
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

      <DownloadModal
        open={showDownload}
        companyId={companyId}
        onClose={() => setShowDownload(false)}
        onDownloaded={load}
      />
    </div>
  );
}
