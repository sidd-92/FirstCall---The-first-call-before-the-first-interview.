import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { CandidateSummary } from '@/lib/types'
import { StageBadge } from '@/components/StageBadge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export function CandidatePipelinePage() {
  const { listCandidates } = useAuthedApi()
  const [candidates, setCandidates] = useState<CandidateSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listCandidates()
      .then(setCandidates)
      .catch((err: Error) => setError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Candidate pipeline</h1>

      {error && <p className="text-destructive">Failed to load candidates: {error}</p>}
      {!error && candidates === null && <p className="text-muted-foreground">Loading...</p>}
      {candidates?.length === 0 && (
        <p className="text-muted-foreground">No candidates yet.</p>
      )}

      {candidates && candidates.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Job posting</TableHead>
              <TableHead>Stage</TableHead>
              <TableHead>Last activity</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {candidates.map((candidate) => (
              <TableRow key={candidate.id}>
                <TableCell>
                  <Link
                    to={`/candidates/${candidate.id}`}
                    className="font-medium hover:underline"
                  >
                    {candidate.name}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {candidate.job_posting_title}
                </TableCell>
                <TableCell>
                  <StageBadge stage={candidate.stage} />
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(candidate.last_activity_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
