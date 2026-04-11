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

export interface Analysis {
  id: number;
  company_id: number;
  report_id: number;
  analysis_type: "subsidiary" | "rnd" | "national_tech";
  status: "pending" | "running" | "completed" | "failed";
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
