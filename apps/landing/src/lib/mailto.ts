export function getApplicationEmailAddress(): string {
  return import.meta.env.VITE_AGENT_EMAIL_ADDRESS as string
}

export function buildApplicationSubject(jobTitle: string, jobId: string): string {
  return `Application: ${jobTitle} [JOB-${jobId}]`
}
