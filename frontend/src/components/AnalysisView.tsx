import AdminButton from "./AdminButton";
import Markdown from "./Markdown";
import type { Analysis } from "../types";

interface Props {
  /** 이 보고서·이 유형의 분석. 아직 요청된 적 없으면 undefined */
  analysis: Analysis | undefined;
  onRun: () => void;
  running: boolean;
}

/** 보고서 1건 × 분석 유형 1개의 결과를 상태에 따라 보여준다. */
export default function AnalysisView({ analysis, onRun, running }: Props) {
  if (analysis?.status === "completed") {
    return (
      <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <div className="mb-4 flex items-center gap-3 border-b border-border pb-4">
          <span className="text-xs text-text-tertiary">
            분석일: {new Date(analysis.updated_at).toLocaleDateString("ko-KR")}
          </span>
          {analysis.model_name && (
            <span className="font-mono text-xs text-text-tertiary">
              {analysis.model_name}
            </span>
          )}
        </div>
        <Markdown>{analysis.result_summary || ""}</Markdown>
      </div>
    );
  }

  if (analysis && (analysis.status === "pending" || analysis.status === "running")) {
    return (
      <div className="flex flex-col items-center rounded-xl border border-border bg-surface py-16">
        <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent" />
        <p className="text-sm text-text-secondary">
          {analysis.status === "pending"
            ? "제출 대기 중입니다..."
            : "Batch 처리 중입니다..."}
        </p>
        {/* 실시간 호출이 아니라 Batch라 분 단위가 걸린다 — 기다려도 된다고 알린다 */}
        <p className="mt-1 text-xs text-text-tertiary">
          보통 수 분 내 완료됩니다. 이 페이지를 벗어나도 계속 진행됩니다.
        </p>
      </div>
    );
  }

  if (analysis?.status === "failed") {
    return (
      <div className="rounded-xl border border-danger/30 bg-danger-bg p-6">
        <p className="mb-2 font-medium text-danger">분석 실패</p>
        <p className="text-sm text-text-secondary">{analysis.error_message}</p>
        <AdminButton onClick={onRun} disabled={running} className="btn btn-action mt-4">
          {running ? "요청 중..." : "재시도"}
        </AdminButton>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-surface py-16 text-center">
      <p className="mb-4 text-sm text-text-tertiary">
        아직 이 유형의 분석이 수행되지 않았습니다.
      </p>
      <AdminButton onClick={onRun} disabled={running} className="btn btn-action">
        {running ? "요청 중..." : "분석 실행"}
      </AdminButton>
    </div>
  );
}
