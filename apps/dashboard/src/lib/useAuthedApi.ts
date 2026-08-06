import { useAuth0 } from '@auth0/auth0-react'
import * as api from '@/lib/api'
import type {
  BusinessUpdate,
  JobPostingConfigUpdate,
  JobPostingCreate,
  ScheduleInterviewRequest,
} from '@/lib/types'

/**
 * Binds every API call to a freshly-fetched Auth0 access token so callers
 * never have to thread the token through themselves. `getAccessTokenSilently`
 * handles caching/refresh internally, so this stays cheap to call per-request.
 */
export function useAuthedApi() {
  const { getAccessTokenSilently } = useAuth0()

  async function withToken<T>(fn: (token: string) => Promise<T>): Promise<T> {
    const token = await getAccessTokenSilently()
    return fn(token)
  }

  return {
    listCandidates: () => withToken(api.listCandidates),
    getCandidate: (id: string) => withToken((token) => api.getCandidate(token, id)),
    assignScreening: (id: string) => withToken((token) => api.assignScreening(token, id)),
    shortlistCandidate: (id: string) => withToken((token) => api.shortlistCandidate(token, id)),
    reviewWithAi: (id: string) => withToken((token) => api.reviewWithAi(token, id)),
    listUpcomingInterviews: () => withToken(api.listUpcomingInterviews),
    scheduleInterview: (id: string, payload: ScheduleInterviewRequest) =>
      withToken((token) => api.scheduleInterview(token, id, payload)),
    createJobPosting: (payload: JobPostingCreate) =>
      withToken((token) => api.createJobPosting(token, payload)),
    listJobPostings: () => withToken(api.listJobPostings),
    getJobPosting: (id: string) => withToken((token) => api.getJobPosting(token, id)),
    updateJobPostingConfig: (id: string, payload: JobPostingConfigUpdate) =>
      withToken((token) => api.updateJobPostingConfig(token, id, payload)),
    getMyBusiness: () => withToken(api.getMyBusiness),
    updateMyBusiness: (payload: BusinessUpdate) =>
      withToken((token) => api.updateMyBusiness(token, payload)),
    requestBusinessAccess: () => withToken(api.requestBusinessAccess),
    adminListBusinesses: (status?: string) =>
      withToken((token) => api.adminListBusinesses(token, status)),
    adminApproveBusiness: (id: number) =>
      withToken((token) => api.adminApproveBusiness(token, id)),
    getMcpServerStatus: () => withToken(api.getMcpServerStatus),
    listMcpTools: () => withToken(api.listMcpTools),
    callMcpTool: (toolName: string, args: Record<string, unknown>) =>
      withToken((token) => api.callMcpTool(token, toolName, args)),
  }
}
