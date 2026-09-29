const KST: Intl.DateTimeFormatOptions = { timeZone: "Asia/Seoul" };

/** 서버 시각 → Date. 백엔드는 UTC를 오프셋 없이 보낸다("2026-09-28T05:27:14") — 그대로 두면
 *  브라우저가 로컬 시각으로 읽어 한국에서 9시간 어긋나므로 UTC로 못박는다.
 *  날짜만 있는 값("2025-03-11")은 원래 UTC로 읽히고 Z를 붙이면 잘못된 날짜가 되므로 그대로 둔다. */
export function parseServerTime(s: string): Date {
  return new Date(s.includes("T") && !/(Z|[+-]\d\d:?\d\d)$/.test(s) ? `${s}Z` : s);
}

/** 서버 시각을 KST 날짜로. */
export const formatDate = (s: string, opts?: Intl.DateTimeFormatOptions) =>
  parseServerTime(s).toLocaleDateString("ko-KR", { ...KST, ...opts });

/** 서버 시각을 KST 날짜·시각으로. */
export const formatDateTime = (s: string, opts?: Intl.DateTimeFormatOptions) =>
  parseServerTime(s).toLocaleString("ko-KR", { ...KST, ...opts });
