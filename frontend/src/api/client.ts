import type {
  Company,
  CompanyCreate,
  CompanyUpdate,
  CompanySearchResult,
  Report,
  Analysis,
  SchedulerStatus,
  BatchJob,
  QueueStatus,
  ExtractionFailure,
  AppSetting,
  Technology,
  TechnologyDetail,
  ScanResult,
  PromptTemplate,
  PromptUpdate,
  Tag,
  TagCreate,
  TagUpdate,
} from "../types";
import { getAdminKey } from "../lib/adminKey";

const BASE = "/api";

/** 관리자 키 헤더를 붙이고 오류 응답을 예외로 바꾼다. Content-Type은 정하지 않는다 —
 *  업로드는 브라우저가 boundary를 담아 직접 정해야 하고(명시하면 multipart 파싱이 깨진다),
 *  다운로드는 JSON이 아니라 파일을 받는다. */
async function adminFetch(url: string, init?: RequestInit): Promise<Response> {
  const adminKey = getAdminKey();
  const resp = await fetch(`${BASE}${url}`, {
    ...init,
    headers: {
      ...(adminKey ? { "X-Admin-Key": adminKey } : {}),
      ...((init?.headers as Record<string, string> | undefined) ?? {}),
    },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  return resp;
}

/** JSON API 호출. */
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await adminFetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...((init?.headers as Record<string, string> | undefined) ?? {}),
    },
  });
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

// --- Companies ---

export function fetchCompanies(): Promise<Company[]> {
  return request("/companies");
}

export function fetchCompany(id: number): Promise<Company> {
  return request(`/companies/${id}`);
}

export function searchCompanies(name: string): Promise<CompanySearchResult[]> {
  return request(`/companies/search?name=${encodeURIComponent(name)}`);
}

export function createCompany(body: CompanyCreate): Promise<Company> {
  return request("/companies", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateCompany(
  id: number,
  body: CompanyUpdate,
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

export function fetchReportAnalyses(reportId: number): Promise<Analysis[]> {
  return request(`/reports/${reportId}/analyses`);
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

// --- Batches ---

export function fetchBatches(): Promise<BatchJob[]> {
  return request("/batches");
}

export function cancelBatch(batchId: number): Promise<{ message: string }> {
  return request(`/batches/${batchId}/cancel`, { method: "POST" });
}

export function fetchExtractionFailures(): Promise<ExtractionFailure[]> {
  return request("/batches/extraction-failures");
}

export function fetchQueueStatus(): Promise<QueueStatus> {
  return request("/queue/status");
}

// --- Scheduler ---

export function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  return request("/scheduler/status");
}

// --- Technologies ---

export function fetchTechnologies(): Promise<Technology[]> {
  return request("/technologies");
}

export function fetchTechnology(id: number): Promise<TechnologyDetail> {
  return request(`/technologies/${id}`);
}

export function createTechnology(body: {
  name: string; description: string; keywords?: string[]; max_companies?: number;
}): Promise<Technology> {
  return request("/technologies", { method: "POST", body: JSON.stringify(body) });
}

export function updateTechnology(
  id: number,
  body: Partial<{ name: string; description: string; keywords: string[]; max_companies: number; is_active: boolean }>,
): Promise<Technology> {
  return request(`/technologies/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteTechnology(id: number): Promise<void> {
  return request(`/technologies/${id}`, { method: "DELETE" });
}

export function scanTechnology(id: number, onboard = false): Promise<ScanResult> {
  return request(`/technologies/${id}/scan?onboard=${onboard}`, { method: "POST" });
}

/** 설명문으로 검색어를 다시 뽑는다. 저장하지 않고 제안만 한다 — 화면이 확인 후 저장한다. */
export function suggestKeywords(id: number): Promise<{ keywords: string[] }> {
  return request(`/technologies/${id}/keywords/suggest`);
}

export function generateTechReport(
  id: number,
): Promise<{ report_md: string; report_generated_at: string; report_basis: string }> {
  return request(`/technologies/${id}/report`, { method: "POST" });
}

// --- App Settings ---

export function fetchAppSettings(): Promise<AppSetting[]> {
  return request("/settings");
}

export function updateAppSetting(key: string, value: boolean): Promise<AppSetting> {
  return request(`/settings/${key}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

// --- Prompts ---

export function fetchPrompts(): Promise<PromptTemplate[]> {
  return request("/prompts");
}

export function updatePrompt(
  analysisType: string,
  body: PromptUpdate,
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

export function createTag(body: TagCreate): Promise<Tag> {
  return request("/tags", { method: "POST", body: JSON.stringify(body) });
}

export function updateTag(
  id: number,
  body: TagUpdate,
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

// --- Admin ---

export async function verifyAdminKey(key: string): Promise<boolean> {
  const resp = await fetch(`${BASE}/admin/verify`, {
    headers: { "X-Admin-Key": key },
  });
  return resp.ok;
}

// --- 백업·복원 (request 대신 adminFetch — 멀티파트 업로드·파일 다운로드) ---

/** 파일을 받아 브라우저 다운로드로 넘긴다. 헤더가 필요해 단순 링크로는 안 된다. */
export async function downloadBackup(kind: "corps" | "db"): Promise<void> {
  const resp = await adminFetch(`/backup/${kind}`);
  const blob = await resp.blob();
  const name = resp.headers
    .get("content-disposition")
    ?.match(/filename="?([^"]+)"?/)?.[1];

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name || `dart-${kind}.sqlite3.gz`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function uploadBackup(
  kind: "corps" | "db" | "applicant-corps",
  file: File,
): Promise<Record<string, unknown>> {
  const form = new FormData();
  form.append("file", file);
  const resp = await adminFetch(`/backup/${kind}`, { method: "POST", body: form });
  return resp.json();
}

export function fetchBackupStatus(): Promise<Record<string, number>> {
  return request("/backup/status");
}
