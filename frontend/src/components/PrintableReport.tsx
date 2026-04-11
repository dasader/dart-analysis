import ReactMarkdown from "react-markdown";
import type { Analysis } from "../types";

interface Props {
  companyName: string;
  fiscalYear: number;
  analysis: Analysis;
}

const TYPE_LABELS: Record<string, string> = {
  subsidiary: "연결대상 종속회사 변동 분석",
  rnd: "연구개발 및 투자 분석",
  national_tech: "국가전략기술 관련 분석",
};

export default function PrintableReport({
  companyName,
  fiscalYear,
  analysis,
}: Props) {
  return (
    <div className="print-only">
      <div className="mb-8 border-b-2 border-black pb-4">
        <h1 className="text-xl font-bold">{companyName}</h1>
        <h2 className="mt-1 text-base text-gray-700">
          {fiscalYear}년 {TYPE_LABELS[analysis.analysis_type]}
        </h2>
        <p className="mt-2 text-xs text-gray-500">
          분석일: {new Date(analysis.updated_at).toLocaleDateString("ko-KR")} |
          모델: {analysis.model_name}
        </p>
      </div>
      <article className="prose prose-sm max-w-none">
        <ReactMarkdown>{analysis.result_summary || ""}</ReactMarkdown>
      </article>
      <footer className="mt-12 border-t border-gray-300 pt-4 text-xs text-gray-400">
        DART 사업보고서 AI 분석 보고서 — 자동 생성됨
      </footer>
    </div>
  );
}
