const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string

export interface JobPosting {
  id: number
  title: string
  description: string
  faq_json: string
}

export interface ApplicationPayload {
  name: string
  email: string
  phone: string
  address: string
  resume: File
}

export interface ApplicationResult {
  id: number
  discord_link_code: string
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json()
    return data.detail ?? `Request failed with status ${response.status}`
  } catch {
    return `Request failed with status ${response.status}`
  }
}

export async function listJobs(): Promise<JobPosting[]> {
  const response = await fetch(`${API_BASE_URL}/jobs`)
  if (!response.ok) throw new Error(await parseErrorMessage(response))
  return response.json()
}

export async function getJob(id: string): Promise<JobPosting> {
  const response = await fetch(`${API_BASE_URL}/jobs/${id}`)
  if (!response.ok) throw new Error(await parseErrorMessage(response))
  return response.json()
}

export async function applyToJob(
  id: string,
  payload: ApplicationPayload,
): Promise<ApplicationResult> {
  const form = new FormData()
  form.set('name', payload.name)
  form.set('email', payload.email)
  form.set('phone', payload.phone)
  form.set('address', payload.address)
  form.set('resume', payload.resume)

  const response = await fetch(`${API_BASE_URL}/jobs/${id}/apply`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) throw new Error(await parseErrorMessage(response))
  return response.json()
}
