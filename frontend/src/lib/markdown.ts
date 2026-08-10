/**
 * LLM 출력의 마크다운을 렌더 가능한 형태로 보정한다.
 *
 * 모델이 표 헤더 다음의 구분선(`|---|---|`)을 빠뜨리는 경우가 있다.
 * 7개 기업 실측에서 표 31개 중 5개(16%)가 그랬고, 한 응답 안에서는 뭉쳐서
 * 실패하는 경향이 있었다(현대자동차는 표 5개 전부 누락).
 * remark-gfm은 구분선이 없으면 표로 인식하지 않아 파이프 문자가 그대로 노출된다.
 *
 * 프롬프트에도 지시를 넣었지만, 모델 출력에 100%를 기대할 수는 없으므로
 * 렌더 직전에 한 번 더 보정한다.
 */
export function normalizeTables(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    out.push(lines[i]);

    const cur = lines[i].trim();
    if (!cur.startsWith("|")) continue;

    // 앞줄도 표라면 이 줄은 헤더가 아니다
    if ((lines[i - 1] ?? "").trim().startsWith("|")) continue;

    const next = (lines[i + 1] ?? "").trim();
    if (!next.startsWith("|")) continue;        // 뒤에 행이 없으면 표가 아니다
    if (isSeparator(next)) continue;            // 이미 구분선이 있다

    const cols = countCells(cur);
    if (cols > 0) out.push(`|${"---|".repeat(cols)}`);
  }

  return out.join("\n");
}

function isSeparator(line: string): boolean {
  return /^\|[\s:|-]+\|$/.test(line) && line.includes("-");
}

/** `| a | b |` → 2. 양 끝 파이프 사이의 셀 수 */
function countCells(row: string): number {
  return row.replace(/^\||\|$/g, "").split("|").length;
}
