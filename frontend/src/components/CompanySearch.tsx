import { useState } from "react";
import { searchCompanies } from "../api/client";
import type { CompanySearchResult } from "../types";

interface Props {
  onSelect: (result: CompanySearchResult) => void;
}

export default function CompanySearch({ onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompanySearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async () => {
    if (query.length < 2) return;
    setLoading(true);
    setError("");
    try {
      const data = await searchCompanies(query);
      setResults(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="기업명을 입력하세요 (2자 이상)"
          className="flex-1 rounded-md border border-border bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-accent"
        />
        <button
          onClick={handleSearch}
          disabled={loading || query.length < 2}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-light disabled:opacity-50"
        >
          {loading ? "검색중..." : "검색"}
        </button>
      </div>

      {error && (
        <p className="mt-2 text-sm text-danger">{error}</p>
      )}

      {results.length > 0 && (
        <div className="mt-3 max-h-64 overflow-y-auto rounded-md border border-border">
          {results.map((r) => (
            <button
              key={r.corp_code}
              onClick={() => onSelect(r)}
              className="flex w-full items-center justify-between border-b border-border px-4 py-3 text-left text-sm transition-colors last:border-b-0 hover:bg-background"
            >
              <div>
                <span className="font-medium text-text-primary">
                  {r.corp_name}
                </span>
                {r.stock_code && (
                  <span className="ml-2 font-mono text-xs text-text-tertiary">
                    {r.stock_code}
                  </span>
                )}
              </div>
              <span className="font-mono text-xs text-text-tertiary">
                {r.corp_code}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
