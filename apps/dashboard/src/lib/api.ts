import type {
  AdminBusiness,
  Business,
  BusinessUpdate,
  CandidateDetail,
  CandidateSummary,
  JobPostingConfigUpdate,
  JobPostingCreate,
  JobPostingDetail,
  JobPostingSummary,
  McpStatus,
  McpTool,
  McpToolCallResult,
  RequestAccessResult,
  ScheduleInterviewRequest,
  UpcomingInterview,
} from '@/lib/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json()
    return data.detail ?? `Request failed with status ${response.status}`
  } catch {
    return `Request failed with status ${response.status}`
  }
}

async function request<T>(token: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...init?.headers,
      Authorization: `Bearer ${token}`,
    },
  })
  if (!response.ok) throw new Error(await parseErrorMessage(response))
  return response.json()
}

export function listCandidates(token: string): Promise<CandidateSummary[]> {
  return request(token, '/candidates')
}

export function getCandidate(token: string, id: string): Promise<CandidateDetail> {
  return request(token, `/candidates/${id}`)
}

export function assignScreening(token: string, id: string): Promise<void> {
  return request(token, `/candidates/${id}/assign-screening`, { method: 'POST' })
}

export function shortlistCandidate(token: string, id: string): Promise<void> {
  return request(token, `/candidates/${id}/shortlist`, { method: 'POST' })
}

export function reviewWithAi(token: string, id: string): Promise<void> {
  return request(token, `/candidates/${id}/review-with-ai`, { method: 'POST' })
}

export function listUpcomingInterviews(token: string): Promise<UpcomingInterview[]> {
  return request(token, '/interviews')
}

export function scheduleInterview(
  token: string,
  id: string,
  payload: ScheduleInterviewRequest,
): Promise<{ stage: string; scheduled_at: string; interview_notes: string | null }> {
  return request(token, `/candidates/${id}/schedule-interview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function createJobPosting(
  token: string,
  payload: JobPostingCreate,
): Promise<{ id: number }> {
  return request(token, '/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listJobPostings(token: string): Promise<JobPostingSummary[]> {
  return request(token, '/job-postings')
}

export function getJobPosting(token: string, id: string): Promise<JobPostingDetail> {
  return request(token, `/job-postings/${id}`)
}

export function updateJobPostingConfig(
  token: string,
  id: string,
  payload: JobPostingConfigUpdate,
): Promise<JobPostingConfigUpdate> {
  return request(token, `/job-postings/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getMyBusiness(token: string): Promise<Business> {
  return request(token, '/business/me')
}

export function updateMyBusiness(token: string, payload: BusinessUpdate): Promise<Business> {
  return request(token, '/business/me', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function requestBusinessAccess(token: string): Promise<RequestAccessResult> {
  return request(token, '/business/request-access', { method: 'POST' })
}

export function adminListBusinesses(
  token: string,
  status?: string,
): Promise<AdminBusiness[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return request(token, `/admin/businesses${query}`)
}

export function adminApproveBusiness(token: string, id: number): Promise<AdminBusiness> {
  return request(token, `/admin/businesses/${id}/approve`, { method: 'POST' })
}

export function getMcpServerStatus(token: string): Promise<McpStatus> {
  return request(token, '/mcp-server/status')
}

export function listMcpTools(token: string): Promise<McpTool[]> {
  return request(token, '/mcp-server/tools')
}

export function callMcpTool(
  token: string,
  toolName: string,
  args: Record<string, unknown>,
): Promise<McpToolCallResult> {
  return request(token, `/mcp-server/tools/${encodeURIComponent(toolName)}/call`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arguments: args }),
  })
}
