import { useState } from "react";
import Markdown from "./Markdown";

/** 「참고 — 산업 밖 주체」 절의 시작. 백엔드 프롬프트가 이 제목을 쓰도록 지시한다.
 *  대학·연구소 목록은 참고자료라 기본으로 접어 둔다. 모델이 제목을 조금 다르게
 *  써도 잡히도록 느슨하게 맞춘다. */
const APPENDIX = /^##\s*참고\s*[—\-–]?\s*산업\s*밖\s*주체.*$/m;

export function splitAppendix(md: string): { body: string; appendix: string | null } {
  const m = md.match(APPENDIX);
  if (m?.index === undefined) return { body: md, appendix: null };
  return {
    body: md.slice(0, m.index).trimEnd(),
    appendix: md.slice(m.index + m[0].length).trim() || null,
  };
}

export default function TechReport({ markdown }: { markdown: string }) {
  const [open, setOpen] = useState(false);
  const { body, appendix } = splitAppendix(markdown);

  return (
    <>
      <Markdown>{body}</Markdown>
      {appendix && (
        <div className="mt-6 border-t border-border pt-4">
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1.5 text-xs font-medium text-text-secondary hover:text-accent"
          >
            <span className={`transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
            참고 — 산업 밖 주체 (대학·연구소·외국기업)
          </button>
          {open && (
            <div className="mt-3">
              <Markdown>{appendix}</Markdown>
            </div>
          )}
        </div>
      )}
    </>
  );
}
