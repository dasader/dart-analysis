import { useEffect, useState } from "react";
import { fetchTags, createTag, updateTag, deleteTag } from "../api/client";
import type { Tag } from "../types";
import { TAG_COLORS } from "../types";

export default function TagSettings() {
  const [tags, setTags] = useState<Tag[]>([]);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState(TAG_COLORS[0]);
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editColor, setEditColor] = useState("");
  const [error, setError] = useState("");

  const load = () => fetchTags().then(setTags).catch(() => {});
  useEffect(load, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!newName.trim()) return;
    try {
      await createTag({ name: newName.trim(), color: newColor });
      setNewName("");
      setNewColor(TAG_COLORS[0]);
      load();
    } catch (e: any) {
      setError(e.message);
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
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleDelete = async (tag: Tag) => {
    if (!confirm(`"${tag.name}" 태그를 삭제하시겠습니까?\n기업에서 할당된 태그도 해제됩니다.`)) return;
    await deleteTag(tag.id);
    load();
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-navy">태그 관리</h1>
        <p className="mt-1 text-sm text-text-secondary">
          기업에 할당할 태그를 미리 정의합니다.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-danger-bg px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}

      {/* 태그 생성 폼 */}
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
            <div className="flex flex-wrap gap-1.5">
              {TAG_COLORS.map((hex) => (
                <button
                  key={hex}
                  type="button"
                  onClick={() => setNewColor(hex)}
                  style={{ backgroundColor: hex }}
                  className={`h-7 w-7 rounded-full transition-transform hover:scale-110 ${
                    newColor === hex ? "ring-2 ring-offset-2 ring-gray-400 scale-110" : ""
                  }`}
                  title={hex}
                />
              ))}
            </div>
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

      {/* 태그 목록 */}
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
                      <span
                        style={{ backgroundColor: tag.color + "20", color: tag.color, border: `1px solid ${tag.color}40` }}
                        className="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium"
                      >
                        {tag.name}
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    {editId === tag.id ? (
                      <div className="flex flex-wrap gap-1.5">
                        {TAG_COLORS.map((hex) => (
                          <button
                            key={hex}
                            type="button"
                            onClick={() => setEditColor(hex)}
                            style={{ backgroundColor: hex }}
                            className={`h-6 w-6 rounded-full transition-transform hover:scale-110 ${
                              editColor === hex ? "ring-2 ring-offset-1 ring-gray-400 scale-110" : ""
                            }`}
                          />
                        ))}
                      </div>
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
                          <button onClick={() => handleDelete(tag)} className="btn btn-text-danger">
                            삭제
                          </button>
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
