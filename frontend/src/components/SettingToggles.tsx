import { useEffect, useState } from "react";
import { fetchAppSettings, updateAppSetting } from "../api/client";
import { getErrorMessage } from "../lib/errors";
import AdminButton from "./AdminButton";
import type { AppSetting } from "../types";

/** 끄면 비용이 크게 늘어나는 설정 — 확인을 한 번 받는다 */
const COST_WARNING: Record<string, string> = {
  section_extract_enabled:
    "구역 추출을 끄면 보고서 전문이 AI에 전달되어 분석 비용이 약 8배로 늘어납니다.\n계속할까요?",
};

export default function SettingToggles() {
  const [items, setItems] = useState<AppSetting[]>([]);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAppSettings()
      .then(setItems)
      .catch((e) => setError(getErrorMessage(e)));
  }, []);

  const toggle = async (item: AppSetting) => {
    const next = !item.value;
    if (next === false && COST_WARNING[item.key] && !window.confirm(COST_WARNING[item.key])) {
      return;
    }
    setSaving(item.key);
    setError(null);
    try {
      const updated = await updateAppSetting(item.key, next);
      setItems((prev) => prev.map((i) => (i.key === item.key ? updated : i)));
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setSaving(null);
    }
  };

  if (items.length === 0) return null;

  return (
    <div className="mb-6 rounded-xl border border-border bg-surface shadow-sm">
      <div className="border-b border-border px-6 py-4">
        <h2 className="font-semibold text-navy">동작 설정</h2>
        <p className="mt-0.5 text-xs text-text-tertiary">
          변경 즉시 반영됩니다. 서버 재시작이 필요하지 않습니다.
        </p>
      </div>

      {error && (
        <div className="border-b border-border bg-warning-bg px-6 py-2 text-sm text-warning">
          {error}
        </div>
      )}

      <div className="divide-y divide-border">
        {items.map((item) => (
          <div key={item.key} className="flex items-start gap-4 px-6 py-4">
            <div className="min-w-0 flex-1">
              <div className="font-medium text-text-primary">{item.label}</div>
              <p className="mt-0.5 text-sm text-text-secondary">{item.description}</p>
              <span className="font-mono text-xs text-text-tertiary">{item.key}</span>
            </div>
            <AdminButton
              type="button"
              role="switch"
              aria-checked={item.value}
              aria-label={item.label}
              disabled={saving === item.key}
              onClick={() => toggle(item)}
              className={`mt-1 flex h-6 w-11 shrink-0 items-center rounded-full px-0.5 transition-colors ${
                item.value ? "justify-end bg-accent" : "justify-start bg-slate-400"
              }`}
            >
              <span className="block h-5 w-5 rounded-full bg-white shadow" />
            </AdminButton>
          </div>
        ))}
      </div>
    </div>
  );
}
