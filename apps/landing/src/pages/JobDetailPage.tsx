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
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [copied, setCopied] = useState(false)

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
      await applyToJob(id, {
        name: String(formData.get('name') ?? ''),
        email: String(formData.get('email') ?? ''),
        phone: String(formData.get('phone') ?? ''),
        address: String(formData.get('address') ?? ''),
        resume,
      })
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
          <CardContent className="flex flex-col gap-3">
            <p className="text-muted-foreground">
              Thanks for applying. You can also reach out directly by email.
            </p>
            <Button variant="outline" onClick={handleCopyEmail} type="button">
              {copied ? 'Copied!' : 'Copy application email'}
            </Button>
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
