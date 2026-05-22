import type {
  Company,
  CompanySearchResult,
  Report,
  Analysis,
  SchedulerStatus,
  PromptTemplate,
  Tag,
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

export function fetchCompanies(tagIds?: number[]): Promise<Company[]> {
  const qs = tagIds && tagIds.length > 0 ? `?tag_ids=${tagIds.join(",")}` : "";
  return request(`/companies${qs}`);
}

export function fetchCompany(id: number): Promise<Company> {
  return request(`/companies/${id}`);
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

export function deleteReport(reportId: number): Promise<void> {
  return request(`/reports/${reportId}`, { method: "DELETE" });
}

export function redownloadReport(reportId: number): Promise<Report> {
  return request(`/reports/${reportId}/redownload`, { method: "POST" });
}

// --- Analyses ---

export function fetchCompanyAnalyses(companyId: number): Promise<Analysis[]> {
  return request(`/companies/${companyId}/analyses`);
}

export function analyzeReport(
  reportId: number,
): Promise<{ message: string; queued: number }> {
  return request(`/reports/${reportId}/analyze-all`, { method: "POST" });
}

export function analyzeAll(
  companyId: number,
): Promise<{ message: string; queued: number }> {
  return request(`/companies/${companyId}/analyze-all`, { method: "POST" });
}

// --- Scheduler ---

export function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  return request("/scheduler/status");
}

// --- Prompts ---

export function fetchPrompts(): Promise<PromptTemplate[]> {
  return request("/prompts");
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

// --- Tags ---

export function fetchTags(): Promise<Tag[]> {
  return request("/tags");
}

export function createTag(body: { name: string; color: string }): Promise<Tag> {
  return request("/tags", { method: "POST", body: JSON.stringify(body) });
}

export function updateTag(
  id: number,
  body: { name?: string; color?: string },
): Promise<Tag> {
  return request(`/tags/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteTag(id: number): Promise<void> {
  return request(`/tags/${id}`, { method: "DELETE" });
}

export function assignTag(companyId: number, tagId: number): Promise<Company> {
  return request(`/companies/${companyId}/tags/${tagId}`, { method: "POST" });
}

export function removeCompanyTag(companyId: number, tagId: number): Promise<Company> {
  return request(`/companies/${companyId}/tags/${tagId}`, { method: "DELETE" });
}
