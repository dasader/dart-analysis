import { useState } from "react";
import CompanySearch from "./CompanySearch";
import { createCompany } from "../api/client";
import type { CompanySearchResult } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export default function CompanyForm({ open, onClose, onCreated }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  const handleSelect = async (result: CompanySearchResult) => {
    setLoading(true);
    setError("");
    try {
      await createCompany({
        corp_code: result.corp_code,
        corp_name: result.corp_name,
        stock_code: result.stock_code,
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-border bg-surface p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text-primary">
            기업 등록
          </h2>
          <button
            onClick={onClose}
            className="text-text-tertiary transition-colors hover:text-text-primary"
          >
            ✕
          </button>
        </div>

        <p className="mb-4 text-sm text-text-secondary">
          OpenDART에서 기업을 검색하고 선택하면 자동으로 등록됩니다.
        </p>

        <CompanySearch onSelect={handleSelect} />

        {loading && (
          <p className="mt-3 text-sm text-text-secondary">등록 중...</p>
        )}
        {error && (
          <p className="mt-3 text-sm text-danger">{error}</p>
        )}
      </div>
    </div>
  );
}
