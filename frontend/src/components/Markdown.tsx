import { memo } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { normalizeTables } from "../lib/markdown";

const PROSE_CLASSES = `
  prose prose-sm max-w-none
  prose-headings:font-semibold prose-headings:text-navy prose-headings:mt-6 prose-headings:mb-3
  prose-h2:text-base prose-h3:text-sm
  prose-p:text-text-primary prose-p:leading-relaxed prose-p:my-3
  prose-li:text-text-primary prose-li:leading-relaxed
  prose-strong:text-text-primary
  prose-table:w-full prose-table:text-sm prose-table:border-collapse
  prose-thead:bg-background
  prose-th:border prose-th:border-border prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:font-semibold prose-th:text-text-secondary
  prose-td:border prose-td:border-border prose-td:px-3 prose-td:py-2 prose-td:text-text-primary
  prose-tr:even:bg-background/40
  prose-hr:border-border prose-hr:my-6
  prose-blockquote:border-l-accent prose-blockquote:text-text-secondary
  prose-code:text-accent prose-code:bg-background prose-code:px-1 prose-code:rounded
`.trim();

/** 모델이 뱉은 마크다운을 렌더한다. 표 구분선 누락은 normalizeTables가 보정한다
 *  — 프롬프트를 고쳐도 100%를 기대할 수는 없다.
 *  memo: 본문은 문자열이라 얕은 비교로 충분하다 — 부모가 다시 그려질 때(입력·폴링·탭) 재파싱하지 않는다. */
export default memo(function Markdown({ children }: { children: string }) {
  return (
    <article className={PROSE_CLASSES}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 보고서 본문의 내부 링크(/companies/...)는 SPA 라우팅을 타야 한다.
          // <a>로 두면 전체 새로고침이 걸린다
          a: ({ href, children: text }) =>
            href?.startsWith("/") ? (
              <Link to={href} className="text-accent hover:underline">{text}</Link>
            ) : (
              <a href={href} target="_blank" rel="noreferrer">{text}</a>
            ),
        }}
      >
        {normalizeTables(children)}
      </ReactMarkdown>
    </article>
  );
});
