import { useEffect, useState } from 'react'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { UpcomingInterview } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function InterviewsPage() {
  const { listUpcomingInterviews } = useAuthedApi()
  const [interviews, setInterviews] = useState<UpcomingInterview[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listUpcomingInterviews()
      .then(setInterviews)
      .catch((err: Error) => setError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Upcoming interviews</h1>

      {error && <p className="text-destructive">Failed to load interviews: {error}</p>}
      {!error && interviews === null && <p className="text-muted-foreground">Loading...</p>}
      {interviews?.length === 0 && (
        <p className="text-muted-foreground">No interviews scheduled.</p>
      )}

      <div className="flex flex-col gap-3">
        {interviews?.map((interview) => (
          <Card key={interview.id}>
            <CardHeader>
              <CardTitle className="text-base">{interview.candidate_name}</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between text-sm text-muted-foreground">
              <span>{interview.job_posting_title}</span>
              <span>{new Date(interview.scheduled_at).toLocaleString()}</span>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
