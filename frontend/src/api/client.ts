import type {
  Company,
  CompanySearchResult,
  Report,
  Analysis,
  SchedulerStatus,
  PromptTemplate,
} from "../types";

const BASE = "/api";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

// --- Companies ---

export function fetchCompanies(): Promise<Company[]> {
  return request("/companies");
}

export function searchCompanies(name: string): Promise<CompanySearchResult[]> {
  return request(`/companies/search?name=${encodeURIComponent(name)}`);
}

export function createCompany(body: {
  corp_code: string;
  corp_name: string;
  stock_code?: string | null;
}): Promise<Company> {
  return request("/companies", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateCompany(
  id: number,
  body: { corp_name?: string; stock_code?: string; is_active?: boolean },
): Promise<Company> {
  return request(`/companies/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function deleteCompany(id: number): Promise<void> {
  return request(`/companies/${id}`, { method: "DELETE" });
}

// --- Reports ---

export function fetchReports(companyId: number): Promise<Report[]> {
  return request(`/companies/${companyId}/reports`);
}

export function downloadReports(
  companyId: number,
  body: { fiscal_year?: number; report_type?: string },
): Promise<Report[]> {
  return request(`/companies/${companyId}/reports/download`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function checkNewReports(
  companyId: number,
): Promise<{ new_count: number; reports: Record<string, string>[] }> {
  return request(`/companies/${companyId}/reports/check`);
}

export function fetchReportContent(
  reportId: number,
): Promise<{ report_id: number; content: string }> {
  return request(`/reports/${reportId}/content`);
}

// --- Analyses ---

export function runAnalysis(
  reportId: number,
  analysisType: string,
): Promise<Analysis> {
  return request(`/reports/${reportId}/analyze`, {
    method: "POST",
    body: JSON.stringify({ analysis_type: analysisType }),
  });
}

export function fetchReportAnalyses(reportId: number): Promise<Analysis[]> {
  return request(`/reports/${reportId}/analyses`);
}

export function fetchAnalysis(analysisId: number): Promise<Analysis> {
  return request(`/analyses/${analysisId}`);
}

export function fetchCompanyAnalyses(companyId: number): Promise<Analysis[]> {
  return request(`/companies/${companyId}/analyses`);
}

export function analyzeAll(
  companyId: number,
): Promise<{ message: string; queued: number }> {
  return request(`/companies/${companyId}/analyze-all`, { method: "POST" });
}

export function fetchQueueStatus(): Promise<{
  pending_count: number;
  running: { analysis_id: number } | null;
}> {
  return request("/queue/status");
}

// --- Scheduler ---

export function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  return request("/scheduler/status");
}

export function runSchedulerNow(): Promise<{ message: string }> {
  return request("/scheduler/run-now", { method: "POST" });
}

// --- Prompts ---

export function fetchPrompts(): Promise<PromptTemplate[]> {
  return request("/prompts");
}

export function fetchPrompt(analysisType: string): Promise<PromptTemplate> {
  return request(`/prompts/${analysisType}`);
}

export function updatePrompt(
  analysisType: string,
  body: { system_prompt: string; user_prompt_template: string },
): Promise<PromptTemplate> {
  return request(`/prompts/${analysisType}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
