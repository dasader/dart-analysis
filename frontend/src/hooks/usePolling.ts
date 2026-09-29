import { useEffect, useEffectEvent } from "react";

/** active인 동안 ms마다 fn을 부른다. 숨은 탭은 건너뛰고, 실패는 다음 주기에 다시 한다. */
export function usePolling(fn: () => Promise<unknown>, ms: number, active = true) {
  const tick = useEffectEvent(() => {
    if (!document.hidden) fn().catch(() => {});
  });
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => tick(), ms); // effect event는 값으로 넘기지 않는다(hooks 규칙)
    return () => clearInterval(t);
  }, [active, ms]);
}
