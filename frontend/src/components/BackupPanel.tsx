import { useEffect, useRef, useState } from "react";
import { downloadBackup, fetchBackupStatus, uploadBackup } from "../api/client";
import { getErrorMessage } from "../lib/errors";
import AdminButton from "./AdminButton";

type Kind = "corps" | "db" | "applicant-corps";

/** 새 서버로 옮길 때 쓰는 데이터 이관 패널.
 *
 *  dart_corps의 법인번호를 다시 채우려면 DART를 3,983번 불러야 하고 분당 제한 때문에
 *  20분 넘게 걸린다(IP 차단 위험도 있다). 파일로 옮기는 편이 안전하다. */
export default function BackupPanel() {
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [busy, setBusy] = useState<Kind | "download-corps" | "download-db" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const inputs = {
    corps: useRef<HTMLInputElement>(null),
    db: useRef<HTMLInputElement>(null),
    "applicant-corps": useRef<HTMLInputElement>(null),
  };

  const load = () => fetchBackupStatus().then(setCounts).catch(() => {});
  useEffect(() => {
    load();
  }, []);

  const handleDownload = async (kind: "corps" | "db") => {
    setBusy(`download-${kind}` as const);
    setError(null);
    setDone(null);
    try {
      await downloadBackup(kind);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const handleUpload = async (kind: Kind, file: File, confirmMsg?: string) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    setBusy(kind);
    setError(null);
    setDone(null);
    try {
      const r = await uploadBackup(kind, file);
      const c = (r.counts ?? r) as Record<string, number>;
      setDone(
        kind === "applicant-corps"
          ? `적재 완료: ${c.before?.toLocaleString()} → ${c.after?.toLocaleString()}건`
          : `복원 완료: 출원인 ${c.applicant_corps?.toLocaleString()}건 / ` +
            `DART 색인 ${c.dart_corps?.toLocaleString()}건`,
      );
      await load();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(null);
      inputs[kind].current!.value = "";   // 같은 파일을 다시 고를 수 있게
    }
  };

  const pick = (kind: Kind) => inputs[kind].current?.click();

  return (
    <div className="mb-8 rounded-xl border border-border bg-surface p-6 shadow-sm">
      <h2 className="text-sm font-semibold text-text-primary">데이터 이관</h2>
      <p className="mt-1 text-xs text-text-tertiary">
        새 서버로 옮길 때 씁니다. DART 색인을 처음부터 채우려면 API를 3,983번 호출해야 하고
        20분 넘게 걸리므로, 파일로 옮기는 편이 안전합니다.
      </p>

      {counts && (
        <div className="mt-3 flex gap-4 text-xs text-text-secondary">
          <span>출원인 법인번호 <b className="text-text-primary tabular-nums">
            {counts.applicant_corps?.toLocaleString() ?? 0}</b>건</span>
          <span>DART 색인 <b className="text-text-primary tabular-nums">
            {counts.dart_corps?.toLocaleString() ?? 0}</b>건</span>
        </div>
      )}

      {error && (
        <div className="mt-3 rounded-lg bg-danger-bg px-3 py-2 text-xs text-danger">{error}</div>
      )}
      {done && (
        <div className="mt-3 rounded-lg bg-success-bg px-3 py-2 text-xs text-success">{done}</div>
      )}

      <div className="mt-4 space-y-3 border-t border-border pt-4">
        <Row
          title="법인 데이터"
          hint="출원인 법인번호 + DART 색인만. 기업·보고서·분석은 건드리지 않습니다 (약 22MB)"
        >
          <AdminButton onClick={() => handleDownload("corps")}
                       disabled={busy !== null} className="btn btn-outline btn-sm">
            {busy === "download-corps" ? "준비 중..." : "내려받기"}
          </AdminButton>
          <AdminButton onClick={() => pick("corps")}
                       disabled={busy !== null} className="btn btn-outline btn-sm">
            {busy === "corps" ? "복원 중..." : "복원"}
          </AdminButton>
        </Row>

        <Row
          title="전체 DB"
          hint="분석 결과까지 전부. 복원하면 지금 데이터가 모두 사라집니다 (약 90MB)"
        >
          <AdminButton onClick={() => handleDownload("db")}
                       disabled={busy !== null} className="btn btn-outline btn-sm">
            {busy === "download-db" ? "준비 중..." : "내려받기"}
          </AdminButton>
          <AdminButton onClick={() => pick("db")}
                       disabled={busy !== null} className="btn btn-danger btn-sm">
            {busy === "db" ? "복원 중..." : "복원"}
          </AdminButton>
        </Row>

        <Row
          title="KIPRIS 출원인 벌크"
          hint="KIPRIS Plus에서 받은 ZIP(또는 TXT)을 올리면 출원인 법인번호를 전량 교체합니다"
        >
          <AdminButton onClick={() => pick("applicant-corps")}
                       disabled={busy !== null} className="btn btn-outline btn-sm">
            {busy === "applicant-corps" ? "적재 중..." : "파일 올리기"}
          </AdminButton>
        </Row>
      </div>

      {/* 숨은 file input들 — 버튼 모양을 맞추려고 label 대신 ref로 연다 */}
      <input ref={inputs.corps} type="file" accept=".gz,.sqlite3" className="hidden"
             onChange={(e) => e.target.files?.[0] && handleUpload(
               "corps", e.target.files[0],
               "법인 데이터(출원인 법인번호 · DART 색인)를 올린 파일로 전량 교체합니다.\n" +
               "기업·보고서·분석 결과는 그대로 남습니다. 계속할까요?")} />
      <input ref={inputs.db} type="file" accept=".gz,.sqlite3" className="hidden"
             onChange={(e) => e.target.files?.[0] && handleUpload(
               "db", e.target.files[0],
               "⚠ 전체 DB를 올린 파일로 교체합니다.\n" +
               "지금의 기업·보고서·분석 결과가 모두 사라집니다. 계속할까요?")} />
      <input ref={inputs["applicant-corps"]} type="file" accept=".zip,.txt" className="hidden"
             onChange={(e) => e.target.files?.[0] && handleUpload(
               "applicant-corps", e.target.files[0],
               "출원인 법인번호를 올린 파일로 전량 교체합니다. 계속할까요?")} />
    </div>
  );
}

function Row({ title, hint, children }: {
  title: string; hint: string; children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="text-sm font-medium text-text-primary">{title}</div>
        <div className="mt-0.5 text-xs text-text-tertiary">{hint}</div>
      </div>
      <div className="flex shrink-0 gap-2">{children}</div>
    </div>
  );
}
