export interface Tag {
  id: number;
  name: string;
  color: string;
  created_at: string;
}

export const TAG_COLORS = [
  "#3B82F6", "#22C55E", "#EF4444", "#F97316",
  "#A855F7", "#EC4899", "#06B6D4", "#EAB308",
  "#6366F1", "#14B8A6", "#78716C", "#6B7280",
] as const;

export interface Company {
  id: number;
  corp_code: string;
  corp_name: string;
  stock_code: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  report_count: number;
  latest_analysis_date: string | null;
  tags: Tag[];
}

export interface CompanySearchResult {
  corp_code: string;
  corp_name: string;
  stock_code: string | null;
}

export interface Report {
  id: number;
  company_id: number;
  rcept_no: string;
  report_name: string;
  report_type: string;
  fiscal_year: number;
  filing_date: string | null;
  file_path: string | null;
  downloaded_at: string | null;
  created_at: string;
  analysis_count: number;
}

export const ANALYSIS_TYPE_KEYS = ["subsidiary", "rnd", "national_tech"] as const;
export type AnalysisType = (typeof ANALYSIS_TYPE_KEYS)[number];
export type AnalysisStatus = "pending" | "running" | "completed" | "failed";

// 화면 탭/헤더용 라벨
export const ANALYSIS_TYPE_LABELS: Record<AnalysisType, string> = {
  subsidiary: "종속회사 변동 분석",
  rnd: "R&D/투자 분석",
  national_tech: "국가전략기술 분석",
};

// 인쇄용 전체 명칭
export const PRINT_TYPE_LABELS: Record<AnalysisType, string> = {
  subsidiary: "연결대상 종속회사 변동 분석",
  rnd: "연구개발 및 투자 분석",
  national_tech: "국가전략기술 관련 분석",
};

export interface Analysis {
  id: number;
  company_id: number;
  report_id: number;
  analysis_type: AnalysisType;
  status: AnalysisStatus;
  result_json: string | null;
  result_summary: string | null;
  error_message: string | null;
  model_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface SchedulerStatus {
  is_running: boolean;
  next_run_time: string | null;
  interval_hours: number;
}

export interface PromptTemplate {
  id: number;
  analysis_type: string;
  label: string;
  system_prompt: string;
  user_prompt_template: string;
  updated_at: string;
}
