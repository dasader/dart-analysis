import { useState } from "react";
import Modal from "./Modal";
import { downloadReports } from "../api/client";
import { getErrorMessage } from "../lib/errors";

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
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="보고서 다운로드" onClose={onClose}>
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
            className="btn btn-primary w-full"
          >
            {loading ? "다운로드 중..." : "다운로드 시작"}
          </button>
        </div>
    </Modal>
  );
}
