import { useAuth0 } from '@auth0/auth0-react'
import * as api from '@/lib/api'
import type { BusinessOnboard, JobPostingCreate } from '@/lib/types'

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
    createJobPosting: (payload: JobPostingCreate) =>
      withToken((token) => api.createJobPosting(token, payload)),
    listBusinesses: () => withToken(api.listBusinesses),
    onboardBusiness: (payload: BusinessOnboard) =>
      withToken((token) => api.onboardBusiness(token, payload)),
  }
}
