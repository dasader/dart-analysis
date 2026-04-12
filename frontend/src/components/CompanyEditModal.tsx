import { useState } from "react";
import { updateCompany } from "../api/client";
import type { Company } from "../types";

interface Props {
  company: Company | null;
  onClose: () => void;
  onUpdated: () => void;
}

export default function CompanyEditModal({ company, onClose, onUpdated }: Props) {
  const [corpName, setCorpName] = useState(company?.corp_name ?? "");
  const [stockCode, setStockCode] = useState(company?.stock_code ?? "");
  const [isActive, setIsActive] = useState(company?.is_active ?? true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!company) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await updateCompany(company.id, {
        corp_name: corpName.trim(),
        stock_code: stockCode.trim() || undefined,
        is_active: isActive,
      });
      onUpdated();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-xl">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text-primary">기업 정보 수정</h2>
          <button onClick={onClose} className="btn-close">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              기업명
            </label>
            <input
              type="text"
              value={corpName}
              onChange={(e) => setCorpName(e.target.value)}
              required
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-text-primary outline-none focus:border-accent focus:ring-1 focus:ring-accent/20"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              종목코드 <span className="text-text-tertiary">(선택)</span>
            </label>
            <input
              type="text"
              value={stockCode}
              onChange={(e) => setStockCode(e.target.value)}
              placeholder="예: 005930"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono text-text-primary outline-none focus:border-accent focus:ring-1 focus:ring-accent/20"
            />
          </div>

          <div className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2.5">
            <input
              id="is_active"
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="h-4 w-4 rounded border-border accent-accent"
            />
            <label htmlFor="is_active" className="text-sm text-text-primary cursor-pointer">
              활성화 (스케줄러 자동 보고서 수집 대상)
            </label>
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="btn btn-outline"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary"
            >
              {loading ? "저장 중..." : "저장"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
