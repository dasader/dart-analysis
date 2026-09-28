import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  cancelBatch,
  fetchBatches,
  fetchExtractionFailures,
  fetchQueueStatus,
} from "../api/client";
import { getErrorMessage } from "../lib/errors";
import AdminButton from "../components/AdminButton";
import type { BatchJob, ExtractionFailure, QueueStatus } from "../types";
import { usePolling } from "../hooks/usePolling";

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
  const [failures, setFailures] = useState<ExtractionFailure[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    Promise.all([fetchBatches(), fetchQueueStatus(), fetchExtractionFailures()])
      .then(([b, q, f]) => {
        setJobs(b);
        setQueue(q);
        setFailures(f);
        setError(null);
      })
      .catch((e) => setError(getErrorMessage(e)))
      .finally(() => setLoading(false));

  // 15초마다 갱신한다(batch turnaround는 분 단위). 한가할 때도 도는 건 다른 곳에서
  // 새로 제출한 작업이 이 화면에 저절로 나타나게 하기 위해서다
  useEffect(() => {
    load();
  }, []);
  usePolling(load, 15000);

  const handleCancel = async (job: BatchJob) => {
    if (!window.confirm(`이 작업을 취소할까요? (보고서 ${job.report_ids.length}건)`)) return;
    try {
      await cancelBatch(job.id);
      await load();
    } catch (e) {
      alert(getErrorMessage(e));
    }
  };

  if (loading) return <div className="p-6 text-text-secondary">불러오는 중...</div>;

  return (
    <div>
      <div className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">분석 작업 현황</h1>
          <p className="mt-1 text-sm text-text-secondary">
            분석은 Gemini Batch API로 처리됩니다. 통상 수 분 내 완료되며, 최대 24시간까지
            걸릴 수 있습니다.
          </p>
        </div>
        {queue && (
          <div className="flex gap-4 text-sm">
            <span className="text-text-secondary">
              제출 대기 <b className="text-text-primary">{queue.pending_count}</b>
            </span>
            <span className="text-text-secondary">
              처리중 <b className="text-text-primary">{queue.running_batches}</b>개 작업
              {" / "}
              <b className="text-text-primary">{queue.running_reports}</b>개 보고서
            </span>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {failures.length > 0 && (
        <div
          role="alert"
          className="mb-6 rounded border-l-4 border-amber-500 bg-amber-50 px-5 py-4"
        >
          <h2 className="flex items-center gap-2 font-semibold text-amber-900">
            <span aria-hidden="true">⚠</span>
            보고서 구역 추출 실패 {failures.length}건 — 확인이 필요합니다
          </h2>
          <p className="mt-1 text-sm text-amber-800">
            보고서 서식이 예상과 달라 분석에 필요한 구역을 찾지 못했습니다.
            해당 보고서는 <b>AI에 전달되지 않았습니다</b>(비용이 발생하지 않았습니다).
            추출 규칙(<code className="font-mono text-xs">section_extract.py</code>) 수정이
            필요합니다.
          </p>
          <ul className="mt-3 space-y-1.5 text-sm">
            {failures.map((f) => (
              <li key={f.report_id} className="text-amber-900">
                <Link
                  to={`/companies/${f.company_id}`}
                  className="font-medium underline underline-offset-2"
                >
                  {f.corp_name}
                </Link>{" "}
                <span className="text-amber-700">
                  {f.fiscal_year}년 {f.report_name}
                </span>
                <div className="text-xs text-amber-700">{f.reason}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {jobs.length === 0 ? (
        <div className="rounded border border-border bg-white px-6 py-12 text-center text-text-secondary">
          아직 제출된 분석 작업이 없습니다.
        </div>
      ) : (
        <div className="overflow-x-auto rounded border border-border bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-slate-50 text-left text-xs uppercase text-text-secondary">
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
                    <td className="px-4 py-3 whitespace-nowrap text-text-secondary">
                      {elapsed(job.submitted_at, job.completed_at)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-xs text-text-secondary">
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
