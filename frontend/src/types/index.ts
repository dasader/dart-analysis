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

/** 진행 상태만 — 기업 상세 폴링 응답(`/companies/{id}/analyses`). 본문은 싣지 않는다. */
export type AnalysisState = Pick<Analysis, "id" | "report_id" | "analysis_type" | "status" | "updated_at">;

export interface SchedulerStatus {
  is_running: boolean;
  next_run_time: string | null;
  interval_hours: number;
}

export interface BatchJob {
  id: number;
  job_name: string;
  model_name: string;
  thinking_level: string;
  state: string;
  report_ids: number[];
  request_count: number;
  success_count: number;
  failed_count: number;
  error_message: string | null;
  submitted_at: string | null;
  completed_at: string | null;
  is_terminal: boolean;
}

/** 구역 추출 실패 — 보고서 서식 변경 신호. LLM에는 보내지 않은 상태다. */
export interface ExtractionFailure {
  report_id: number;
  company_id: number;
  corp_name: string;
  report_name: string;
  fiscal_year: number;
  reason: string;
  failed_at: string | null;
}

export interface QueueStatus {
  pending_count: number;
  running_batches: number;
  running_reports: number;
}

/** 백엔드 `constants.TechStatus`와 같은 값·순서(화면 섹션 순서). */
export const TECH_STATUSES = ["tracked", "available", "excluded"] as const;
export type TechStatus = (typeof TECH_STATUSES)[number];

export interface TechCompany {
  id: number;
  company_id: number | null;
  corp_code: string | null;
  corp_name: string | null;
  applicant_name: string;
  patent_count: number;
  keyword_hits: string[];
  status: TechStatus;
  exclude_reason: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  is_new: boolean;
  is_gone: boolean;
}

export interface KeywordStat {
  word: string;
  total: number;
  broad: boolean;
}

export interface Technology {
  id: number;
  name: string;
  description: string;
  keywords: string[];
  keyword_stats: KeywordStat[];
  ipc_core: string[];
  max_companies: number;
  is_active: boolean;
  last_scanned_at: string | null;
  created_at: string;
  tracked_count: number;
  available_count: number;
  excluded_count: number;
}

export interface TechnologyDetail extends Technology {
  companies: TechCompany[];
  report_md: string | null;
  report_generated_at: string | null;
  report_basis: string | null;
}

export interface ScanResult {
  technology_id: number;
  keywords: string[];
  searched: KeywordStat[];
  applicants: number;
  tracked: number;
  available: number;
  excluded: number;
  new: number;
  kept: number;
  dropped: number;
  onboarded: {
    // role·reason은 후보가 상한보다 많아 적합도 판정을 거쳤을 때만 온다
    registered: { corp_name: string; role: string | null; reason: string | null }[];
    queued_reports: number;
  } | null;
}

/** 런타임에 바꿀 수 있는 설정 (DB 저장, 재시작 불필요) */
export interface AppSetting {
  key: string;
  label: string;
  description: string;
  value: boolean;
}

export interface PromptTemplate {
  id: number;
  analysis_type: string;
  label: string;
  system_prompt: string;
  user_prompt_template: string;
  updated_at: string;
}

// --- API 요청 body 타입 (백엔드 schemas.py 대응) ---

export interface CompanyCreate {
  corp_code: string;
  corp_name: string;
  stock_code?: string | null;
}

export interface CompanyUpdate {
  corp_name?: string;
  stock_code?: string;
  is_active?: boolean;
}

export interface TagCreate {
  name: string;
  color: string;
}

export interface TagUpdate {
  name?: string;
  color?: string;
}

export interface PromptUpdate {
  system_prompt: string;
  user_prompt_template: string;
}
