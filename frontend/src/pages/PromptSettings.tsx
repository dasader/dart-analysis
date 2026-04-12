import { useEffect, useState } from "react";
import { fetchPrompts, updatePrompt } from "../api/client";
import type { PromptTemplate } from "../types";

export default function PromptSettings() {
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  // 편집 상태를 별도로 관리
  const [edits, setEdits] = useState<
    Record<string, { system_prompt: string; user_prompt_template: string }>
  >({});

  useEffect(() => {
    fetchPrompts()
      .then((data) => {
        setPrompts(data);
        const initial: typeof edits = {};
        for (const p of data) {
          initial[p.analysis_type] = {
            system_prompt: p.system_prompt,
            user_prompt_template: p.user_prompt_template,
          };
        }
        setEdits(initial);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (analysisType: string) => {
    const edit = edits[analysisType];
    if (!edit) return;
    setSaving(analysisType);
    setSaved(null);
    try {
      await updatePrompt(analysisType, edit);
      setSaved(analysisType);
      setTimeout(() => setSaved(null), 2000);
    } catch (e: any) {
      alert(e.message);
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
        <h1 className="text-2xl font-bold tracking-tight text-navy">
          프롬프트 설정
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Gemini LLM 분석에 사용되는 프롬프트를 편집합니다. 변경 즉시 반영됩니다.
        </p>
      </div>

      {/* 플레이스홀더 안내 */}
      <div className="mb-6 rounded-lg border border-border bg-surface px-5 py-4">
        <h3 className="mb-2 text-sm font-semibold text-text-primary">
          사용 가능한 플레이스홀더
        </h3>
        <div className="flex flex-wrap gap-3 text-sm">
          <code className="rounded bg-background px-2 py-1 font-mono text-xs text-accent">
            {"{corp_name}"}
          </code>
          <span className="text-text-secondary">기업명</span>
          <code className="rounded bg-background px-2 py-1 font-mono text-xs text-accent">
            {"{fiscal_year}"}
          </code>
          <span className="text-text-secondary">사업연도</span>
          <code className="rounded bg-background px-2 py-1 font-mono text-xs text-accent">
            {"{report_text}"}
          </code>
          <span className="text-text-secondary">
            보고서 전문 (유저 프롬프트에서 사용)
          </span>
        </div>
      </div>

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
                <button
                  onClick={() => handleSave(p.analysis_type)}
                  disabled={saving === p.analysis_type}
                  className="btn btn-primary"
                >
                  {saving === p.analysis_type ? "저장중..." : "저장"}
                </button>
              </div>
            </div>

            <div className="space-y-4 p-6">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  시스템 프롬프트
                </label>
                <textarea
                  value={edits[p.analysis_type]?.system_prompt ?? ""}
                  onChange={(e) =>
                    setEdits((prev) => ({
                      ...prev,
                      [p.analysis_type]: {
                        ...prev[p.analysis_type],
                        system_prompt: e.target.value,
                      },
                    }))
                  }
                  rows={12}
                  className="w-full rounded-lg border border-border bg-background px-4 py-3 font-mono text-sm leading-relaxed text-text-primary outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/20"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  유저 프롬프트 템플릿
                </label>
                <textarea
                  value={
                    edits[p.analysis_type]?.user_prompt_template ?? ""
                  }
                  onChange={(e) =>
                    setEdits((prev) => ({
                      ...prev,
                      [p.analysis_type]: {
                        ...prev[p.analysis_type],
                        user_prompt_template: e.target.value,
                      },
                    }))
                  }
                  rows={6}
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
