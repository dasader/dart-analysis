import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createTechnology, fetchTechnologies } from "../api/client";
import { getErrorMessage } from "../lib/errors";
import AdminButton from "../components/AdminButton";
import { useAdmin } from "../context/AdminContext";
import type { Technology } from "../types";

function formatDate(iso: string | null): string {
  if (!iso) return "미실행";
  return new Date(iso).toLocaleDateString("ko-KR", {
    year: "2-digit", month: "2-digit", day: "2-digit",
  });
}

export default function TechnologyList() {
  const { isAdmin } = useAdmin();
  const [items, setItems] = useState<Technology[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () =>
    fetchTechnologies()
      .then(setItems)
      .catch((e) => setError(getErrorMessage(e)))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async () => {
    if (!name.trim() || !description.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createTechnology({ name: name.trim(), description: description.trim() });
      setName("");
      setDescription("");
      setShowForm(false);
      await load();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="py-16 text-center text-text-tertiary">불러오는 중...</div>;

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-navy">기술</h1>
          <p className="mt-1 text-sm text-text-secondary">
            기술을 등록하면 특허를 검색해 관련 기업을 찾고, 그 기업의 사업보고서 분석으로 이어집니다.
          </p>
        </div>
        <AdminButton onClick={() => setShowForm((v) => !v)} className="btn btn-primary">
          기술 등록
        </AdminButton>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-danger-bg px-4 py-3 text-sm text-danger">{error}</div>
      )}

      {showForm && isAdmin && (
        <div className="mb-6 rounded-xl border border-border bg-surface p-6 shadow-sm">
          <label className="block text-sm font-medium text-text-primary">기술명</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="전고체 배터리"
            className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
          <label className="mt-4 block text-sm font-medium text-text-primary">기술 설명</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="리튬이온 배터리의 액체 전해질을 고체로 대체해 안전성과 에너지 밀도를 높이는 기술..."
            className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
          <p className="mt-1 text-xs text-text-tertiary">
            설명에서 특허 검색어를 자동으로 뽑습니다. 등록 후 수정할 수 있습니다.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleCreate}
              disabled={saving || !name.trim() || !description.trim()}
              className="btn btn-primary disabled:opacity-50"
            >
              {saving ? "검색어 생성 중..." : "등록"}
            </button>
            <button onClick={() => setShowForm(false)} className="btn btn-ghost">
              취소
            </button>
          </div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface py-16 text-center text-sm text-text-tertiary">
          등록된 기술이 없습니다.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-background/50 text-left">
                <th className="px-5 py-3 font-semibold text-text-secondary">기술</th>
                <th className="px-5 py-3 text-center font-semibold text-text-secondary">추적 중</th>
                <th className="px-5 py-3 text-center font-semibold text-text-secondary">등록 가능</th>
                <th className="px-5 py-3 text-center font-semibold text-text-secondary">제외</th>
                <th className="px-5 py-3 font-semibold text-text-secondary">최근 스캔</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} className="border-b border-border last:border-0 hover:bg-background/30">
                  <td className="px-5 py-3.5">
                    <Link
                      to={`/technologies/${t.id}`}
                      className="font-medium text-text-primary hover:text-accent hover:underline"
                    >
                      {t.name}
                    </Link>
                    {!t.is_active && (
                      <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-text-tertiary">
                        비활성
                      </span>
                    )}
                    <div className="mt-0.5 line-clamp-1 text-xs text-text-tertiary">
                      {t.description}
                    </div>
                  </td>
                  <td className="px-5 py-3.5 text-center font-medium text-success">
                    {t.tracked_count}
                  </td>
                  <td className="px-5 py-3.5 text-center text-warning">{t.available_count}</td>
                  <td className="px-5 py-3.5 text-center text-text-tertiary">{t.excluded_count}</td>
                  <td className="px-5 py-3.5 text-text-secondary">
                    {formatDate(t.last_scanned_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
