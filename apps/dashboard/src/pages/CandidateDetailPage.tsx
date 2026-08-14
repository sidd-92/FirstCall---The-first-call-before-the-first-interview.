import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { CandidateDetail } from '@/lib/types'
import { StageBadge } from '@/components/StageBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string

export function CandidateDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { getCandidate, assignScreening, shortlistCandidate, reviewWithAi, scheduleInterview } =
    useAuthedApi()
  const [candidate, setCandidate] = useState<CandidateDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const [schedulingError, setSchedulingError] = useState<string | null>(null)
  const [scheduling, setScheduling] = useState(false)

  function load() {
    if (!id) return
    getCandidate(id)
      .then(setCandidate)
      .catch((err: Error) => setError(err.message))
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [id])

  async function runAction(name: string, action: () => Promise<void>) {
    if (!id) return
    setPendingAction(name)
    setActionError(null)
    try {
      await action()
      load()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : `Failed to ${name}.`)
    } finally {
      setPendingAction(null)
    }
  }

  async function handleScheduleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!id) return
    const formData = new FormData(event.currentTarget)
    const scheduledAtLocal = String(formData.get('scheduled_at') ?? '')
    if (!scheduledAtLocal) return
    const notes = String(formData.get('interview_notes') ?? '').trim()

    setScheduling(true)
    setSchedulingError(null)
    try {
      await scheduleInterview(id, {
        scheduled_at: new Date(scheduledAtLocal).toISOString(),
        interview_notes: notes || null,
      })
      load()
    } catch (err) {
      setSchedulingError(
        err instanceof Error ? err.message : 'Failed to schedule interview.',
      )
    } finally {
      setScheduling(false)
    }
  }

  if (error) {
    return <p className="text-destructive">Failed to load candidate: {error}</p>
  }

  if (!candidate) {
    return <p className="text-muted-foreground">Loading...</p>
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
          &larr; Back to pipeline
        </Link>
        <div className="mt-2 flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{candidate.name}</h1>
          <StageBadge stage={candidate.stage} />
        </div>
        <p className="text-muted-foreground">{candidate.job_posting_title}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Application</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-1 text-sm">
          <p>
            <span className="text-muted-foreground">Email: </span>
            {candidate.email}
          </p>
          <p>
            <span className="text-muted-foreground">Phone: </span>
            {candidate.phone}
          </p>
          <p>
            <span className="text-muted-foreground">Address: </span>
            {candidate.address}
          </p>
          <a
            href={`${API_BASE_URL}${candidate.resume_file_path}`}
            target="_blank"
            rel="noreferrer"
            className="mt-1 text-primary underline-offset-4 hover:underline"
          >
            Download resume
          </a>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Chat / email history</CardTitle>
        </CardHeader>
        <CardContent>
          {candidate.messages.length === 0 ? (
            <p className="text-muted-foreground text-sm">No messages yet.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {candidate.messages.map((message) => (
                <div key={message.id} className="text-sm">
                  <span className="text-muted-foreground">
                    {message.direction === 'inbound' ? 'Candidate' : 'Agent'} &middot;{' '}
                    {new Date(message.created_at).toLocaleString()}
                  </span>
                  <p className="whitespace-pre-wrap">{message.content}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {candidate.screening_transcript && (
        <Card>
          <CardHeader>
            <CardTitle>Screening transcript</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm">{candidate.screening_transcript}</p>
          </CardContent>
        </Card>
      )}

      {candidate.stage === 'shortlisted' && (
        <Card>
          <CardHeader>
            <CardTitle>Schedule Interview</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-4" onSubmit={handleScheduleSubmit}>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="scheduled_at">Date &amp; time</Label>
                <Input id="scheduled_at" name="scheduled_at" type="datetime-local" required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="interview_notes">Notes (meeting link, interviewer, ...)</Label>
                <Textarea id="interview_notes" name="interview_notes" rows={3} />
              </div>
              {schedulingError && (
                <p className="text-sm text-destructive">{schedulingError}</p>
              )}
              <Button type="submit" disabled={scheduling} className="w-fit">
                {scheduling ? 'Scheduling...' : 'Schedule Interview'}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {(candidate.stage === 'interview_scheduled' || candidate.stage === 'confirmed') &&
        candidate.scheduled_at && (
          <Card>
            <CardHeader>
              <CardTitle>Interview scheduled</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-1 text-sm">
              <p>
                <span className="text-muted-foreground">When: </span>
                {new Date(candidate.scheduled_at).toLocaleString()}
              </p>
              {candidate.interview_notes && (
                <p>
                  <span className="text-muted-foreground">Notes: </span>
                  {candidate.interview_notes}
                </p>
              )}
            </CardContent>
          </Card>
        )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          disabled={pendingAction === 'review'}
          onClick={() => runAction('review', () => reviewWithAi(id!))}
        >
          {pendingAction === 'review' ? 'Reviewing...' : 'Review with AI'}
        </Button>

        {candidate.stage === 'applied' && (
          <div className="flex flex-col gap-1">
            <Button
              disabled={pendingAction === 'assign' || !candidate.screening_questions_available}
              onClick={() => runAction('assign', () => assignScreening(id!))}
            >
              {pendingAction === 'assign' ? 'Assigning...' : 'Assign Screening'}
            </Button>
            {!candidate.screening_questions_available && (
              <p className="text-xs text-muted-foreground">
                Add screening questions to this job posting before screening candidates.
              </p>
            )}
          </div>
        )}

        {candidate.stage === 'screening_completed' && (
          <Button
            disabled={pendingAction === 'shortlist'}
            onClick={() => runAction('shortlist', () => shortlistCandidate(id!))}
          >
            {pendingAction === 'shortlist' ? 'Shortlisting...' : 'Shortlist for Next Round'}
          </Button>
        )}
      </div>

      {actionError && (
        <>
          <Separator />
          <p className="text-destructive text-sm">{actionError}</p>
        </>
      )}
    </div>
  )
}
