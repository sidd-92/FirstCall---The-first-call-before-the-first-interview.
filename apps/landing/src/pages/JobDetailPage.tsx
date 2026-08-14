import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router'
import { applyToJob, getJob, type JobPosting } from '@/lib/api'
import { buildApplicationSubject, getApplicationEmailAddress } from '@/lib/mailto'
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
  const [subjectCopied, setSubjectCopied] = useState(false)
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
    await navigator.clipboard.writeText(getApplicationEmailAddress())
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleCopySubject() {
    if (!job || !id) return
    await navigator.clipboard.writeText(buildApplicationSubject(job.title, id))
    setSubjectCopied(true)
    setTimeout(() => setSubjectCopied(false), 2000)
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

  const payRange =
    job.pay_min != null && job.pay_max != null
      ? job.pay_currency === 'INR'
        ? `₹${job.pay_min / 100_000}–${job.pay_max / 100_000} LPA`
        : `${job.pay_currency} ${job.pay_min.toLocaleString()}–${job.pay_max.toLocaleString()}`
      : null

  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <Link to="/" className="text-sm text-accent hover:underline">
        &larr; Back to all jobs
      </Link>

      <p className="mt-4 text-sm font-medium text-accent">{job.business_name}</p>
      <h1 className="mb-2 text-3xl font-semibold tracking-tight">{job.title}</h1>
      <p className="mb-4 text-sm text-muted-foreground">
        {[job.location, job.employment_type, payRange].filter(Boolean).join(' · ')}
      </p>
      <p className="mb-6 whitespace-pre-wrap text-muted-foreground">{job.description}</p>

      {job.benefits.length > 0 && (
        <div className="mb-8">
          <h2 className="mb-2 font-heading text-lg font-medium">Benefits</h2>
          <ul className="list-disc pl-5 text-muted-foreground">
            {job.benefits.map((benefit) => (
              <li key={benefit}>{benefit}</li>
            ))}
          </ul>
        </div>
      )}

      {submitted ? (
        <Card>
          <CardHeader>
            <CardTitle>Application submitted</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-3 rounded-md border p-4">
              <p className="text-sm font-medium">Reach out directly by email (optional)</p>
              <div className="flex flex-wrap items-center gap-3">
                <code className="w-fit rounded bg-muted px-3 py-1.5 font-mono text-sm">
                  {getApplicationEmailAddress()}
                </code>
                <Button variant="outline" size="sm" onClick={handleCopyEmail} type="button">
                  {copied ? 'Copied!' : 'Copy address'}
                </Button>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <code className="w-fit rounded bg-muted px-3 py-1.5 font-mono text-sm">
                  {job && id ? buildApplicationSubject(job.title, id) : ''}
                </code>
                <Button variant="outline" size="sm" onClick={handleCopySubject} type="button">
                  {subjectCopied ? 'Copied!' : 'Copy subject'}
                </Button>
              </div>
              <ol className="flex list-decimal flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
                <li>
                  Click <span className="font-medium text-foreground">Copy address</span> above, then start a new
                  email in your own email app and paste it into the To field.
                </li>
                <li>
                  Click <span className="font-medium text-foreground">Copy subject</span> above, then paste it into
                  the Subject field -- this keeps your job reference (
                  <span className="font-mono">[JOB-{id}]</span>) attached to the thread so replies get matched to
                  your application automatically.
                </li>
                <li>Add your message and send.</li>
              </ol>
            </div>

            {discordLinkCode && (
              <div className="flex flex-col gap-3 rounded-md border p-4">
                <p className="text-sm font-medium">Get updates over Discord (optional)</p>
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

                <ol className="flex list-decimal flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
                  {discordInviteUrl && (
                    <li>
                      Click <span className="font-medium text-foreground">Join Discord Server</span> below and accept
                      the invite.
                    </li>
                  )}
                  <li>
                    In Discord, open{' '}
                    <span className="font-medium text-foreground">Direct Messages</span> and start (or open) a chat
                    with the{' '}
                    <span className="font-medium text-foreground">FirstCallApplication</span> bot -- not the server's
                    text channels.
                  </li>
                  <li>
                    Paste the code above into that DM and send it as a normal message (nothing else needs to be in
                    the message).
                  </li>
                  <li>
                    The bot replies right away to confirm it's linked. From then on, application updates arrive in
                    that same DM thread.
                  </li>
                </ol>

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
