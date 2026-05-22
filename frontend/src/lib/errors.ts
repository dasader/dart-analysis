/** 알 수 없는 throw 값에서 사용자에게 보여줄 메시지를 추출한다. */
export function getErrorMessage(e: unknown, fallback = "오류가 발생했습니다."): string {
  return e instanceof Error ? e.message : fallback;
}
