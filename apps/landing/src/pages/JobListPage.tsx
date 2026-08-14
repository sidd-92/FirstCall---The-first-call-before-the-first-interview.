import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { listJobs, type JobPosting } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function JobListPage() {
  const [jobs, setJobs] = useState<JobPosting[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listJobs()
      .then(setJobs)
      .catch((err: Error) => setError(err.message))
  }, [])

  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="mb-8 text-3xl font-semibold tracking-tight">Open positions</h1>

      {error && <p className="text-destructive">Failed to load job postings: {error}</p>}
      {!error && jobs === null && <p className="text-muted-foreground">Loading jobs...</p>}
      {jobs?.length === 0 && <p className="text-muted-foreground">No open positions right now.</p>}

      <div className="flex flex-col gap-4">
        {jobs?.map((job) => (
          <Card key={job.id}>
            <CardHeader>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-accent">{job.business_name}</p>
                  <CardTitle>{job.title}</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {[job.location, job.employment_type].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <Button asChild>
                  <Link to={`/jobs/${job.id}`}>View</Link>
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">{job.description}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  )
}
