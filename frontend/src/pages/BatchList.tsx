import { useEffect, useState } from "react";
import { cancelBatch, fetchBatches, fetchQueueStatus } from "../api/client";
import { getErrorMessage } from "../lib/errors";
import AdminButton from "../components/AdminButton";
import type { BatchJob, QueueStatus } from "../types";

/** JOB_STATE_* → 한글 라벨 + 배지 색 */
const STATE_LABEL: Record<string, { text: string; cls: string }> = {
  JOB_STATE_PENDING: { text: "대기", cls: "bg-slate-100 text-slate-700" },
  JOB_STATE_RUNNING: { text: "처리중", cls: "bg-blue-100 text-blue-700" },
  JOB_STATE_SUCCEEDED: { text: "완료", cls: "bg-green-100 text-green-700" },
  JOB_STATE_FAILED: { text: "실패", cls: "bg-red-100 text-red-700" },
  JOB_STATE_CANCELLED: { text: "취소됨", cls: "bg-slate-100 text-slate-600" },
  JOB_STATE_EXPIRED: { text: "만료", cls: "bg-amber-100 text-amber-700" },
};

function elapsed(from: string | null, to: string | null): string {
  if (!from) return "-";
  const ms = new Date(to ?? Date.now()).getTime() - new Date(from).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 60) return `${min}분`;
  return `${Math.floor(min / 60)}시간 ${min % 60}분`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export default function BatchList() {
  const [jobs, setJobs] = useState<BatchJob[]>([]);
  const [queue, setQueue] = useState<QueueStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    Promise.all([fetchBatches(), fetchQueueStatus()])
      .then(([b, q]) => {
        setJobs(b);
        setQueue(q);
        setError(null);
      })
      .catch((e) => setError(getErrorMessage(e)))
      .finally(() => setLoading(false));

  // 진행 중인 작업이 있으면 주기적으로 갱신 (batch turnaround는 분 단위)
  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  const handleCancel = async (job: BatchJob) => {
    if (!window.confirm(`이 작업을 취소할까요? (보고서 ${job.report_ids.length}건)`)) return;
    try {
      await cancelBatch(job.id);
      await load();
    } catch (e) {
      alert(getErrorMessage(e));
    }
  };

  if (loading) return <div className="p-6 text-muted">불러오는 중...</div>;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">분석 작업 현황</h1>
          <p className="mt-1 text-sm text-muted">
            분석은 Gemini Batch API로 처리됩니다. 통상 수 분 내 완료되며, 최대 24시간까지
            걸릴 수 있습니다.
          </p>
        </div>
        {queue && (
          <div className="flex gap-4 text-sm">
            <span className="text-muted">
              제출 대기 <b className="text-foreground">{queue.pending_count}</b>
            </span>
            <span className="text-muted">
              처리중 <b className="text-foreground">{queue.running_batches}</b>개 작업
              {" / "}
              <b className="text-foreground">{queue.running_reports}</b>개 보고서
            </span>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {jobs.length === 0 ? (
        <div className="rounded border border-border bg-white px-6 py-12 text-center text-muted">
          아직 제출된 분석 작업이 없습니다.
        </div>
      ) : (
        <div className="overflow-x-auto rounded border border-border bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-slate-50 text-left text-xs uppercase text-muted">
              <tr>
                <th className="px-4 py-3 font-medium">제출</th>
                <th className="px-4 py-3 font-medium">상태</th>
                <th className="px-4 py-3 font-medium">보고서</th>
                <th className="px-4 py-3 font-medium">성공/실패</th>
                <th className="px-4 py-3 font-medium">경과</th>
                <th className="px-4 py-3 font-medium">모델</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const badge = STATE_LABEL[job.state] ?? {
                  text: job.state,
                  cls: "bg-slate-100 text-slate-700",
                };
                return (
                  <tr key={job.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 whitespace-nowrap">
                      {formatTime(job.submitted_at)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${badge.cls}`}>
                        {badge.text}
                      </span>
                      {job.error_message && (
                        <div
                          className="mt-1 max-w-md truncate text-xs text-red-600"
                          title={job.error_message}
                        >
                          {job.error_message}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">{job.report_ids.length}건</td>
                    <td className="px-4 py-3">
                      <span className="text-green-700">{job.success_count}</span>
                      {" / "}
                      <span className={job.failed_count > 0 ? "text-red-600" : ""}>
                        {job.failed_count}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted">
                      {elapsed(job.submitted_at, job.completed_at)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-xs text-muted">
                      {job.model_name}
                      <span className="ml-1 opacity-60">({job.thinking_level})</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {!job.is_terminal && (
                        <AdminButton
                          onClick={() => handleCancel(job)}
                          className="text-xs text-red-600 hover:underline"
                        >
                          취소
                        </AdminButton>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
