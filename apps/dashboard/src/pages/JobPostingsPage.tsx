import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { JobPostingSummary } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function JobPostingsPage() {
  const { listJobPostings } = useAuthedApi()
  const [postings, setPostings] = useState<JobPostingSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listJobPostings()
      .then(setPostings)
      .catch((err: Error) => setError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Job postings</h1>

      {error && <p className="text-destructive">Failed to load job postings: {error}</p>}
      {!error && postings === null && <p className="text-muted-foreground">Loading...</p>}
      {postings?.length === 0 && (
        <p className="text-muted-foreground">No job postings yet.</p>
      )}

      <div className="flex flex-col gap-3">
        {postings?.map((posting) => (
          <Link key={posting.id} to={`/jobs/${posting.id}`}>
            <Card className="transition-colors hover:bg-muted/50">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{posting.title}</CardTitle>
                  {!posting.is_active && <Badge variant="outline">Inactive</Badge>}
                </div>
              </CardHeader>
              <CardContent className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                <span>{posting.location || 'No location set'}</span>
                <span>&middot;</span>
                <span>{posting.employment_type || 'No type set'}</span>
                <span>&middot;</span>
                <span>
                  {posting.faq_count} FAQ {posting.faq_count === 1 ? 'entry' : 'entries'}
                </span>
                <span>&middot;</span>
                <span>
                  {posting.screening_question_count} screening{' '}
                  {posting.screening_question_count === 1 ? 'question' : 'questions'}
                </span>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
