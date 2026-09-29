import { useEffect, useState } from "react";
import { fetchPrompts, updatePrompt } from "../api/client";
import { getErrorMessage } from "../lib/errors";
import AdminButton, { AdminNotice } from "../components/AdminButton";
import SettingToggles from "../components/SettingToggles";
import BackupPanel from "../components/BackupPanel";
import type { PromptTemplate } from "../types";

export default function PromptSettings() {
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  // 편집 중인 시스템 프롬프트(분석 유형별)
  const [edits, setEdits] = useState<Record<string, string>>({});

  useEffect(() => {
    fetchPrompts()
      .then((data) => {
        setPrompts(data);
        setEdits(Object.fromEntries(data.map((p) => [p.analysis_type, p.system_prompt])));
      })
      .finally(() => setLoading(false));
  }, []);

  // 저장 표시는 2초 뒤 지운다 — 연달아 저장해도 앞 타이머가 새 표시를 일찍 지우지 않게 effect로
  useEffect(() => {
    if (!saved) return;
    const t = setTimeout(() => setSaved(null), 2000);
    return () => clearTimeout(t);
  }, [saved]);

  const handleSave = async (analysisType: string) => {
    const systemPrompt = edits[analysisType];
    if (!systemPrompt) return;
    setSaving(analysisType);
    setSaved(null);
    try {
      await updatePrompt(analysisType, { system_prompt: systemPrompt });
      setSaved(analysisType);
    } catch (e) {
      alert(getErrorMessage(e));
    } finally {
      setSaving(null);
    }
  };

  if (loading) {
    return (
      <div className="py-16 text-center text-text-tertiary">로딩 중...</div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-navy">설정</h1>
        <p className="mt-1 text-sm text-text-secondary">
          분석 동작과 Gemini LLM 프롬프트를 편집합니다. 변경 즉시 반영됩니다.
        </p>
      </div>

      <AdminNotice />

      <SettingToggles />

      <BackupPanel />

      {/* 프롬프트 카드들 */}
      <div className="space-y-6">
        {prompts.map((p) => (
          <div
            key={p.analysis_type}
            className="rounded-xl border border-border bg-surface shadow-sm"
          >
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <div>
                <h2 className="font-semibold text-navy">{p.label}</h2>
                <span className="font-mono text-xs text-text-tertiary">
                  {p.analysis_type}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {saved === p.analysis_type && (
                  <span className="text-sm text-success">저장됨</span>
                )}
                <AdminButton
                  onClick={() => handleSave(p.analysis_type)}
                  disabled={saving === p.analysis_type}
                  className="btn btn-primary"
                >
                  {saving === p.analysis_type ? "저장중..." : "저장"}
                </AdminButton>
              </div>
            </div>

            <div className="space-y-4 p-6">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  시스템 프롬프트
                </label>
                <textarea
                  value={edits[p.analysis_type] ?? ""}
                  onChange={(e) =>
                    setEdits((prev) => ({ ...prev, [p.analysis_type]: e.target.value }))
                  }
                  rows={12}
                  className="w-full rounded-lg border border-border bg-background px-4 py-3 font-mono text-sm leading-relaxed text-text-primary outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/20"
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
