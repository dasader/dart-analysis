import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchCompanies } from "../api/client";
import CompanyForm from "../components/CompanyForm";
import type { Company } from "../types";

export default function CompanyList() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    fetchCompanies()
      .then(setCompanies)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const filtered = companies.filter((c) =>
    c.corp_name.toLowerCase().includes(search.toLowerCase()),
  );

  const getStatusBadge = (c: Company) => {
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
          className="rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-accent-light hover:shadow-md"
        >
          + 기업 등록
        </button>
      </div>

      {/* Search */}
      <div className="mb-6">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="등록된 기업 검색..."
          className="w-full max-w-sm rounded-lg border border-border bg-surface px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent/20"
        />
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-background/50">
              <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">
                기업명
              </th>
              <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">
                종목코드
              </th>
              <th className="px-6 py-3.5 text-center font-semibold text-text-secondary">
                보고서
              </th>
              <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">
                최근 분석
              </th>
              <th className="px-6 py-3.5 text-center font-semibold text-text-secondary">
                상태
              </th>
              <th className="px-6 py-3.5 text-right font-semibold text-text-secondary" />
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
                  className="border-b border-border transition-colors last:border-b-0 hover:bg-background/30"
                >
                  <td className="px-6 py-4">
                    <Link
                      to={`/companies/${c.id}`}
                      className="font-medium text-navy hover:text-accent"
                    >
                      {c.corp_name}
                    </Link>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs text-text-secondary">
                    {c.stock_code || "—"}
                  </td>
                  <td className="px-6 py-4 text-center font-mono text-text-secondary">
                    {c.report_count}건
                  </td>
                  <td className="px-6 py-4 text-text-secondary">
                    {c.latest_analysis_date
                      ? new Date(c.latest_analysis_date).toLocaleDateString("ko-KR")
                      : "—"}
                  </td>
                  <td className="px-6 py-4 text-center">{getStatusBadge(c)}</td>
                  <td className="px-6 py-4 text-right">
                    <Link
                      to={`/companies/${c.id}`}
                      className="text-sm text-accent hover:underline"
                    >
                      상세 →
                    </Link>
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
    </div>
  );
}
