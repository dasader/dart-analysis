import { useState } from "react";

export type SortDir = "asc" | "desc";

/** 컬럼 클릭 정렬 상태(키·방향)와 토글·비교 헬퍼를 제공한다. */
export function useSort<K extends string>(defaultKey: K, defaultDir: SortDir) {
  const [sortKey, setSortKey] = useState<K>(defaultKey);
  const [sortDir, setSortDir] = useState<SortDir>(defaultDir);

  const toggleSort = (key: K) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir(defaultDir);
    }
  };

  const compare = (av: string | number, bv: string | number) => {
    if (av < bv) return sortDir === "asc" ? -1 : 1;
    if (av > bv) return sortDir === "asc" ? 1 : -1;
    return 0;
  };

  return { sortKey, sortDir, toggleSort, compare };
}
