import { useState } from "react";
import CompanySearch from "./CompanySearch";
import Modal from "./Modal";
import { createCompany } from "../api/client";
import { getErrorMessage } from "../lib/errors";
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
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="기업 등록" onClose={onClose} widthClass="max-w-lg">
      <p className="mb-4 text-sm text-text-secondary">
        OpenDART에서 기업을 검색하고 선택하면 자동으로 등록됩니다.
      </p>

      <CompanySearch onSelect={handleSelect} />

      {loading && <p className="mt-3 text-sm text-text-secondary">등록 중...</p>}
      {error && <p className="mt-3 text-sm text-danger">{error}</p>}
    </Modal>
  );
}
