import type { SortDir } from "../hooks/useSort";

/** 정렬 가능한 컬럼 헤더에 붙이는 방향 아이콘. */
export default function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 opacity-30">↕</span>;
  return <span className="ml-1">{dir === "asc" ? "↑" : "↓"}</span>;
}
