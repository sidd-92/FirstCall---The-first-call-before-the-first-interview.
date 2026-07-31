export function buildApplicationMailto(jobTitle: string, jobId: string): string {
  const agentEmail = import.meta.env.VITE_AGENT_EMAIL_ADDRESS as string
  const subject = `Application: ${jobTitle} [JOB-${jobId}]`
  return `mailto:${agentEmail}?subject=${encodeURIComponent(subject)}`
}
