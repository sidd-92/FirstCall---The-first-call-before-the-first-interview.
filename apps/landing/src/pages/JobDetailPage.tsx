import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router'
import { applyToJob, getJob, type JobPosting } from '@/lib/api'
import { buildApplicationMailto } from '@/lib/mailto'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [job, setJob] = useState<JobPosting | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [discordLinkCode, setDiscordLinkCode] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [copied, setCopied] = useState(false)
  const [discordCodeCopied, setDiscordCodeCopied] = useState(false)
  const discordInviteUrl = import.meta.env.VITE_DISCORD_INVITE_URL as string | undefined

  useEffect(() => {
    if (!id) return
    getJob(id)
      .then(setJob)
      .catch((err: Error) => setError(err.message))
  }, [id])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!id) return

    const form = event.currentTarget
    const formData = new FormData(form)
    const resume = formData.get('resume')
    if (!(resume instanceof File) || resume.size === 0) {
      setSubmitError('Please attach a resume file.')
      return
    }

    setSubmitting(true)
    setSubmitError(null)
    try {
      const result = await applyToJob(id, {
        name: String(formData.get('name') ?? ''),
        email: String(formData.get('email') ?? ''),
        phone: String(formData.get('phone') ?? ''),
        address: String(formData.get('address') ?? ''),
        resume,
      })
      setDiscordLinkCode(result.discord_link_code)
      setSubmitted(true)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to submit application.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCopyEmail() {
    if (!job || !id) return
    await navigator.clipboard.writeText(buildApplicationMailto(job.title, id))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleCopyDiscordCode() {
    if (!discordLinkCode) return
    await navigator.clipboard.writeText(discordLinkCode)
    setDiscordCodeCopied(true)
    setTimeout(() => setDiscordCodeCopied(false), 2000)
  }

  async function handleJoinDiscord() {
    if (!discordLinkCode) return
    // Copy first so the code is on the clipboard the instant the new tab
    // opens -- the candidate can paste it into the bot DM right away.
    await navigator.clipboard.writeText(discordLinkCode)
    setDiscordCodeCopied(true)
    setTimeout(() => setDiscordCodeCopied(false), 2000)
    if (discordInviteUrl) {
      window.open(discordInviteUrl, '_blank', 'noreferrer')
    }
  }

  if (error) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-12">
        <p className="text-destructive">Failed to load job: {error}</p>
        <Link to="/" className="text-primary underline-offset-4 hover:underline">
          Back to all jobs
        </Link>
      </main>
    )
  }

  if (!job) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-12">
        <p className="text-muted-foreground">Loading job...</p>
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
        &larr; Back to all jobs
      </Link>

      <h1 className="mt-4 mb-2 text-3xl font-semibold tracking-tight">{job.title}</h1>
      <p className="mb-8 whitespace-pre-wrap text-muted-foreground">{job.description}</p>

      {submitted ? (
        <Card>
          <CardHeader>
            <CardTitle>Application submitted</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p className="text-muted-foreground">
              Thanks for applying. You can also reach out directly by email.
            </p>
            <Button variant="outline" onClick={handleCopyEmail} type="button" className="w-fit">
              {copied ? 'Copied!' : 'Copy application email'}
            </Button>

            {discordLinkCode && (
              <div className="flex flex-col gap-3 rounded-md border p-4">
                <p className="text-sm font-medium">Get updates over Discord (optional)</p>
                <p className="text-sm text-muted-foreground">
                  {discordInviteUrl
                    ? 'Join our Discord server and DM the bot the code below to connect your application.'
                    : 'DM our Discord bot the code below to connect your application.'}
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <code className="w-fit rounded bg-muted px-3 py-1.5 font-mono text-lg tracking-widest">
                    {discordLinkCode}
                  </code>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopyDiscordCode}
                    type="button"
                  >
                    {discordCodeCopied ? 'Copied!' : 'Copy code'}
                  </Button>
                </div>
                {discordInviteUrl && (
                  <Button onClick={handleJoinDiscord} type="button" className="w-fit">
                    {discordCodeCopied ? 'Code copied -- opening Discord...' : 'Join Discord Server'}
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Apply for this position</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="name">Full name</Label>
                <Input id="name" name="name" required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email">Email</Label>
                <Input id="email" name="email" type="email" required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="phone">Phone</Label>
                <Input id="phone" name="phone" type="tel" required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="address">Address</Label>
                <Textarea id="address" name="address" required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="resume">Resume</Label>
                <Input id="resume" name="resume" type="file" required />
              </div>

              {submitError && <p className="text-destructive text-sm">{submitError}</p>}

              <Button type="submit" disabled={submitting}>
                {submitting ? 'Submitting...' : 'Submit application'}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </main>
  )
}
