import type { AnalysisState } from "../types";

/** 대기·처리 중이면 폴링이 필요하다. */
export const isInProgress = (a: Pick<AnalysisState, "status">) =>
  a.status === "pending" || a.status === "running";

/** 폴링 결과가 그대로면 이전 배열을 유지해 다시 그리지 않게 한다. */
export function analysesEqual(a: AnalysisState[], b: AnalysisState[]): boolean {
  return (
    a.length === b.length &&
    a.every((x, i) => x.id === b[i].id && x.status === b[i].status && x.updated_at === b[i].updated_at)
  );
}
