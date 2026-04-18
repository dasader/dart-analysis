import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchCompanies, deleteCompany, fetchTags } from "../api/client";
import CompanyForm from "../components/CompanyForm";
import CompanyEditModal from "../components/CompanyEditModal";
import TagChip from "../components/TagChip";
import type { Company, Tag } from "../types";

type SortKey = "corp_name" | "corp_code" | "report_count" | "latest_analysis_date";
type SortDir = "asc" | "desc";

export default function CompanyList() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("corp_name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);

  const load = (tagIds = selectedTagIds) => {
    setLoading(true);
    fetchCompanies(tagIds.length > 0 ? tagIds : undefined)
      .then(setCompanies)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchTags().then(setAllTags).catch(() => {});
    load([]);
  }, []);

  const toggleTagFilter = (tagId: number) => {
    const newIds = selectedTagIds.includes(tagId)
      ? selectedTagIds.filter((id) => id !== tagId)
      : [...selectedTagIds, tagId];
    setSelectedTagIds(newIds);
    load(newIds);
  };

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("asc"); }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <span className="ml-1 opacity-30">↕</span>;
    return <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>;
  };

  const filtered = companies
    .filter((c) =>
      c.corp_name.toLowerCase().includes(search.toLowerCase()) ||
      c.corp_code.toLowerCase().includes(search.toLowerCase()),
    )
    .sort((a, b) => {
      let av: string | number, bv: string | number;
      if (sortKey === "corp_name") { av = a.corp_name; bv = b.corp_name; }
      else if (sortKey === "corp_code") { av = a.corp_code; bv = b.corp_code; }
      else if (sortKey === "report_count") { av = a.report_count; bv = b.report_count; }
      else { av = a.latest_analysis_date ?? ""; bv = b.latest_analysis_date ?? ""; }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });

  const handleDelete = async (c: Company) => {
    if (!confirm(`"${c.corp_name}"을(를) 삭제하시겠습니까?\n관련 보고서와 분석 데이터가 모두 삭제됩니다.`)) return;
    await deleteCompany(c.id);
    load();
  };

  const getStatusBadge = (c: Company) => {
    if (!c.is_active) {
      return (
        <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-text-tertiary">
          비활성
        </span>
      );
    }
    if (c.latest_analysis_date) {
      return (
        <span className="inline-flex items-center rounded-full bg-success-bg px-2.5 py-0.5 text-xs font-medium text-success">
          분석완료
        </span>
      );
    }
    if (c.report_count > 0) {
      return (
        <span className="inline-flex items-center rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning">
          보고서만
        </span>
      );
    }
    return (
      <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-text-tertiary">
        대기
      </span>
    );
  };

  return (
    <div>
      {/* Page Header */}
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-navy">
            분석 대상 기업
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            OpenDART 사업보고서 기반 기업 분석 대시보드
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="btn btn-primary"
        >
          + 기업 등록
        </button>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="기업명 또는 기업코드 검색..."
          className="w-full max-w-sm rounded-lg border border-border bg-surface px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent/20"
        />
        {allTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {allTags.map((tag) => {
              const active = selectedTagIds.includes(tag.id);
              return (
                <button
                  key={tag.id}
                  onClick={() => toggleTagFilter(tag.id)}
                  style={
                    active
                      ? { backgroundColor: tag.color, color: "#fff", borderColor: tag.color }
                      : { color: tag.color, borderColor: tag.color + "60" }
                  }
                  className="rounded-full border px-3 py-1 text-xs font-medium transition-all hover:opacity-80"
                >
                  {tag.name}
                </button>
              );
            })}
            {selectedTagIds.length > 0 && (
              <button
                onClick={() => { setSelectedTagIds([]); load([]); }}
                className="rounded-full border border-border px-3 py-1 text-xs text-text-tertiary hover:text-text-primary"
              >
                초기화
              </button>
            )}
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-background/50">
              <th
                className="cursor-pointer px-6 py-3.5 text-left font-semibold text-text-secondary hover:text-text-primary"
                onClick={() => toggleSort("corp_name")}
              >
                기업명<SortIcon col="corp_name" />
              </th>
              <th
                className="cursor-pointer px-6 py-3.5 text-left font-semibold text-text-secondary hover:text-text-primary"
                onClick={() => toggleSort("corp_code")}
              >
                종목코드<SortIcon col="corp_code" />
              </th>
              <th
                className="cursor-pointer px-6 py-3.5 text-center font-semibold text-text-secondary hover:text-text-primary"
                onClick={() => toggleSort("report_count")}
              >
                보고서<SortIcon col="report_count" />
              </th>
              <th
                className="cursor-pointer px-6 py-3.5 text-left font-semibold text-text-secondary hover:text-text-primary"
                onClick={() => toggleSort("latest_analysis_date")}
              >
                최근 분석<SortIcon col="latest_analysis_date" />
              </th>
              <th className="px-6 py-3.5 text-center font-semibold text-text-secondary">상태</th>
              <th className="px-6 py-3.5 text-right font-semibold text-text-secondary">작업</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-text-tertiary">
                  로딩 중...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-text-tertiary">
                  {companies.length === 0
                    ? "등록된 기업이 없습니다. 기업을 등록해주세요."
                    : "검색 결과가 없습니다."}
                </td>
              </tr>
            ) : (
              filtered.map((c) => (
                <tr
                  key={c.id}
                  className={`border-b border-border transition-colors last:border-b-0 hover:bg-background/30 ${
                    !c.is_active ? "opacity-60" : ""
                  }`}
                >
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Link
                        to={`/companies/${c.id}`}
                        className="font-medium text-navy hover:text-accent"
                      >
                        {c.corp_name}
                      </Link>
                      {!c.is_active && (
                        <span className="text-xs text-text-tertiary">(비활성)</span>
                      )}
                      {c.tags.slice(0, 3).map((tag) => (
                        <TagChip key={tag.id} tag={tag} size="xs" />
                      ))}
                      {c.tags.length > 3 && (
                        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-text-tertiary">
                          +{c.tags.length - 3}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs text-text-secondary">
                    {c.stock_code || "—"}
                  </td>
                  <td className="px-6 py-4 text-center text-text-secondary">
                    {c.report_count}건
                  </td>
                  <td className="px-6 py-4 text-text-secondary">
                    {c.latest_analysis_date
                      ? new Date(c.latest_analysis_date).toLocaleDateString("ko-KR")
                      : "—"}
                  </td>
                  <td className="px-6 py-4 text-center">{getStatusBadge(c)}</td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-3">
                      <Link
                        to={`/companies/${c.id}`}
                        className="text-accent hover:underline"
                      >
                        상세
                      </Link>
                      <button
                        onClick={() => setEditTarget(c)}
                        className="btn btn-text"
                      >
                        수정
                      </button>
                      <button
                        onClick={() => handleDelete(c)}
                        className="btn btn-text-danger"
                      >
                        삭제
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <CompanyForm
        open={showForm}
        onClose={() => setShowForm(false)}
        onCreated={load}
      />

      <CompanyEditModal
        company={editTarget}
        onClose={() => setEditTarget(null)}
        onUpdated={load}
      />
    </div>
  );
}
