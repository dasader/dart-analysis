import { useState } from "react";
import { downloadReports } from "../api/client";

interface Props {
  open: boolean;
  companyId: number;
  onClose: () => void;
  onDownloaded: () => void;
}

export default function DownloadModal({
  open,
  companyId,
  onClose,
  onDownloaded,
}: Props) {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  const handleDownload = async () => {
    setLoading(true);
    setError("");
    try {
      await downloadReports(companyId, { fiscal_year: year });
      onDownloaded();
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
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text-primary">
            보고서 다운로드
          </h2>
          <button
            onClick={onClose}
            className="text-text-tertiary transition-colors hover:text-text-primary"
          >
            ✕
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-text-secondary">
              사업연도
            </label>
            <select
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus:border-accent"
            >
              {Array.from({ length: 10 }, (_, i) => currentYear - i).map(
                (y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ),
              )}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-text-secondary">
              보고서 유형
            </label>
            <div className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-text-secondary">
              사업보고서
            </div>
            <p className="mt-1 text-xs text-text-tertiary">
              반기·분기보고서는 수집 대상에서 제외됩니다.
            </p>
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <button
            onClick={handleDownload}
            disabled={loading}
            className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-light disabled:opacity-50"
          >
            {loading ? "다운로드 중..." : "다운로드 시작"}
          </button>
        </div>
      </div>
    </div>
  );
}
