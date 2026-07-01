import { useEffect, useState } from "react";
import { fetchTags, createTag, updateTag, deleteTag } from "../api/client";
import TagChip from "../components/TagChip";
import ColorPicker from "../components/ColorPicker";
import { getErrorMessage } from "../lib/errors";
import type { Tag } from "../types";
import { TAG_COLORS } from "../types";
import AdminButton from "../components/AdminButton";
import { useAdmin } from "../context/AdminContext";

export default function TagSettings() {
  const { isAdmin } = useAdmin();
  const [tags, setTags] = useState<Tag[]>([]);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState<string>(TAG_COLORS[0]);
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editColor, setEditColor] = useState("");
  const [error, setError] = useState("");

  const load = () => fetchTags().then(setTags).catch(() => {});
  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!newName.trim()) return;
    try {
      await createTag({ name: newName.trim(), color: newColor });
      setNewName("");
      setNewColor(TAG_COLORS[0]);
      load();
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  const startEdit = (tag: Tag) => {
    setEditId(tag.id);
    setEditName(tag.name);
    setEditColor(tag.color);
    setError("");
  };

  const handleUpdate = async (id: number) => {
    setError("");
    if (!editName.trim()) return;
    try {
      await updateTag(id, { name: editName.trim(), color: editColor });
      setEditId(null);
      load();
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  const handleDelete = async (tag: Tag) => {
    if (!confirm(`"${tag.name}" 태그를 삭제하시겠습니까?\n기업에서 할당된 태그도 해제됩니다.`)) return;
    try {
      await deleteTag(tag.id);
      load();
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-navy">태그 관리</h1>
        <p className="mt-1 text-sm text-text-secondary">
          기업에 할당할 태그를 미리 정의합니다.
        </p>
      </div>

      {!isAdmin && (
        <div className="mb-6 rounded-lg border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
          관리 기능을 사용하려면 우측 상단에서 관리자 로그인이 필요합니다.
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg bg-danger-bg px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}

      <div className="mb-8 rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h2 className="mb-4 text-sm font-semibold text-text-primary">새 태그 추가</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-48">
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              태그 이름
            </label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="예: 포트폴리오"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent focus:ring-1 focus:ring-accent/20"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              색상
            </label>
            <ColorPicker value={newColor} onChange={setNewColor} />
          </div>
          <button
            type="submit"
            disabled={!newName.trim()}
            className="btn btn-primary"
          >
            추가
          </button>
        </form>
      </div>

      <div className="rounded-xl border border-border bg-surface shadow-sm">
        {tags.length === 0 ? (
          <div className="py-12 text-center text-sm text-text-tertiary">
            태그가 없습니다. 위에서 태그를 추가해주세요.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-background/50">
                <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">태그</th>
                <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">색상</th>
                <th className="px-6 py-3.5 text-right font-semibold text-text-secondary">작업</th>
              </tr>
            </thead>
            <tbody>
              {tags.map((tag) => (
                <tr key={tag.id} className="border-b border-border transition-colors last:border-b-0 hover:bg-background/30">
                  <td className="px-6 py-4">
                    {editId === tag.id ? (
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className="w-full max-w-xs rounded border border-border px-2 py-1 text-sm outline-none focus:border-accent"
                        autoFocus
                      />
                    ) : (
                      <TagChip tag={tag} size="md" />
                    )}
                  </td>
                  <td className="px-6 py-4">
                    {editId === tag.id ? (
                      <ColorPicker value={editColor} onChange={setEditColor} size="sm" />
                    ) : (
                      <span
                        style={{ backgroundColor: tag.color }}
                        className="inline-block h-5 w-5 rounded-full"
                        title={tag.color}
                      />
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-3">
                      {editId === tag.id ? (
                        <>
                          <button onClick={() => handleUpdate(tag.id)} className="btn btn-link">
                            저장
                          </button>
                          <button onClick={() => setEditId(null)} className="btn btn-text">
                            취소
                          </button>
                        </>
                      ) : (
                        <>
                          <button onClick={() => startEdit(tag)} className="btn btn-text">
                            수정
                          </button>
                          <AdminButton onClick={() => handleDelete(tag)} className="btn btn-text-danger">
                            삭제
                          </AdminButton>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
