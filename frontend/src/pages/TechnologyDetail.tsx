import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  deleteTechnology, fetchTechnology, generateTechReport, scanTechnology, suggestKeywords,
  updateTechnology,
} from "../api/client";
import { getErrorMessage } from "../lib/errors";
import AdminButton from "../components/AdminButton";
import TechReport from "../components/TechReport";
import type { ScanResult, TechCompany, TechnologyDetail as TechDetail } from "../types";

const STATUS_META: Record<string, { title: string; hint: string; cls: string }> = {
  tracked: {
    title: "추적 중",
    hint: "사업보고서 분석 결과를 볼 수 있습니다",
    cls: "text-success",
  },
  available: {
    title: "등록 가능",
    hint: "특허는 많지만 아직 추적하지 않는 기업입니다. 등록하면 보고서 수집·분석이 시작됩니다",
    cls: "text-warning",
  },
  excluded: {
    title: "제외",
    hint: "대학·연구소·개인·외국기업이라 사업보고서가 없습니다",
    cls: "text-text-tertiary",
  },
};

function Section({ status, rows }: { status: string; rows: TechCompany[] }) {
  const meta = STATUS_META[status];
  if (!meta || rows.length === 0) return null;

  return (
    <div className="mb-6">
      <h3 className={`text-sm font-semibold ${meta.cls}`}>
        {meta.title} <span className="text-text-tertiary">({rows.length})</span>
      </h3>
      <p className="mb-2 text-xs text-text-tertiary">{meta.hint}</p>
      <div className="overflow-hidden rounded-xl border border-border bg-surface">
        <table className="w-full text-sm">
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} className="border-b border-border last:border-0">
                <td className="px-4 py-2.5">
                  {c.company_id ? (
                    <Link
                      to={`/companies/${c.company_id}`}
                      className="font-medium hover:text-accent hover:underline"
                    >
                      {c.corp_name}
                    </Link>
                  ) : (
                    <span className="font-medium">{c.corp_name || c.applicant_name}</span>
                  )}
                  {c.is_new && (
                    <span className="ml-2 rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                      신규
                    </span>
                  )}
                  {c.is_gone && (
                    <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-text-tertiary">
                      이번 스캔에 없음
                    </span>
                  )}
                  {c.corp_name && c.corp_name !== c.applicant_name && (
                    <div className="text-xs text-text-tertiary">특허: {c.applicant_name}</div>
                  )}
                  {c.exclude_reason && (
                    <div className="text-xs text-text-tertiary">{c.exclude_reason}</div>
                  )}
                </td>
                <td className="w-24 px-4 py-2.5 text-right text-text-secondary">
                  특허 {c.patent_count}건
                </td>
                <td className="w-32 px-4 py-2.5 text-right">
                  {/* 넓은 키워드 하나에만 걸린 기업은 연관성이 약하다 */}
                  <span
                    className={c.keyword_hits.length <= 1 ? "text-text-tertiary" : "text-text-secondary"}
                    title={c.keyword_hits.join(", ")}
                  >
                    키워드 {c.keyword_hits.length}개
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function TechnologyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const techId = Number(id);
  const navigate = useNavigate();

  const [tech, setTech] = useState<TechDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editKeywords, setEditKeywords] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [editMax, setEditMax] = useState<number | null>(null);
  const [reporting, setReporting] = useState(false);

  const load = useCallback(async () => {
    try {
      setTech(await fetchTechnology(techId));
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [techId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleScan = async (onboard: boolean) => {
    if (onboard) {
      // 상한이 0(전체)이면 몇 개가 걸릴지 미리 알려야 한다 — 비용이 기업 수만큼 곱해진다.
      // 다시 스캔하면 후보가 늘 수 있으므로 "최소" 몇 건인지로 말한다.
      const cap = tech?.max_companies ?? 0;
      const candidates = tech?.available_count ?? 0;
      const n = cap === 0 ? candidates : Math.min(cap, candidates);
      if (!window.confirm(
        (cap === 0
          ? `등록 가능한 기업 ${candidates}개사를 모두 등록하고 사업보고서를 분석합니다.\n`
          : `상위 ${cap}개 기업을 등록하고 사업보고서를 분석합니다(현재 후보 ${candidates}개).\n`) +
        `보고서 1건당 약 $0.014 — 지금 기준 약 $${(n * 0.0135).toFixed(2)}가 발생합니다.\n` +
        `계속할까요?`,
      )) return;
    }

    setScanning(true);
    setError(null);
    setScanResult(null);
    try {
      setScanResult(await scanTechnology(techId, onboard));
      await load();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setScanning(false);
    }
  };

  const handleReport = async () => {
    setReporting(true);
    setError(null);
    try {
      await generateTechReport(techId);
      await load();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setReporting(false);
    }
  };

  const handleSaveKeywords = async () => {
    if (editKeywords === null) return;
    const list = editKeywords.split(",").map((k) => k.trim()).filter(Boolean);
    try {
      await updateTechnology(techId, { keywords: list });
      setEditKeywords(null);
      await load();
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  // 뽑은 결과를 바로 저장하지 않고 입력창에 채운다 — 회차마다 달라지므로 사람이 보고 고른다
  const handleSuggest = async () => {
    setSuggesting(true);
    setError(null);
    try {
      const { keywords } = await suggestKeywords(techId);
      setEditKeywords(keywords.join(", "));
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setSuggesting(false);
    }
  };

  const handleSaveMax = async () => {
    if (editMax === null) return;
    try {
      await updateTechnology(techId, { max_companies: editMax });
      setEditMax(null);
      await load();
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("이 기술과 스캔 결과를 삭제합니다. 계속할까요?")) return;
    await deleteTechnology(techId);
    navigate("/technologies");
  };

  if (loading) return <div className="py-16 text-center text-text-tertiary">불러오는 중...</div>;
  if (!tech) {
    return (
      <div className="py-16 text-center text-text-tertiary">
        기술을 찾을 수 없습니다.{" "}
        <Link to="/technologies" className="text-accent underline">목록으로</Link>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <Link to="/technologies" className="text-sm text-text-tertiary hover:text-accent">
          ← 기술 목록
        </Link>
        <div className="mt-3 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-navy">{tech.name}</h1>
            <p className="mt-1 max-w-3xl text-sm text-text-secondary">{tech.description}</p>
          </div>
          <div className="flex gap-2">
            <AdminButton
              disabled={scanning}
              onClick={() => handleScan(false)}
              className="btn btn-outline btn-sm"
              title="특허를 다시 검색해 관련 기업을 갱신합니다 (비용 없음)"
            >
              {scanning ? "스캔 중..." : "스캔"}
            </AdminButton>
            <AdminButton
              disabled={scanning || tech.available_count === 0}
              onClick={() => handleScan(true)}
              className="btn btn-primary btn-sm"
              title="스캔 후 미등록 기업을 등록하고 분석까지 실행합니다"
            >
              스캔 + 분석
            </AdminButton>
            <AdminButton onClick={handleDelete} className="btn btn-danger btn-sm">
              삭제
            </AdminButton>
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-danger-bg px-4 py-3 text-sm text-danger">{error}</div>
      )}

      {/* 검색 키워드 */}
      <div className="mb-6 rounded-xl border border-border bg-surface px-5 py-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary">검색 키워드</h3>
          <AdminButton
            onClick={() =>
              setEditKeywords(editKeywords === null ? tech.keywords.join(", ") : null)
            }
            className="btn btn-text text-xs"
          >
            {editKeywords === null ? "편집" : "취소"}
          </AdminButton>
        </div>
        {editKeywords === null ? (
          <>
          <div className="mt-2 flex flex-wrap gap-2">
            {tech.keywords.map((k) => {
              // 마지막 스캔의 총건수. 넓으면 정밀도가 9%까지 떨어지기도 하지만
              // 그 분야 정식 용어라면 넓어도 정확하다 — 판정이 아니라 확인 신호다
              const stat = tech.keyword_stats.find((s) => s.word === k);
              return (
                <span
                  key={k}
                  title={stat?.broad ? "검색 결과가 2만 건을 넘습니다. 확인해 보세요" : undefined}
                  className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs ${
                    stat?.broad
                      ? "bg-amber-50 text-amber-800 ring-1 ring-amber-200"
                      : "bg-background text-text-secondary"
                  }`}
                >
                  {k}
                  {stat && (
                    <span className="tabular-nums opacity-70">
                      {stat.total.toLocaleString()}건{stat.broad ? " ⚠" : ""}
                    </span>
                  )}
                </span>
              );
            })}
          </div>
          {tech.keyword_stats.some((s) => s.broad) && (
            <p className="mt-2 text-xs text-amber-700">
              ⚠ 결과가 2만 건을 넘습니다. 산업 전체를 가리키는 일반어면 더 구체적인 층위로
              바꾸세요. 그 분야의 정식 용어라면 넓어도 정확합니다.
            </p>
          )}
          </>
        ) : (
          <div className="mt-2">
            <input
              value={editKeywords}
              onChange={(e) => setEditKeywords(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm"
            />
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-text-tertiary">
              <li>여러 개는 쉼표로 구분합니다</li>
              <li>띄어쓰기는 AND입니다. 붙여 쓴 복합어도 형태소로 쪼개져 각각 AND로 걸립니다</li>
              <li>
                소재명·공정명·구조명처럼 구체적으로 씁니다 —
                "치유·제어·융합" 같은 추상어는 엉뚱한 분야를 끌어옵니다
              </li>
              <li>
                검색식도 그대로 씁니다: <code className="font-mono">A*B</code> 둘 다,{" "}
                <code className="font-mono">A+B</code> 둘 중 하나,{" "}
                <code className="font-mono">A!B</code> 제외,{" "}
                <code className="font-mono">"A B"</code> 이 표현 그대로,{" "}
                <code className="font-mono">( )</code> 묶기
              </li>
            </ul>
            <div className="mt-2 flex items-center gap-2">
              <button onClick={handleSaveKeywords} className="btn btn-primary btn-sm">
                저장
              </button>
              <AdminButton
                onClick={handleSuggest}
                disabled={suggesting}
                className="btn btn-outline btn-sm"
              >
                {suggesting ? "뽑는 중…" : "설명문으로 다시 뽑기"}
              </AdminButton>
              <span className="text-xs text-text-tertiary">
                결과를 위 칸에 채웁니다. 확인 후 저장하세요
              </span>
            </div>
          </div>
        )}

        {/* 분석 상한 — 비용이 기업 수만큼 곱해지므로(1건당 약 $0.0135) 여기서 정한다 */}
        <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
          <div>
            <span className="text-sm font-medium text-text-primary">분석 상한</span>
            <span className="ml-2 text-xs text-text-tertiary">
              「스캔 + 분석」이 한 번에 등록·분석할 기업 수
            </span>
          </div>
          {editMax === null ? (
            <div className="flex items-center gap-2">
              <span className="text-sm tabular-nums text-text-secondary">
                {tech.max_companies === 0 ? "전체" : `상위 ${tech.max_companies}개`}
              </span>
              <AdminButton onClick={() => setEditMax(tech.max_companies)}
                           className="btn btn-text text-xs">
                편집
              </AdminButton>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 text-xs text-text-secondary">
                <input type="checkbox" checked={editMax === 0}
                       onChange={(e) => setEditMax(e.target.checked ? 0 : 5)} />
                전체
              </label>
              <input
                type="number" min={1} value={editMax === 0 ? "" : editMax}
                disabled={editMax === 0}
                onChange={(e) => setEditMax(Number(e.target.value) || 1)}
                className="w-20 rounded-lg border border-border px-2 py-1 text-sm disabled:bg-background"
              />
              <button onClick={handleSaveMax} className="btn btn-primary btn-sm">저장</button>
              <button onClick={() => setEditMax(null)} className="btn btn-ghost btn-sm">취소</button>
            </div>
          )}
        </div>
      </div>

      {/* 스캔 결과 요약 */}
      {scanResult && (
        <div className="mb-6 rounded-xl border border-accent/30 bg-accent/5 px-5 py-4 text-sm">
          <div className="font-medium text-text-primary">
            스캔 완료 — 출원인 {scanResult.applicants}명, 신규 {scanResult.new}개
            {scanResult.dropped > 0 && `, 이번에 안 나온 기업 ${scanResult.dropped}개`}
          </div>
          <div className="mt-2 space-y-0.5 text-xs text-text-secondary">
            {scanResult.searched.map((s) => (
              <div key={s.word}>
                {s.word} — {s.total.toLocaleString()}건
                {s.broad && (
                  <span className="ml-1 text-warning">넓음(기술 특이성이 희석됩니다)</span>
                )}
              </div>
            ))}
          </div>
          {scanResult.onboarded && (
            <div className="mt-2 text-xs text-text-secondary">
              등록 {scanResult.onboarded.registered.length}개 · 분석 큐 투입{" "}
              {scanResult.onboarded.queued_reports}건 —{" "}
              <Link to="/settings/batches" className="text-accent underline">
                진행 상황
              </Link>
            </div>
          )}
        </div>
      )}

      {/* 종합 보고서 — 특허가 주근거다. 사업보고서는 아직 양산 전인 기술을 싣지 않으므로
          여기 없는 기업이 그 기술을 안 하는 것은 아니다 */}
      <div className="mb-6 rounded-xl border border-border bg-surface px-5 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">종합 보고서</h3>
            {tech.report_generated_at ? (
              <>
                {/* 무엇을 근거로 쓴 보고서인지 — 특허 기간·사업보고서 연도가
                    안 보이면 언제 기준인지 알 수 없다 */}
                {tech.report_basis && (
                  <p className="mt-0.5 text-xs font-medium text-text-secondary">
                    근거: {tech.report_basis}
                  </p>
                )}
                <p className="mt-0.5 text-xs text-text-tertiary">
                  생성: {new Date(tech.report_generated_at).toLocaleString("ko-KR")}
                </p>
              </>
            ) : (
              <p className="mt-0.5 text-xs text-text-tertiary">
                특허 초록과 추적 중 기업의 사업보고서 분석을 묶어 한 편으로 정리합니다.
              </p>
            )}
          </div>
          <AdminButton
            onClick={handleReport}
            disabled={reporting}
            className="btn btn-action btn-sm"
            title="특허를 다시 검색해 보고서를 만듭니다 (키워드 수만큼 KIPRIS 호출)"
          >
            {reporting ? "생성 중..." : tech.report_md ? "다시 생성" : "보고서 생성"}
          </AdminButton>
        </div>
        {reporting && (
          <p className="mt-3 text-xs text-text-secondary">
            특허 검색 후 한 번에 작성합니다. 보통 1분 내에 끝납니다.
          </p>
        )}
        {tech.report_md && !reporting && (
          <div className="mt-4 border-t border-border pt-4">
            <TechReport markdown={tech.report_md} />
          </div>
        )}
      </div>

      {(["tracked", "available", "excluded"] as const).map((s) => (
        <Section key={s} status={s} rows={tech.companies.filter((c) => c.status === s)} />
      ))}
    </div>
  );
}
