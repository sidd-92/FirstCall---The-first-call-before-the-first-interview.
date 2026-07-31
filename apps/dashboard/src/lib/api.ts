import type { CandidateDetail, CandidateSummary, UpcomingInterview } from '@/lib/types'

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
